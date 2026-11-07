#!/usr/bin/env python3
"""Build, verify and reversibly inject the pinned Model Council addon."""
import argparse
import fcntl
import json
import os
import plistlib
import subprocess
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest
from lifecycle import Transaction, changes, inventory, write_json
import signing

ROOT = Path(__file__).resolve().parents[1]
MODULE = ROOT
STATE_ROOT = Path(os.environ.get('T3_ADDS_STATE_DIR', Path.home() / 'Library/Application Support/T3 Adds')).expanduser()
STATE = STATE_ROOT / 'model-council'
PREFIX = 'apps/server/dist/client/'
ENTRY = PREFIX + 'index.html'
MARKER = '<!-- t3-adds:model-council -->'
TAG = MARKER + '\n    <script type="module" src="/assets/model-council/ui.mjs"></script>'
RECEIPT = STATE / 'backups/model-council-install.json'


def backup_path(value):
    path = Path(value)
    return path if path.is_absolute() else STATE / path


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def replacements(archive):
    index = archive.read(ENTRY).decode()
    if MARKER in index:
        raise ValueError('Addon already present; restore the recorded original before rebuilding.')
    if index.count('</body>') != 1:
        raise ValueError('Unsupported client index: body anchor is not unique.')
    result = {ENTRY: index.replace('</body>', TAG + '\n  </body>').encode()}
    for path in sorted((MODULE / 'src').glob('*.mjs')):
        result[PREFIX + 'assets/model-council/' + path.name] = path.read_bytes()
    return result


def verify_original(app):
    archive = Archive(app / 'Contents/Resources/app.asar')
    package = json.loads(archive.read('package.json'))
    manifest = json.loads((MODULE / 'addon.json').read_text())
    compatible = manifest['compatibility']
    if package['version'] != compatible['version'] or package.get('t3codeCommitHash') != compatible['commit']:
        raise ValueError(f"Unsupported T3 build: {package['version']} / {package.get('t3codeCommitHash')}")
    hashes = json.loads((MODULE / 'compatibility.json').read_text())
    for path, expected in hashes.items():
        if digest(archive.read(path)) != expected:
            raise ValueError(f'Changed or unsupported integration file: {path}')
    return archive


def validate_prepared(app):
    archive = Archive(app / 'Contents/Resources/app.asar')
    expected = json.loads((MODULE / 'compatibility.json').read_text())
    for path, hash_ in expected.items():
        if path != ENTRY and digest(archive.read(path)) != hash_:
            raise ValueError(f'Unexpected host change: {path}')
    if archive.read(ENTRY).decode().count(MARKER) != 1:
        raise ValueError('Missing or duplicate addon entry')
    for source in (MODULE / 'src').glob('*.mjs'):
        if archive.read(PREFIX + 'assets/model-council/' + source.name) != source.read_bytes():
            raise ValueError(f'Addon mismatch: {source.name}')
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


def team(app):
    verify_signed(app)
    result = subprocess.run(['codesign', '-dv', str(app)], check=True, capture_output=True, text=True)
    return next((line.split('=', 1)[1] for line in result.stderr.splitlines()
                 if line.startswith('TeamIdentifier=')), None)


def source_record():
    paths = [ROOT / name for name in ('addon.json', 'compatibility.json', 'integration.patch')]
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


def checked_receipt(app, persist_adoption=False):
    receipt = json.loads(RECEIPT.read_text())
    if receipt['app'] != str(app):
        raise ValueError('Receipt belongs to a different installation.')
    original = backup_path(receipt['backup'])
    verify_signed(original)
    if digest((app / 'Contents/Resources/app.asar').read_bytes()) != receipt['installedAsarHash']:
        raise ValueError('Installation changed since injection; refusing to overwrite an update.')
    if 'installedInventory' in receipt:
        if inventory(app) != receipt['installedInventory'] or inventory(original) != receipt['originalInventory']:
            raise ValueError('Application or original backup changed since recording; refusing replacement.')
        if receipt.get('signing'):
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
    header_hash = original.rewrite(rewritten, replacements(original))
    os.replace(rewritten, archive_path)
    info = staged / 'Contents/Info.plist'
    with info.open('rb') as stream:
        plist = plistlib.load(stream)
    plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
    with info.open('wb') as stream:
        plistlib.dump(plist, stream)
    signature = signing.sign(staged, STATE)
    validate_prepared(staged)
    write_json(staged.with_name(staged.name + '.prepared.json'),
               dict(original=inventory(app), prepared=inventory(staged), sources=source_record(), signing=signature))
    return staged


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
            print('Compatible original T3 installation verified.')
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
        if not current_team or current_team == 'not set' or current_team != candidate_team:
            raise ValueError('Official update must have the same verified distributor team as the original app.')
        if before['bundleId'] != after['bundleId']:
            raise ValueError('Official update has a different application identity.')
        def version(value):
            parts = value.split('.')
            if len(parts) != 3 or not all(part.isdigit() for part in parts):
                raise ValueError('Automatic installation supports stable numeric versions only.')
            return tuple(map(int, parts))
        if version(after['version']) <= version(before['version']):
            raise ValueError('Candidate must be a newer official release; no downgrade or reinstall.')
        transaction.start(app, candidate, RECEIPT, None,
                          dict(action='install-official', hostBefore=before, hostAfter=after,
                               distributorTeam=candidate_team))
        transaction.execute(verify_signed)
        print('Official T3 update installed and verified. Restart T3. Addons remain withdrawn pending review.')
        return
    if args.action in ('update', 'restore'):
        receipt, original = checked_receipt(app, persist_adoption=True)
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
            validate_prepared(args.staged)
        else:
            prepare(original, args.staged)
        def validator(path):
            validate_prepared(path)
            signing.verify(path, signing.load(STATE))
        installed = inventory(args.staged)
        next_receipt = dict(schemaVersion=2, app=str(app),
                            addon=json.loads((ROOT / 'addon.json').read_text()),
                            host=identity(original), sources=source_record(),
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
    record = transaction.start(app, args.staged, RECEIPT, next_receipt,
                               dict(action=args.action, host=identity(original), sources=source_record()))
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
