#!/usr/bin/env python3
"""Install or withdraw the independent, journaled macOS negotiation helper."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import uuid
import urllib.request

sys.dont_write_bytecode = True
from lifecycle import write_json
import bridge

LABEL = 'com.t3adds.codex-dictation'
STATE = Path(os.environ.get('T3_ADDS_STATE_DIR', Path.home() / 'Library/Application Support/T3 Adds')).expanduser() / 'codex-dictation'
RECEIPT = STATE / 'service.json'
PENDING = STATE / 'service-pending.json'
RUNTIME = STATE / 'runtime'
PLIST = Path.home() / 'Library/LaunchAgents' / (LABEL + '.plist')


def fingerprint(path):
    if path.is_symlink():
        return {'kind': 'link', 'target': os.readlink(path), 'mode': stat.S_IMODE(path.lstat().st_mode)}
    if not path.exists():
        return None
    return {'kind': 'file', 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'mode': stat.S_IMODE(path.stat().st_mode)}


def launch(action):
    if action == 'stop':
        result = subprocess.run(['launchctl', 'bootout', 'gui/' + str(os.getuid()), str(PLIST)], capture_output=True)
        # A missing/stopped service has nothing to withdraw.
        if result.returncode and result.returncode not in (3, 5, 36, 113):
            raise ValueError('Could not stop the dictation helper.')
    else:
        subprocess.run(['launchctl', 'bootstrap', 'gui/' + str(os.getuid()), str(PLIST)], capture_output=True, check=True)


def health():
    request = urllib.request.Request('http://127.0.0.1:48173/health', data=b'{}',
                                    headers={'Origin': 't3code://app', 'Content-Type': 'application/json', 'X-T3-Dictation': '1'})
    return json.load(urllib.request.urlopen(request, timeout=5))


def owned(receipt):
    for name, expected in receipt['files'].items():
        if fingerprint(Path(name)) != expected:
            raise ValueError('A helper file changed unexpectedly; refusing to overwrite or remove it: ' + name)


def recover():
    if not PENDING.exists():
        print('No unfinished helper operation.'); return
    record = json.loads(PENDING.read_text())
    for name, item in record['files'].items():
        if fingerprint(Path(name)) not in (item['before'], item['after']):
            raise ValueError('Helper recovery found an unexpected file: ' + name)
        if item['before'] and fingerprint(Path(item['backup'])) != item['before']:
            raise ValueError('Helper recovery copy changed unexpectedly; no files restored.')
    launch('stop')
    for name, item in record['files'].items():
        path = Path(name)
        if item['before'] is None:
            path.unlink(missing_ok=True)
        else:
            shutil.copy2(item['backup'], path, follow_symlinks=False)
    if record['receiptBefore']:
        write_json(RECEIPT, record['receiptBefore']); launch('start')
    else:
        RECEIPT.unlink(missing_ok=True)
    record['status'] = 'rolled-back'
    write_json(STATE / 'service-transactions' / (record['id'] + '.json'), record)
    PENDING.unlink()
    print('Recovered the previous helper installation.')


def manage(action):
    if action == 'recover':
        return recover()
    if PENDING.exists():
        raise ValueError('An unfinished helper operation exists. Run scripts/service.py recover first.')
    previous = json.loads(RECEIPT.read_text()) if RECEIPT.exists() else None
    if previous:
        owned(previous)
    if action == 'check':
        if not previous:
            raise ValueError('Dictation helper is not installed. Run scripts/service.py install.')
        if health() != {'addon': 'codex-dictation', 'version': '0.1.0'}:
            raise ValueError('Unexpected helper response.')
        print('Dictation helper files and loopback health verified.'); return
    if action == 'remove' and not previous:
        print('Dictation helper is already absent.'); return
    if action == 'install':
        codex = shutil.which('codex')
        if not codex:
            raise ValueError('Codex CLI is not on PATH.')
        try:
            version = bridge.probe(codex)
        except bridge.ProtocolError as error:
            raise ValueError('Unsupported Codex CLI: ' + str(error))
        config = {'Label': LABEL, 'ProgramArguments': [sys.executable, str(RUNTIME / 'bridge.py'), '--codex', codex],
                  'RunAtLoad': True, 'KeepAlive': True, 'WorkingDirectory': str(RUNTIME),
                  'ProcessType': 'Background', 'EnvironmentVariables': {'PYTHONDONTWRITEBYTECODE': '1', 'PATH': os.environ.get('PATH', os.defpath)},
                  'StandardOutPath': '/dev/null', 'StandardErrorPath': '/dev/null'}
        contents = {str(RUNTIME / 'bridge.py'): Path(__file__).with_name('bridge.py').read_bytes(),
                    str(PLIST): plistlib.dumps(config)}
        if previous and all(fingerprint(Path(n)) == {'kind': 'file', 'sha256': hashlib.sha256(b).hexdigest(), 'mode': 0o600}
                            for n, b in contents.items()):
            manage('check'); return
    else:
        contents = {name: None for name in previous['files']}
    operation = uuid.uuid4().hex
    backup = STATE / 'service-backups' / operation
    backup.mkdir(parents=True)
    files = {}
    for index, (name, data) in enumerate(contents.items()):
        path = Path(name)
        before = fingerprint(path)
        if before is not None and not previous:
            raise ValueError('Unrecorded helper file exists; refusing replacement: ' + name)
        if before and before['kind'] != 'file':
            raise ValueError('Helper paths must be regular files.')
        saved = backup / str(index)
        if before:
            shutil.copy2(path, saved)
        files[name] = {'before': before, 'after': None if data is None else
                       {'kind': 'file', 'sha256': hashlib.sha256(data).hexdigest(), 'mode': 0o600},
                       'backup': str(saved) if before else None}
    record = {'schemaVersion': 1, 'id': operation, 'action': action, 'status': 'planned', 'files': files,
              'receiptBefore': previous, 'verification': {}}
    write_json(PENDING, record)
    try:
        if previous:
            launch('stop')
        for name, data in contents.items():
            path = Path(name)
            if fingerprint(path) != files[name]['before']:
                raise ValueError('Helper changed during installation.')
            if data is None:
                path.unlink()
            else:
                path.parent.mkdir(parents=True, exist_ok=True)
                temp = path.with_suffix('.new')
                with temp.open('wb') as stream:
                    os.fchmod(stream.fileno(), 0o600); stream.write(data); stream.flush(); os.fsync(stream.fileno())
                os.replace(temp, path)
        if action == 'install':
            launch('start')
            # launchd starts asynchronously; use short bounded retries only during installation.
            import time
            for attempt in range(20):
                try:
                    health(); break
                except OSError:
                    if attempt == 19:
                        raise
                    time.sleep(0.25)
            receipt = {'schemaVersion': 1, 'addon': 'codex-dictation', 'version': '0.1.0', 'codexVersion': version,
                       'transaction': operation, 'files': {name: item['after'] for name, item in files.items()}}
            owned(receipt); write_json(RECEIPT, receipt)
        else:
            RECEIPT.unlink()
        record['status'] = 'completed'
        record['verification'] = {'fileHashesAndModes': 'passed', 'launchd': 'passed', 'loopbackHealth': 'passed' if action == 'install' else 'not-applicable'}
        write_json(STATE / 'service-transactions' / (operation + '.json'), record)
        PENDING.unlink()
    except BaseException:
        recover()
        raise
    print('Dictation helper ' + ('installed' if action == 'install' else 'removed') + ' with external recovery records.')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['install', 'check', 'remove', 'recover'])
    args = parser.parse_args()
    addon = Path(__file__).resolve().parents[1]
    project = addon.parents[1] if addon.parent.name == 'addons' and (addon.parents[1] / 'AGENTS.md').exists() else addon
    if STATE.resolve() == project or project in STATE.resolve().parents:
        raise ValueError('Helper runtime, receipts, and recovery copies must stay outside the source project.')
    STATE.mkdir(parents=True, exist_ok=True)
    with (STATE / 'service.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manage(args.action)


if __name__ == '__main__':
    try:
        main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print('Helper operation stopped: ' + str(error), file=sys.stderr)
        sys.exit(1)
