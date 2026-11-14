#!/usr/bin/env python3
"""Add, update, or withdraw one T3 Adds addon on the installed T3 Code application.

The installer layers a single addon onto whatever application is installed. It never restores a
whole-application backup to withdraw, so other addons and an intervening official update are untouched.
"""
import argparse
import fcntl
import json
import os
import plistlib
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest
from lifecycle import Transaction, changes, inventory, write_json
import signing
from discover import DiscoveryError, discover as discover_assets, render_adapter

ROOT = Path(__file__).resolve().parents[1]
ADDON = json.loads((ROOT / 'addon.json').read_text())
ID = ADDON['id']
STATE_ROOT = Path(os.environ.get('T3_ADDS_STATE_DIR', Path.home() / 'Library/Application Support/T3 Adds')).expanduser()
STATE = STATE_ROOT / ID
PREFIX = 'apps/server/dist/client/'
ENTRY = PREFIX + 'index.html'
ASSETS = PREFIX + 'assets/' + ID + '/'
MARKER = f'<!-- t3-adds:{ID} -->'
TAG = MARKER + '\n    <script type="module" src="/assets/' + ID + '/ui.mjs"></script>'
INSERT = TAG + '\n  '
RECEIPT = STATE / 'installation.json'


def run(*args):
    subprocess.run(args, check=True, capture_output=True)


def verify_signed(app):
    run('codesign', '--verify', '--deep', '--strict', str(app))


def identity(app):
    with (Path(app) / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    package = json.loads(Archive(Path(app) / 'Contents/Resources/app.asar').read('package.json'))
    return {'bundleId': plist['CFBundleIdentifier'], 'version': package['version'],
            'commit': package.get('t3codeCommitHash')}


def verify_host(app):
    archive = Archive(Path(app) / 'Contents/Resources/app.asar')
    package = json.loads(archive.read('package.json'))
    series = ADDON['compatibility']['series']
    if not package['version'].startswith(series + '.'):
        raise ValueError(f"Unsupported T3 build: {package['version']} (this addon supports the {series}.x series)")
    discover(archive)
    return archive


def discover(archive):
    """Find the draft store in the target client by signature; refuse clearly when it is not there."""
    client = PREFIX + 'assets/'
    assets = {}

    def walk(node, prefix=''):
        for name, value in node.get('files', {}).items():
            if 'files' in value:
                walk(value, prefix + name + '/')
            elif prefix == client and name.endswith('.js') and 'link' not in value and not value.get('unpacked'):
                assets[name] = archive.read(prefix + name)

    walk(archive.header)
    try:
        return discover_assets(assets)
    except DiscoveryError as error:
        raise ValueError(f'Unsupported T3 client: {error}')


def entries(app):
    """Logical ASAR entries: content hash, or link target."""
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
                # Unpacked native code is re-signed with the bundle, so its bytes legitimately change;
                # the bundle inventory and signature checks cover it instead.
                result[path] = {'unpacked': True}
            else:
                result[path] = {'sha256': digest(archive.read(path)), 'unpacked': False}

    walk(archive.header)
    return result


def sources(found):
    files = {ASSETS + path.name: path.read_bytes() for path in sorted((ROOT / 'src').glob('*.mjs'))}
    files[ASSETS + 'host.mjs'] = render_adapter(found).encode()
    return files


def source_record():
    paths = [ROOT / name for name in ('addon.json', 'compatibility.json')]
    paths += sorted((ROOT / 'src').glob('*.mjs')) + [ROOT / 'src/host.template']
    paths += sorted(path for path in (ROOT / 'scripts').iterdir() if path.suffix in ('.py', '.mjs'))
    return {str(path.relative_to(ROOT)): digest(path.read_bytes()) for path in paths}


def has_assets(archive):
    try:
        archive.node(ASSETS.rstrip('/'))
        return True
    except KeyError:
        return False


def check_owned(archive, receipt):
    """The recorded entry, files, and nothing else must still be exactly ours before touching them."""
    index = archive.read(ENTRY).decode()
    if index.count(receipt['insert']) != 1 or index.count(MARKER) != 1:
        raise ValueError('The addon entry in the installed application is missing or was changed; refusing to modify it.')
    for path, expected in receipt['ownedEntries'].items():
        try:
            current = digest(archive.read(path))
        except KeyError:
            current = None
        if current != expected:
            raise ValueError(f'Addon file changed or missing since installation: {path}')
    return index


def plan(archive, mode, receipt):
    """Return (replacements, removals) for one addon operation against the current archive."""
    if mode == 'install':
        index = archive.read(ENTRY).decode()
        if MARKER in index or has_assets(archive):
            raise ValueError('Addon already present in the installed application. Check, update, or remove it first.')
        if index.count('</body>') != 1:
            raise ValueError('Unsupported client index: body anchor is not unique.')
        return {ENTRY: index.replace('</body>', INSERT + '</body>').encode(), **sources(discover(archive))}, []
    index = check_owned(archive, receipt)
    if mode == 'remove':
        return {ENTRY: index.replace(receipt['insert'], '', 1).encode()}, sorted(receipt['ownedEntries'])
    replacements = sources(discover(archive))
    if receipt['insert'] != INSERT:
        replacements[ENTRY] = index.replace(receipt['insert'], INSERT, 1).encode()
    return replacements, sorted(set(receipt['ownedEntries']) - set(replacements))


def validate_prepared(before, staged, replacements, removals, present):
    """Exactly the planned logical entries changed; plist integrity and signature hold."""
    after = entries(staged)
    expected = set(replacements) | set(removals)
    unexpected = {p for p in before.keys() | after.keys() if before.get(p) != after.get(p)} - expected
    if unexpected:
        raise ValueError('Unexpected host change: ' + ', '.join(sorted(unexpected)[:5]))
    for path, data in replacements.items():
        if after.get(path, {}).get('sha256') != digest(data):
            raise ValueError(f'Addon mismatch: {path}')
    for path in removals:
        if path in after:
            raise ValueError(f'Entry was not removed: {path}')
    archive = Archive(staged / 'Contents/Resources/app.asar')
    index = archive.read(ENTRY).decode()
    if index.count(MARKER) != (1 if present else 0) or (present and index.count(INSERT) != 1):
        raise ValueError('Missing, duplicate, or leftover addon entry')
    if present != has_assets(archive):
        raise ValueError('Addon asset directory does not match the intended state')
    with (staged / 'Contents/Info.plist').open('rb') as stream:
        plist = plistlib.load(stream)
    if plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] != digest(archive.header_bytes):
        raise ValueError('Electron ASAR integrity mismatch')
    verify_signed(staged)
    return after


def prepare(app, staged, mode, receipt):
    config = signing.resolve(app, STATE)
    archive = verify_host(app) if mode != 'remove' else Archive(app / 'Contents/Resources/app.asar')
    replacements, removals = plan(archive, mode, receipt)
    before = entries(app)
    if staged.exists():
        raise ValueError(f'Staging path exists: {staged}')
    staged.parent.mkdir(parents=True, exist_ok=True)
    run('ditto', str(app), str(staged))
    archive_path = staged / 'Contents/Resources/app.asar'
    rewritten = archive_path.with_suffix('.asar.new')
    header_hash = archive.rewrite(rewritten, replacements, removals)
    os.replace(rewritten, archive_path)
    info = staged / 'Contents/Info.plist'
    with info.open('rb') as stream:
        plist = plistlib.load(stream)
    plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
    with info.open('wb') as stream:
        plistlib.dump(plist, stream)
    signature = signing.sign(staged, config, STATE)
    after = validate_prepared(before, staged, replacements, removals, present=mode != 'remove')
    return config, signature, replacements, removals, before, after


def checked_receipt(app):
    receipt = json.loads(RECEIPT.read_text())
    if receipt['app'] != str(app):
        raise ValueError('Receipt belongs to a different installation.')
    check_owned(Archive(app / 'Contents/Resources/app.asar'), receipt)
    verify_signed(app)
    return receipt


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'setup-signing', 'apply', 'update', 'remove', 'recover', 'forget'])
    parser.add_argument('--app', type=Path, default=Path('/Applications/T3 Code (Beta).app'))
    args = parser.parse_args()
    app = args.app.resolve()
    project = ROOT.parents[1] if ROOT.parent.name == 'addons' and (ROOT.parents[1] / 'AGENTS.md').exists() else ROOT
    for local in (STATE, app):
        if local.resolve() == project or project in local.resolve().parents:
            raise ValueError('Application bundles, staging, and installation state must stay outside the project.')
    STATE.mkdir(parents=True, exist_ok=True)
    # One application mutation at a time across every addon installer.
    with (STATE_ROOT / 'app-mutation.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('Another T3 Adds installer is changing the application. Try again when it finishes.')
        if args.action in ('apply', 'update'):
            # Validate host state before installing the independent helper.
            verify_signed(app)
            verify_host(app)
            subprocess.run([sys.executable, str(ROOT / 'scripts/service.py'), 'install'], check=True)
        execute(args, app)
        if args.action == 'remove':
            subprocess.run([sys.executable, str(ROOT / 'scripts/service.py'), 'remove'], check=True)
        elif args.action == 'check' and RECEIPT.exists():
            subprocess.run([sys.executable, str(ROOT / 'scripts/service.py'), 'check'], check=True)


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
        verify_signed(app)
        if RECEIPT.exists():
            checked_receipt(app)
            print(f'{ADDON["name"]} installed; entry, files, signature, and receipt verified.')
        else:
            verify_host(app)
            print(f'Compatible T3 installation verified; {ADDON["name"]} is not installed.')
        return
    if args.action == 'forget':
        if not RECEIPT.exists():
            raise ValueError('No installation receipt to archive.')
        archive = Archive(app / 'Contents/Resources/app.asar')
        if MARKER in archive.read(ENTRY).decode() or has_assets(archive):
            raise ValueError('The addon is still present in the application; use remove instead.')
        write_json(STATE / 'transactions' / (uuid.uuid4().hex + '-forgotten-receipt.json'), json.loads(RECEIPT.read_text()))
        RECEIPT.unlink()
        print('Archived a stale receipt: the addon is no longer in the installed application.')
        return
    verify_signed(app)
    mode = {'apply': 'install', 'update': 'update', 'remove': 'remove'}[args.action]
    if mode == 'install' and RECEIPT.exists():
        raise ValueError('An installation receipt exists. Check, update, or remove it first.')
    receipt = checked_receipt(app) if mode != 'install' else None
    staged = STATE / '.cache/staged' / uuid.uuid4().hex / app.name
    try:
        config, signature, replacements, removals, before, after = prepare(app, staged, mode, receipt)

        def validator(path):
            validate_prepared(before, path, replacements, removals, present=mode != 'remove')
            signing.verify(path, config)

        host = identity(app)
        next_receipt = None
        if mode != 'remove':
            next_receipt = dict(schemaVersion=3, kind='overlay', app=str(app), addon=ADDON, host=host,
                                sources=source_record(), insert=INSERT,
                                hostDiscovery=discover(Archive(app / 'Contents/Resources/app.asar')),
                                ownedEntries={path: digest(data) for path, data in replacements.items()
                                              if path.startswith(ASSETS)},
                                installedAsarHash=digest((staged / 'Contents/Resources/app.asar').read_bytes()),
                                signing=signature,
                                verification={'hostCompatibility': 'passed', 'preparedSignature': 'passed',
                                              'asarIntegrity': 'passed', 'onlyPlannedEntriesChanged': 'passed',
                                              'persistentSigningRequirements': 'passed'},
                                archiveChanges=changes(before, after))
        record = transaction.start(app, staged, RECEIPT, next_receipt,
                                   dict(action=args.action, host=host, sources=source_record(),
                                        archiveChanges=changes(before, after)))
        if next_receipt is not None:
            next_receipt['previous'] = str(Path(record['previous']).relative_to(STATE))
            record['receiptAfter'] = next_receipt
            write_json(transaction.pending, record)
        transaction.execute(validator)
    finally:
        if not transaction.pending.exists():
            shutil.rmtree(staged.parent, ignore_errors=True)
    verbs = {'install': 'installed', 'update': 'updated', 'remove': 'removed'}
    print(f'{ADDON["name"]} {verbs[mode]} and verified. Other addons and official files were not touched.')
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
