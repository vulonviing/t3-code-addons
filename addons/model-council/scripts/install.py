#!/usr/bin/env python3
"""Build, verify and reversibly inject the Model Council addon."""
import argparse
import fcntl
import json
import os
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest
from lifecycle import Transaction, changes, inventory, write_json
import signing
from discover import discover as discover_assets, render_adapter

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT
STATE_ROOT = Path(os.environ.get('T3_ADDS_STATE_DIR', Path.home() / 'Library/Application Support/T3 Adds')).expanduser()
STATE = STATE_ROOT / 'model-council'
PREFIX = 'apps/server/dist/client/'
ENTRY = PREFIX + 'index.html'
MARKER = '<!-- t3-adds:model-council -->'
ASSETS = PREFIX + 'assets/model-council/'
TAG = MARKER + '\n    <script type="module" src="/assets/model-council/ui.mjs"></script>'
RECEIPT = STATE / 'backups/model-council-install.json'


def backup_path(value):
    path = Path(value)
    return path if path.is_absolute() else STATE / path


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def discover(archive):
    """Find the client modules this addon imports by how the client uses them. Never refuses.

    A module that cannot be found is listed in `missing`; the generated adapter then reports it at runtime in a
    dismissible note instead of attaching, which cannot harm the application.
    """
    client = PREFIX + 'assets/'
    assets = {}

    def walk(node, prefix=''):
        for name, value in node.get('files', {}).items():
            if 'files' in value:
                walk(value, prefix + name + '/')
            elif prefix == client and name.endswith('.js') and 'link' not in value and not value.get('unpacked'):
                assets[name] = archive.read(prefix + name)

    walk(archive.header)
    return discover_assets(assets)


def host_discovery(app):
    return discover(Archive(Path(app) / 'Contents/Resources/app.asar'))


def sources(found):
    files = {ASSETS + path.name: path.read_bytes() for path in sorted((MODULE / 'src').glob('*.mjs'))}
    files[ASSETS + 'host.mjs'] = render_adapter(found).encode()
    return files


def replacements(archive, found):
    index = archive.read(ENTRY).decode()
    if MARKER in index:
        raise ValueError('Addon already present; restore the recorded original before rebuilding.')
    if index.count('</body>') != 1:
        raise ValueError('Unsupported client index: body anchor is not unique.')
    return {ENTRY: index.replace('</body>', TAG + '\n  </body>').encode(), **sources(found)}


def verify_original(app):
    """No T3 version, commit, or chunk-hash gate. Only a readable archive with the client entry is required."""
    archive = Archive(app / 'Contents/Resources/app.asar')
    archive.read('package.json')
    archive.read(ENTRY)
    return archive


def logical_entries(app):
    """Logical ASAR entries: content hash, or link target. Unpacked entries are compared only as {'unpacked': True},
    so this check cannot see edits to their contents; those are covered only by the bundle inventory and signature
    checks (unpacked native code is re-signed with the bundle, so its bytes legitimately change)."""
    archive = Archive(Path(app) / 'Contents/Resources/app.asar')
    result = {}

    def walk(node, prefix=''):
        for name, value in node.get('files', {}).items():
            path = prefix + name
            if 'files' in value:
                walk(value, path + '/')
            elif 'link' in value:
                result[path] = {'link': value['link']}
            elif value.get('unpacked'):
                result[path] = {'unpacked': True}
            else:
                result[path] = {'sha256': digest(archive.read(path))}

    walk(archive.header)
    return result


def validate_prepared(app, original):
    """Exactly the entry tag and this addon's files differ from the original archive; integrity and signature hold."""
    found = host_discovery(original)
    archive = Archive(app / 'Contents/Resources/app.asar')
    expected = sources(found)
    before, after = logical_entries(original), logical_entries(app)
    unexpected = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)} - set(expected) - {ENTRY}
    if unexpected:
        raise ValueError('Unexpected host change: ' + ', '.join(sorted(unexpected)[:5]))
    if archive.read(ENTRY).decode().count(MARKER) != 1:
        raise ValueError('Missing or duplicate addon entry')
    for path, data in expected.items():
        if archive.read(path) != data:
            raise ValueError(f'Addon mismatch: {path[len(ASSETS):]}')
    with (app / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    if plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] != digest(archive.header_bytes):
        raise ValueError('Electron ASAR integrity mismatch')
    run('codesign', '--verify', '--deep', '--strict', str(app))


def identity(app):
    with (app / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    archive = Archive(app / 'Contents/Resources/app.asar')
    package = json.loads(archive.read('package.json'))
    return {'bundleId': plist['CFBundleIdentifier'], 'version': package['version'],
            'commit': package.get('t3codeCommitHash')}


def verify_signed(app):
    run('codesign', '--verify', '--deep', '--strict', str(app))


def recorded_teams(app):
    """Distributor teams recorded for this application: earlier official installs and verified original backups."""
    teams = set()
    for path in (STATE / 'transactions').glob('*.json'):
        try:
            value = json.loads(path.read_text()).get('metadata', {}).get('distributorTeam')
        except (OSError, ValueError, AttributeError):
            continue
        if value and value != 'not set':
            teams.add(value)
    for backup in (STATE / 'backups').glob('*/' + app.name):
        try:
            value = team(backup)
        except (ValueError, OSError, subprocess.CalledProcessError):
            continue
        if value and value != 'not set':
            teams.add(value)
    return teams


def team(app):
    verify_signed(app)
    result = subprocess.run(['codesign', '-dv', str(app)], check=True, capture_output=True, text=True)
    return next((line.split('=', 1)[1] for line in result.stderr.splitlines()
                 if line.startswith('TeamIdentifier=')), None)


def source_record():
    paths = [ROOT / name for name in ('addon.json', 'compatibility.json', 'integration.patch', 'src/host.template')]
    paths += sorted((ROOT / 'src').glob('*.mjs'))
    paths += sorted(path for path in (ROOT / 'scripts').iterdir() if path.suffix in ('.py', '.mjs'))
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def archive_changes(original, installed):
    def entries(app):
        archive = Archive(app / 'Contents/Resources/app.asar')
        result = {}
        def walk(node, prefix=''):
            for name, value in node.get('files', {}).items():
                path = prefix + name
                if 'files' in value:
                    walk(value, path + '/')
                elif 'link' in value:
                    result[path] = {'link': value['link']}
                else:
                    result[path] = {'sha256': digest(archive.read(path)), 'unpacked': bool(value.get('unpacked'))}
        walk(archive.header)
        return result
    return changes(entries(original), entries(installed))


def is_code_signature_file(path):
    return path == '_CodeSignature/CodeResources' or path.endswith('/_CodeSignature/CodeResources')


def is_macho(path):
    try:
        with open(path, 'rb') as stream:
            return stream.read(4) in signing.MACHO
    except OSError:
        return False


def unsigned_code_equal(first, second):
    """Compare code after removing signatures from disposable external copies."""
    with tempfile.TemporaryDirectory(prefix='t3-code-compare-') as directory:
        copies = [Path(directory) / name for name in ('first', 'second')]
        for source, target in zip((first, second), copies):
            shutil.copy2(source, target)
            run('/usr/bin/codesign', '--remove-signature', str(target))
        return copies[0].read_bytes() == copies[1].read_bytes()


def signature_drift(app, original, receipt, current, layered=False):
    """Return the files whose bytes differ only because codesign rewrote them, or refuse.

    Allowed: regular files that were Mach-O code in the original, or a bundle's
    _CodeSignature/CodeResources, with equal size and mode. Everything else must match the receipt.
    """
    recorded = receipt['installedInventory']
    if current.keys() != recorded.keys():
        extra = sorted(current.keys() ^ recorded.keys())[:3]
        raise ValueError(f'Application changed since recording (files added or removed: {extra}); refusing replacement.')
    drift = []
    for path in sorted(current):
        now, before = current[path], recorded[path]
        if now == before:
            continue
        if layered and path in LAYERED_SKIPPED:
            continue  # the archive and the plist integrity hash are checked separately
        same_shape = (now.get('kind') == before.get('kind') == 'file' and now['size'] == before['size']
                      and now['mode'] == before['mode'])
        code = is_code_signature_file(path) or (is_macho(original / path) and is_macho(app / path))
        if not (same_shape and code) or (not is_code_signature_file(path) and
                not unsigned_code_equal(original / path, app / path)):
            raise ValueError(f'Application changed since recording ({path} is not a signature-only difference); refusing replacement.')
        drift.append(path)
    return drift


LAYERED_SKIPPED = ('Contents/Resources/app.asar', 'Contents/Info.plist')
OTHER_ADDON = re.compile(r'<!-- t3-adds:[\w-]+ -->\n\s*<script type="module" src="/assets/[\w-]+/[\w.-]+"></script>\n  ')
OWN_BLOCK = TAG + '\n  '


def owned_entries(receipt):
    """The archive files this addon added: recorded directly, or derived from an older receipt's archive changes."""
    if receipt.get('ownedEntries'):
        return dict(receipt['ownedEntries'])
    return {c['path']: c['after']['sha256'] for c in receipt.get('archiveChanges', [])
            if c['path'].startswith(ASSETS) and c.get('after') and c['after'].get('sha256')}


def plist_without_integrity(path):
    with (Path(path) / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    plist.get('ElectronAsarIntegrity', {}).get('Resources/app.asar', {}).pop('hash', None)
    return plist


def check_layered(app, original, receipt):
    """Verify only what this addon owns while other addons are installed beside it.

    The archive must equal the original plus this addon's files and tag plus other addons' marked additions (files
    under their own assets/<id>/ directory and their marked script lines). Anything else, such as an official update
    that replaced the archive, is refused. Unpacked entries are compared only as {'unpacked': True}.
    """
    changed = 'Installation changed since injection; refusing to overwrite an update.'
    owned = owned_entries(receipt)
    if not owned or 'installedInventory' not in receipt:
        raise ValueError(changed + ' (This receipt cannot be verified beside other addons.)')
    current, base = logical_entries(app), logical_entries(original)
    for path, expected in owned.items():
        if current.get(path, {}).get('sha256') != expected:
            raise ValueError(f'Model Council file changed or missing: {path[len(ASSETS):]}')
    archive = Archive(app / 'Contents/Resources/app.asar')
    index = archive.read(ENTRY).decode()
    if index.count(MARKER) != 1 or index.count(OWN_BLOCK) != 1:
        raise ValueError('The Model Council entry in the installed application is missing or was changed.')
    stripped = OTHER_ADDON.sub('', index.replace(OWN_BLOCK, '', 1))
    if stripped != Archive(original / 'Contents/Resources/app.asar').read(ENTRY).decode():
        raise ValueError(changed)
    other = PREFIX + 'assets/'
    # Only addons whose marked script line is actually present may add files, and only under their own assets/<id>/.
    marked = {m for m in re.findall(r'<!-- t3-adds:[\w-]+ -->\n\s*<script type="module" src="/assets/([\w-]+)/', index)}
    marked.discard('model-council')
    for path in sorted(current.keys() | base.keys()):
        if path in owned or path == ENTRY or current.get(path) == base.get(path):
            continue
        if path not in base and path.startswith(other) and path[len(other):].split('/', 1)[0] in marked and '/' in path[len(other):]:
            continue  # a marked addon's own assets/<id>/ file; Model Council's own directory is never tolerated
        raise ValueError(changed)
    if receipt.get('host', {}).get('bundleId') and identity(app)['bundleId'] != receipt['host']['bundleId']:
        raise ValueError(changed)
    for chunk, expected in receipt.get('hostDiscovery', {}).get('chunkSha256', {}).items():
        if current.get(PREFIX + 'assets/' + chunk, {}).get('sha256') != expected:
            raise ValueError(changed)
    if plist_without_integrity(app) != plist_without_integrity(original):
        raise ValueError(changed)


def checked_receipt(app, persist_adoption=False):
    receipt = json.loads(RECEIPT.read_text())
    if receipt['app'] != str(app):
        raise ValueError('Receipt belongs to a different installation.')
    original = backup_path(receipt['backup'])
    verify_signed(original)
    layered = digest((app / 'Contents/Resources/app.asar').read_bytes()) != receipt['installedAsarHash']
    if layered:
        # Other addons changed the archive after injection: verify only what this addon owns.
        check_layered(app, original, receipt)
        receipt['layered'] = True
    if 'installedInventory' in receipt:
        if inventory(original) != receipt['originalInventory']:
            raise ValueError('Application or original backup changed since recording; refusing replacement.')
        current = inventory(app)
        if current != receipt['installedInventory']:
            drift = signature_drift(app, original, receipt, current, layered)
            # Accept re-signing only when the strict pinned-certificate verification passes first.
            if not receipt.get('signing'):
                raise ValueError('Application changed since recording and no pinned signing record exists; refusing replacement.')
            signing.verify(app, receipt['signing'])
            receipt['acceptedSignatureDrift'] = drift
            print(f'Notice: accepted signature-only drift in {len(drift)} files (the app was re-signed by the pinned local certificate, for example by an overlay addon).')
        elif receipt.get('signing'):
            signing.verify(app, receipt['signing'])
    else:
        verify_original(original)
        # Legacy receipts recorded only the ASAR. Reconstruct the expected bundle
        # before adopting it; do not invent a historical per-file audit trail.
        with tempfile.TemporaryDirectory(prefix='adopt-', dir=STATE) as temp:
            expected = prepare(original, Path(temp) / app.name)
            if inventory(expected) != inventory(app):
                raise ValueError('Legacy installation differs from a reproducible build. Inspect before adoption.')
        receipt.update(schemaVersion=2, adoptedLegacy=True,
                       host=identity(original), addon=json.loads((ROOT / 'addon.json').read_text()),
                       sources=source_record(),
                       originalInventory=inventory(original), installedInventory=inventory(app),
                       adoptionEvidence='Current bundle matches reconstruction from signed original and current source.')
        receipt['changes'] = changes(receipt['originalInventory'], receipt['installedInventory'])
        receipt['archiveChanges'] = archive_changes(original, app)
        if persist_adoption:
            write_json(RECEIPT, receipt)
    return receipt, original


def prepare(app, staged):
    signing.load(STATE)
    original = verify_original(app)
    if staged.exists():
        raise ValueError(f'Staging path exists: {staged}')
    staged.parent.mkdir(parents=True, exist_ok=True)
    run('ditto', str(app), str(staged))
    archive_path = staged / 'Contents/Resources/app.asar'
    rewritten = archive_path.with_suffix('.asar.new')
    header_hash = original.rewrite(rewritten, replacements(original, discover(original)))
    os.replace(rewritten, archive_path)
    info = staged / 'Contents/Info.plist'
    with info.open('rb') as stream:
        plist = plistlib.load(stream)
    plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
    with info.open('wb') as stream:
        plistlib.dump(plist, stream)
    signature = signing.sign(staged, STATE)
    validate_prepared(staged, app)
    write_json(staged.with_name(staged.name + '.prepared.json'),
               dict(original=inventory(app), prepared=inventory(staged), sources=source_record(), signing=signature))
    return staged


def validate_layered(app, before, replacements, removals):
    """After a layered operation exactly the planned entries changed; integrity and signature hold."""
    after = logical_entries(app)
    planned = set(replacements) | set(removals)
    unexpected = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)} - planned
    if unexpected:
        raise ValueError('Unexpected host change: ' + ', '.join(sorted(unexpected)[:5]))
    archive = Archive(app / 'Contents/Resources/app.asar')
    for path, data in replacements.items():
        if after.get(path, {}).get('sha256') != digest(data):
            raise ValueError(f'Addon mismatch: {path}')
    for path in removals:
        if path in after:
            raise ValueError(f'Entry was not removed: {path}')
    with (app / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    if plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] != digest(archive.header_bytes):
        raise ValueError('Electron ASAR integrity mismatch')
    run('codesign', '--verify', '--deep', '--strict', str(app))


def layered_operation(args, app, receipt, transaction):
    """Withdraw or update only this addon's entries in an archive that other addons also changed.

    The current application is copied, only the recorded entries are rewritten, and the copy is re-signed with the
    persistent certificate. The previous application stays recoverable, and nothing else in the archive is touched.
    """
    if args.staged.exists():
        raise ValueError('Staging path exists; preserve or remove it before this operation.')
    archive = Archive(app / 'Contents/Resources/app.asar')
    owned = owned_entries(receipt)
    index = archive.read(ENTRY).decode()
    found = None
    if args.action == 'restore':
        replacements, removals = {ENTRY: index.replace(OWN_BLOCK, '', 1).encode()}, sorted(owned)
    else:
        found = discover(archive)
        replacements = sources(found)
        removals = sorted(set(owned) - set(replacements))
    before = logical_entries(app)
    signing.load(STATE)
    args.staged.parent.mkdir(parents=True, exist_ok=True)
    run('ditto', str(app), str(args.staged))
    archive_path = args.staged / 'Contents/Resources/app.asar'
    rewritten = archive_path.with_suffix('.asar.new')
    header_hash = archive.rewrite(rewritten, replacements, removals)
    os.replace(rewritten, archive_path)
    info = args.staged / 'Contents/Info.plist'
    with info.open('rb') as stream:
        plist = plistlib.load(stream)
    plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
    with info.open('wb') as stream:
        plistlib.dump(plist, stream)
    signature = signing.sign(args.staged, STATE)
    validate_layered(args.staged, before, replacements, removals)

    def validator(path):
        validate_layered(path, before, replacements, removals)
        signing.verify(path, signing.load(STATE))

    next_receipt = None
    if args.action == 'update':
        installed = inventory(args.staged)
        next_receipt = {key: value for key, value in receipt.items() if key not in ('layered', 'acceptedSignatureDrift')}
        next_receipt.update(addon=json.loads((ROOT / 'addon.json').read_text()), sources=source_record(),
                            hostDiscovery=found, signing=signature,
                            ownedEntries={path: digest(data) for path, data in replacements.items() if path.startswith(ASSETS)},
                            installedAsarHash=digest(archive_path.read_bytes()), installedInventory=installed,
                            archiveChanges=changes(before, logical_entries(args.staged)))
    transaction.start(app, args.staged, RECEIPT, next_receipt,
                      dict(action=args.action, layered=True, host=identity(app), sources=source_record()))
    transaction.execute(validator)
    print('Model Council withdrawn; other addons and official files were not touched.' if args.action == 'restore'
          else 'Model Council updated; other addons and official files were not touched.')
    print('File changes and recovery copies recorded outside the project. Restart T3 to load the installed bundle.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'setup-signing', 'stage', 'apply', 'update', 'restore', 'recover', 'install-official'])
    parser.add_argument('--app', type=Path, default=Path('/Applications/T3 Code (Beta).app'))
    parser.add_argument('--staged', type=Path, default=STATE / '.cache/staged/T3 Code (Beta).app')
    parser.add_argument('--candidate', type=Path, help='Extracted official application for install-official')
    args = parser.parse_args()
    app = args.app.resolve()
    project = ROOT.parents[1] if ROOT.parent.name == 'addons' and (ROOT.parents[1] / 'AGENTS.md').exists() else ROOT
    for local in (STATE, args.staged, app, args.candidate):
        if local is not None and (local.resolve() == project or project in local.resolve().parents):
            raise ValueError('Application bundles, staging, and installation state must stay outside the project.')
    # A second installer must never race an application swap or receipt update.
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'installation.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        execute(args, app)


def execute(args, app):
    transaction = Transaction(STATE)
    if args.action == 'recover':
        print(transaction.recover(verify_signed))
        return
    transaction.require_idle()
    if args.action == 'setup-signing':
        signing.setup(STATE)
        print('Persistent local signing configured in Keychain. No subscription or developer account is required.')
        return
    if args.action == 'check':
        if RECEIPT.exists():
            receipt, original = checked_receipt(app)
            verify_signed(app)
            print('Model Council installed; full bundle, original backup, and receipt verified.')
        else:
            verify_original(app)
            verify_signed(app)
            print('Original T3 installation verified.')
            found = host_discovery(app)
            if found['missing']:
                print('Warning: could not find in this T3 release: ' + ', '.join(found['missing'])
                      + '. An install would still be safe; the addon would show a dismissible note instead of attaching.')
            else:
                print('All T3 client modules this addon uses were found by signature.')
        return
    if args.action == 'stage':
        print(prepare(app, args.staged))
        return
    if args.action == 'install-official':
        if RECEIPT.exists():
            raise ValueError('Withdraw Model Council before installing an official update.')
        if args.candidate is None:
            raise ValueError('install-official requires --candidate.')
        candidate = args.candidate.resolve()
        before, after = identity(app), identity(candidate)
        current_team, candidate_team = team(app), team(candidate)
        if not candidate_team or candidate_team == 'not set':
            raise ValueError('Official update must have a verified distributor team.')
        locally_signed = not current_team or current_team == 'not set'
        # A locally signed app (for example after an overlay) has no distributor team, so compare with the team
        # recorded for the original app instead of the live bundle.
        teams = {current_team} if not locally_signed else recorded_teams(app)
        if candidate_team not in teams:
            raise ValueError('Official update must have the same verified distributor team as the original app.')
        if before['bundleId'] != after['bundleId']:
            raise ValueError('Official update has a different application identity.')
        def version(value):
            parts = value.split('.')
            if len(parts) != 3 or not all(part.isdigit() for part in parts):
                raise ValueError('Automatic installation supports stable numeric versions only.')
            return tuple(map(int, parts))
        if version(after['version']) < version(before['version']) or (
                version(after['version']) == version(before['version']) and not locally_signed):
            raise ValueError('Candidate must be a newer official release; no downgrade, and no same-version '
                             'reinstall over a distributor-signed app.')
        transaction.start(app, candidate, RECEIPT, None,
                          dict(action='install-official', hostBefore=before, hostAfter=after,
                               distributorTeam=candidate_team))
        transaction.execute(verify_signed)
        print('Official T3 update installed and verified. Restart T3. Addons remain withdrawn pending review.')
        return
    if args.action in ('update', 'restore'):
        receipt, original = checked_receipt(app, persist_adoption=True)
        if receipt.get('layered'):
            return layered_operation(args, app, receipt, transaction)
    else:
        if RECEIPT.exists():
            raise ValueError('An installation receipt exists. Check or restore it before applying again.')
        verify_original(app)
        verify_signed(app)
        original = app
        receipt = None
        if team(original) in (None, 'not set'):
            raise ValueError('A clean distributor-signed original is required; composed addon installs need a verified plan.')
    if args.action == 'restore':
        if args.staged.exists():
            raise ValueError('Staging path exists; preserve or remove it before restoration.')
        args.staged.parent.mkdir(parents=True, exist_ok=True)
        run('ditto', str(original), str(args.staged))
        if inventory(args.staged) != receipt['originalInventory']:
            raise ValueError('Restoration copy differs from the recorded original.')
        validator = verify_signed
        next_receipt = None
    else:
        if args.staged.exists():
            prepared_record = args.staged.with_name(args.staged.name + '.prepared.json')
            if not prepared_record.exists():
                raise ValueError('Unrecorded staged application; preserve it and prepare a new staging path.')
            expected = json.loads(prepared_record.read_text())
            if (expected['original'] != inventory(original) or expected['prepared'] != inventory(args.staged)
                    or expected['sources'] != source_record()):
                raise ValueError('Staging contents, source, or original changed; prepare a new staging path.')
            config = signing.load(STATE)
            if expected.get('signing', {}).get('sha1') != config['sha1']:
                raise ValueError('Staged signing identity differs from the configured persistent identity; prepare a new staging path.')
            signing.verify(args.staged, config)
            validate_prepared(args.staged, original)
        else:
            prepare(original, args.staged)
        def validator(path):
            validate_prepared(path, original)
            signing.verify(path, signing.load(STATE))
        installed = inventory(args.staged)
        next_receipt = dict(schemaVersion=2, app=str(app),
                            addon=json.loads((ROOT / 'addon.json').read_text()),
                            host=identity(original), sources=source_record(),
                            hostDiscovery=host_discovery(original),
                            ownedEntries={path: digest(data) for path, data in sources(host_discovery(original)).items()},
                            installedAsarHash=digest((args.staged / 'Contents/Resources/app.asar').read_bytes()),
                            originalAsarHash=digest((original / 'Contents/Resources/app.asar').read_bytes()),
                            originalInventory=inventory(original), installedInventory=installed)
        next_receipt['signing'] = json.loads(args.staged.with_name(args.staged.name + '.prepared.json').read_text())['signing']
        next_receipt['verification'] = {'originalSignature': 'passed', 'preparedSignature': 'passed',
                                        'asarIntegrity': 'passed', 'addonSources': 'passed',
                                        'persistentSigningRequirements': 'passed'}
        next_receipt['changes'] = changes(next_receipt['originalInventory'], installed)
        next_receipt['archiveChanges'] = archive_changes(original, args.staged)
        if receipt:
            next_receipt['backup'] = receipt['backup']
            if receipt.get('acceptedSignatureDrift'):
                next_receipt['acceptedSignatureDrift'] = receipt['acceptedSignatureDrift']
    record = transaction.start(app, args.staged, RECEIPT, next_receipt,
                               dict(action=args.action, host=identity(original), sources=source_record(),
                                    acceptedSignatureDrift=(receipt or {}).get('acceptedSignatureDrift', [])))
    if args.action == 'apply':
        next_receipt['backup'] = str(Path(record['previous']).relative_to(STATE))
        record['receiptAfter'] = next_receipt
        write_json(transaction.pending, record)
    transaction.execute(validator)
    print('Original signed T3 restored.' if args.action == 'restore' else 'Model Council installed and verified.')
    print('File changes and recovery copies recorded outside the project. Restart T3 to load the installed bundle.')


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        message = str(error)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            message += '\n' + error.stderr.decode(errors='replace')
        print('Installation stopped: ' + message, file=sys.stderr)
        sys.exit(1)
