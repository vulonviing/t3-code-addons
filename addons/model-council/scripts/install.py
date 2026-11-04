#!/usr/bin/env python3
"""Build, verify and reversibly inject the pinned Model Council addon."""
import argparse
import datetime
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest

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


def prepare(app, staged):
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
    # Apple-issued identity/keychain entitlements cannot be used by an ad-hoc signature.
    raw = subprocess.check_output(['codesign', '-d', '--entitlements', ':-', str(app)], stderr=subprocess.DEVNULL)
    entitlements = plistlib.loads(raw)
    for key in list(entitlements):
        if key.startswith('com.apple.developer.') or key in ['com.apple.application-identifier', 'keychain-access-groups']:
            del entitlements[key]
    entitlement_file = staged.parent / 'local-entitlements.plist'
    entitlement_file.write_bytes(plistlib.dumps(entitlements))
    run('codesign', '--force', '--deep', '--sign', '-', '--options', 'runtime', '--entitlements', str(entitlement_file), str(staged))
    validate_prepared(staged)
    return staged


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['check', 'stage', 'apply', 'update', 'restore'])
    parser.add_argument('--app', type=Path, default=Path('/Applications/T3 Code (Beta).app'))
    parser.add_argument('--staged', type=Path, default=STATE / '.cache/staged/T3 Code (Beta).app')
    args = parser.parse_args()
    app = args.app.resolve()
    if args.action == 'check':
        archive = Archive(app / 'Contents/Resources/app.asar')
        if MARKER in archive.read(ENTRY).decode():
            validate_prepared(app)
            print('Model Council installed; bundle contents and signature verified.')
        else:
            verify_original(app)
            print('T3 0.1.6 / 2359643cffa6: compatible original installation.')
        return
    if args.action == 'stage':
        print(prepare(app, args.staged))
        return
    if args.action == 'update':
        receipt = json.loads(RECEIPT.read_text())
        if receipt['app'] != str(app):
            raise ValueError('Receipt belongs to a different installation.')
        if digest((app / 'Contents/Resources/app.asar').read_bytes()) != receipt['installedAsarHash']:
            raise ValueError('Installation changed since injection; refusing to overwrite an update.')
        original = backup_path(receipt['backup'])
        verify_original(original)
        run('codesign', '--verify', '--deep', '--strict', str(app))
        staged = prepare(original, args.staged)
        stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        previous = STATE / 'backups' / stamp / app.name
        previous.parent.mkdir(parents=True)
        os.rename(app, previous)
        try:
            os.rename(staged, app)
            validate_prepared(app)
        except BaseException:
            if app.exists():
                os.rename(app, staged)
            os.rename(previous, app)
            raise
        receipt.setdefault('updates', []).append({'at': stamp, 'previous': str(previous.relative_to(STATE))})
        receipt['installedAsarHash'] = digest((app / 'Contents/Resources/app.asar').read_bytes())
        pending = RECEIPT.with_suffix('.pending.json')
        pending.write_text(json.dumps(receipt, indent=2) + '\n')
        os.replace(pending, RECEIPT)
        print('Model Council updated. Original backup retained. Restart T3 to load it.')
        return
    if args.action == 'restore':
        receipt = json.loads(RECEIPT.read_text())
        if receipt['app'] != str(app):
            raise ValueError('Receipt belongs to a different installation.')
        backup = backup_path(receipt['backup'])
        verify_original(backup)
        if digest((app / 'Contents/Resources/app.asar').read_bytes()) != receipt['installedAsarHash']:
            raise ValueError('Installation changed since injection; refusing to overwrite an update.')
        run('codesign', '--verify', '--deep', '--strict', str(backup))
        removed = backup.parent / ('removed-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.app')
        os.rename(app, removed)
        try:
            os.rename(backup, app)
        except BaseException:
            os.rename(removed, app)
            raise
        RECEIPT.rename(RECEIPT.with_suffix('.restored.json'))
        print(f'Original installation restored. Removed addon bundle kept at {removed}')
        return
    if RECEIPT.exists():
        raise ValueError('An installation receipt exists. Check or restore it before applying again.')
    verify_original(app)
    staged = args.staged
    if not staged.exists():
        prepare(app, staged)
    validate_prepared(staged)
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup = STATE / 'backups' / stamp / app.name
    backup.parent.mkdir(parents=True)
    receipt = {
        'app': str(app), 'backup': str(backup.relative_to(STATE)), 'installedAt': stamp,
        'installedAsarHash': digest((staged / 'Contents/Resources/app.asar').read_bytes()),
        'originalAsarHash': digest((app / 'Contents/Resources/app.asar').read_bytes()),
    }
    pending = RECEIPT.with_suffix('.pending.json')
    pending.write_text(json.dumps(receipt, indent=2) + '\n')
    os.rename(app, backup)
    try:
        os.rename(staged, app)
        validate_prepared(app)
    except BaseException:
        if app.exists():
            os.rename(app, staged)
        os.rename(backup, app)
        pending.unlink(missing_ok=True)
        raise
    os.replace(pending, RECEIPT)
    print(f'Model Council injected. Original app backup: {backup}')
    print('Restart T3 Code to load the addon. The running app was not stopped.')


if __name__ == '__main__':
    main()
