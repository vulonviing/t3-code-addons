#!/usr/bin/env python3
"""Unplug every T3 Adds addon, update T3 Code, plug the addons back in, and report what attached.

    python3 update_all.py [--candidate PATH] [--app APP] [--addons DIR] [--no-restart] [--drop ID]

Steps: withdraw every installed addon with its own installer (overlays first, Model Council restore last),
install the official update when --candidate (an extracted .app or a .zip) is given, apply every addon again
with its own installer, run each addon's check, print one table, and restart T3 once through a detached job.

Compatibility means "does the addon attach?". A failed addon is reported and left withdrawn; the others
continue and the run still finishes. The wanted-addon list lives in the external state root, so an
interrupted or partly failed run is repaired by running the same command again. CLI updates (Codex, Claude
Code, Open Code) never involve this tool. Standard library only; all paths are resolved at runtime.
"""
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
import time
from pathlib import Path

sys.dont_write_bytecode = True
DEFAULT_APP = '/Applications/T3 Code (Beta).app'
TIMEOUT = 900


def state_root():
    return Path(os.environ.get('T3_ADDS_STATE_DIR', Path.home() / 'Library/Application Support/T3 Adds')).expanduser()


def default_addons_dir():
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / 'addons').is_dir():
            return parent / 'addons'
    return Path.cwd() / 'addons'


class Addon:
    def __init__(self, directory, root):
        self.dir = directory
        self.id = json.loads((directory / 'addon.json').read_text())['id']
        self.script = directory / 'scripts/install.py'
        source = self.script.read_text()
        self.bundle = "'restore'" in source  # whole-bundle addon: restore withdraws it
        state = root / self.id
        self.receipt = state / ('backups/model-council-install.json' if self.bundle else 'installation.json')
        if self.bundle and not self.receipt.parent.exists() and (state / 'installation.json').exists():
            self.receipt = state / 'installation.json'
        self.state = state

    def installed(self):
        return self.receipt.exists()

    def run(self, action, app, *extra):
        result = subprocess.run([sys.executable, '-B', str(self.script), action, '--app', str(app), *extra],
                                cwd=self.dir, capture_output=True, text=True, timeout=TIMEOUT)
        return result.returncode == 0, short((result.stderr or result.stdout))


def short(text, limit=160):
    lines = [line.strip() for line in (text or '').strip().splitlines() if line.strip()]
    line = lines[-1] if lines else 'no output'
    line = re.sub(r'^Installation stopped:\s*', '', line)
    return line[:limit]


def discover(addons_dir, root):
    found = []
    for directory in sorted(Path(addons_dir).iterdir()) if Path(addons_dir).is_dir() else []:
        if (directory / 'addon.json').exists() and (directory / 'scripts/install.py').exists():
            found.append(Addon(directory, root))
    return found


def read_json(path, default):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix='.tmp-')
    with os.fdopen(fd, 'w') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def ensure_signing(addon, addons, app):
    """Make persistent signing exist without a prompt: reuse a sibling's identity, else run setup-signing once."""
    target = addon.state / 'signing/identity.json'
    if target.exists():
        return True, ''
    for other in addons:
        source = other.state / 'signing/identity.json'
        if other is not addon and source.exists():
            target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            shutil.copyfile(source, target)
            target.chmod(0o600)
            certificate = other.state / 'signing/certificate.pem'
            if certificate.exists():
                shutil.copyfile(certificate, target.parent / 'certificate.pem')
            return True, 'reused signing identity'
    ok, message = addon.run('setup-signing', app)
    return ok, ('' if ok else 'signing setup failed: ' + message)


def asar_hash(app):
    import hashlib
    path = Path(app) / 'Contents/Resources/app.asar'
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def withdraw(addon, app, root):
    """Return (ok, note). A stale receipt of an app that an official update already replaced is archived."""
    if not addon.installed():
        return True, 'not installed'
    ok, message = addon.run('remove' if not addon.bundle else 'restore', app)
    if not ok:
        addon.run('recover', app)
        ok, message = addon.run('remove' if not addon.bundle else 'restore', app)
    if ok:
        return True, 'withdrawn'
    if not addon.bundle:
        ok, forget = addon.run('forget', app)
        if ok:
            return True, 'stale receipt archived'
    else:
        receipt = read_json(addon.receipt, {})
        recorded = receipt.get('installedAsarHash')
        current = asar_hash(app)
        if recorded and current and recorded != current:
            archive = root / 'lifecycle/archived-receipts'
            archive.mkdir(parents=True, exist_ok=True)
            shutil.move(str(addon.receipt), str(archive / f'{addon.id}-{int(time.time())}.json'))
            return True, 'stale receipt archived'
    return False, message


def attach(addon, app, addons, root):
    """Apply and check one addon; on failure recover, withdraw, and try once more. Leaves a failure withdrawn."""
    note = ''
    for attempt in (1, 2):
        ok = True
        if not addon.installed():
            ok, note = ensure_signing(addon, addons, app)
            if ok:
                ok, note = addon.run('apply', app)
        if ok:
            ok, note = addon.run('check', app)
            note = '' if ok else 'check: ' + note
        if ok:
            return True, ''
        addon.run('recover', app)
        if addon.installed():
            withdraw(addon, app, root)
    return False, note


def prepare_candidate(candidate, root):
    """Return (application, staging dir to clean up or None)."""
    candidate = Path(candidate)
    if candidate.suffix != '.zip':
        return candidate, None
    staging = root / 'lifecycle/staging' / f'{int(time.time() * 1000)}'
    staging.mkdir(parents=True)
    try:
        subprocess.run(['/usr/bin/ditto', '-x', '-k', str(candidate), str(staging)], check=True, timeout=TIMEOUT)
        apps = sorted(staging.glob('*.app'))
        if len(apps) != 1:
            raise ValueError('The archive must contain exactly one application.')
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    return apps[0], staging


def install_official(addons, app, candidate, root):
    """Use the official-update installer that ships with the bundle addon (it verifies signature and identity)."""
    installer = next((a for a in addons if a.bundle), None)
    if installer is None:
        return False, 'no installer available for an official update; update T3 yourself and run again'
    try:
        staged, staging = prepare_candidate(candidate, root)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        return False, short(str(error))
    try:
        return installer.run('install-official', app, '--candidate', str(staged))
    finally:
        if staging is not None:
            shutil.rmtree(staging, ignore_errors=True)


def restart(app):
    """Quit and reopen T3 once, from a detached job that outlives this process (and T3 itself)."""
    bundle = None
    try:
        bundle = plistlib.loads((Path(app) / 'Contents/Info.plist').read_bytes()).get('CFBundleIdentifier')
    except (OSError, ValueError):
        pass
    quit_cmd = f"/usr/bin/osascript -e 'tell application id \"{bundle}\" to quit'; " if bundle else ''
    script = f"sleep 3; {quit_cmd}sleep 4; /usr/bin/open {shell_quote(str(app))}"
    subprocess.Popen(['/bin/sh', '-c', script], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                     stderr=subprocess.DEVNULL, start_new_session=True)


def shell_quote(value):
    return "'" + value.replace("'", "'\\''") + "'"


def run(args, restarter=restart, out=print, publisher=None):
    root = state_root()
    app = Path(args.app).expanduser()
    addons = discover(args.addons or default_addons_dir(), root)
    by_id = {a.id: a for a in addons}
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'update-all.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            out('Another update-all run is active.')
            return 2
        return _run(args, app, addons, by_id, root, restarter, out, publisher)


def _run(args, app, addons, by_id, root, restarter, out, publisher):
    journal_path = root / 'lifecycle/wanted.json'
    journal = read_json(journal_path, {'wanted': [], 'updated': None})
    if args.drop:
        journal['wanted'] = [i for i in journal['wanted'] if i != args.drop]
        write_json(journal_path, journal)
    # The saved list holds only addons this tool still owes an attach (failed or interrupted). An addon the
    # user withdrew by hand after a completed run is not in it, so it is not silently re-applied.
    wanted = [i for i in journal['wanted'] if i in by_id]
    for addon in addons:
        if addon.installed() and addon.id not in wanted:
            wanted.append(addon.id)
    journal['wanted'] = wanted
    write_json(journal_path, journal)  # durable before any change: an interruption cannot lose the set

    rows = {i: ['', ''] for i in wanted}
    # 1. Unplug: overlays first, whole-bundle addons last.
    stuck = []
    for addon in sorted((by_id[i] for i in wanted), key=lambda a: a.bundle):
        ok, note = withdraw(addon, app, root)
        if not ok:
            rows[addon.id] = ['failed', 'could not withdraw (still installed): ' + note]
            stuck.append(addon.id)
    # 2. Update T3 (only if asked, and only when nothing blocks it).
    update_note = 'not requested'
    if args.candidate and Path(args.candidate).exists():
        if stuck:
            update_note = ('NOT installed: could not withdraw ' + ', '.join(stuck) + '. Fix or remove it with its own '
                           'install.py (remove/restore, then recover), then run again.')
        else:
            ok, message = install_official(addons, app, args.candidate, root)
            update_note = 'T3 updated' if ok else 'update failed: ' + message
            if ok:
                journal['updated'] = str(args.candidate)
                write_json(journal_path, journal)
    elif args.candidate:
        update_note = 'candidate not found (already consumed by an earlier run?)'
    # 3. Plug back in: bundle addons first (they need the clean original), then overlays. Each addon heals once.
    changed = False
    todo = [by_id[i] for i in wanted if i not in stuck]
    for addon in sorted(todo, key=lambda a: not a.bundle):
        was_installed = addon.installed()
        ok, note = attach(addon, app, addons, root)
        changed = changed or not was_installed
        rows[addon.id] = ['attached', ''] if ok else ['failed', note]
    # 4. The table comes from real checks run after everything is plugged in; one more heal if a late check fails.
    for addon in sorted(todo, key=lambda a: not a.bundle):
        if rows[addon.id][0] != 'attached':
            continue
        ok, note = addon.run('check', app) if addon.installed() else (False, 'not installed')
        if not ok:
            withdraw(addon, app, root)
            ok, note = attach(addon, app, addons, root)
            changed = True
        rows[addon.id] = ['attached', ''] if ok else ['failed', note]
    # Wanted list keeps every failed addon so the next run retries it; attached ones stay wanted too.
    out(f'T3 update: {update_note}')
    width = max([len(i) for i in rows] + [5])
    for addon_id, (status, reason) in rows.items():
        out(f'  {addon_id.ljust(width)}  {status}{"  " + reason if reason else ""}')
        if status != 'attached':
            out(f'  {" " * width}  next: cd "{by_id[addon_id].dir}" && python3 scripts/install.py apply --app "{app}"')
    failed = [i for i, row in rows.items() if row[0] != 'attached']
    withdrawn = [i for i in failed if i not in stuck]
    if withdrawn:
        out('Left withdrawn: ' + ', '.join(withdrawn) + '. Run again to retry, or --drop ID to stop wanting one.')
    if stuck:
        out('Left installed as is: ' + ', '.join(stuck) + '. Nothing was removed or lost.')
    if (changed or journal.get('updated')) and not args.no_restart:
        restarter(app)
        out('T3 will restart once in a few seconds.')
    journal['updated'] = None
    journal['wanted'] = failed  # only what is still owed; attached addons are re-read from receipts next time
    write_json(journal_path, journal)
    if not failed and not args.no_publish:
        publish_step(publisher, out)
    return 1 if failed else 0


def publish_step(publisher, out):
    """Publish only when the working tree is dirty. Any problem is reported and never fails the update."""
    try:
        if publisher is None:
            import publish
            publisher = publish.run_publish
        message = publisher()
        if message:
            out(message)
    except Exception as error:  # reporting only
        out('Publish skipped: ' + short(str(error)))


def build_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--candidate', type=Path, help='Extracted official .app or .zip to install as the T3 update')
    parser.add_argument('--app', type=Path, default=Path(DEFAULT_APP))
    parser.add_argument('--addons', type=Path, help='Directory holding the addon folders')
    parser.add_argument('--no-restart', action='store_true')
    parser.add_argument('--no-publish', action='store_true', help='Do not commit and push the result')
    parser.add_argument('--drop', metavar='ID', help='Stop re-applying this addon')
    return parser.parse_args(argv)


def main(argv=None):
    return run(build_args(argv))


if __name__ == '__main__':
    sys.exit(main())
