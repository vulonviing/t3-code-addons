"""Durable, content-checked application swaps. No host or addon imports."""
import hashlib
from datetime import datetime, timezone
import json
import os
import stat
import uuid
from pathlib import Path


def inventory(root):
    root = Path(root)
    result = {}
    for path in [root, *sorted(root.rglob('*'))]:
        info = path.lstat()
        item = {'mode': stat.S_IMODE(info.st_mode)}
        if path.is_symlink():
            item.update(kind='link', target=os.readlink(path))
        elif path.is_file():
            h = hashlib.sha256()
            with path.open('rb') as stream:
                for block in iter(lambda: stream.read(1024 * 1024), b''):
                    h.update(block)
            item.update(kind='file', sha256=h.hexdigest(), size=info.st_size)
        elif path.is_dir():
            item['kind'] = 'directory'
        else:
            raise ValueError('Unsupported bundle entry type')
        result[path.relative_to(root).as_posix()] = item
    return result


def changes(before, after):
    return [dict(path=p, before=before.get(p), after=after.get(p))
            for p in sorted(before.keys() | after.keys()) if before.get(p) != after.get(p)]


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    with temporary.open('w') as stream:
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)
    descriptor = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def move(source, target):
    os.rename(source, target)
    for parent in {Path(source).parent, Path(target).parent}:
        descriptor = os.open(parent, os.O_RDONLY)
        try:
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


class Transaction:
    """Write intent before renames; explicit recovery finishes only known states."""

    def __init__(self, state):
        self.state = Path(state)
        self.pending = self.state / 'transactions/pending.json'

    def require_idle(self):
        if self.pending.exists():
            raise ValueError('An unfinished transaction exists. Run recover before another operation.')

    def start(self, app, candidate, receipt_path, receipt_after, metadata):
        self.require_idle()
        app, candidate, receipt_path = map(Path, (app, candidate, receipt_path))
        if not app.is_dir() or not candidate.is_dir():
            raise ValueError('Application and prepared candidate must both exist.')
        if app == candidate or app in candidate.parents or candidate in app.parents:
            raise ValueError('Application and candidate must be separate bundles.')
        self.state.mkdir(parents=True, exist_ok=True)
        if len({p.stat().st_dev for p in (app.parent, candidate.parent, self.state)}) != 1:
            raise ValueError('Atomic application swaps require staging and state on the application volume.')
        before, after = inventory(app), inventory(candidate)
        operation = uuid.uuid4().hex
        previous = self.state / 'backups' / operation / app.name
        previous.parent.mkdir(parents=True)
        record = dict(schemaVersion=1, id=operation, status='prepared', app=str(app),
                      startedAt=datetime.now(timezone.utc).isoformat(),
                      candidate=str(candidate), previous=str(previous),
                      receiptPath=str(receipt_path),
                      receiptBefore=json.loads(receipt_path.read_text()) if receipt_path.exists() else None,
                      receiptAfter=receipt_after, before=before, after=after,
                      changes=changes(before, after), metadata=metadata)
        write_json(self.pending, record)
        return record

    def _finish(self, record, status):
        record['status'] = status
        record['finishedAt'] = datetime.now(timezone.utc).isoformat()
        write_json(self.state / 'transactions' / (record['id'] + '.json'), record)
        self.pending.unlink()

    def execute(self, validate):
        record = json.loads(self.pending.read_text())
        app, candidate, previous = (Path(record[k]) for k in ('app', 'candidate', 'previous'))
        if inventory(app) != record['before'] or inventory(candidate) != record['after']:
            raise ValueError('Application or candidate changed after preparation; no files replaced.')
        move(app, previous)
        record['status'] = 'original-moved'
        write_json(self.pending, record)
        move(candidate, app)
        record['status'] = 'candidate-installed'
        write_json(self.pending, record)
        try:
            validate(app)
            if inventory(app) != record['after']:
                raise ValueError('Installed bundle changed during verification.')
        except BaseException:
            # Preserve both copies. A crash here is recoverable from their inventories.
            move(app, candidate)
            move(previous, app)
            self._finish(record, 'rolled-back')
            raise
        self._commit_receipt(record)
        record['verification'] = {'installedInventory': 'passed', 'validator': 'passed'}
        self._finish(record, 'committed')
        return record

    def _commit_receipt(self, record):
        path = Path(record['receiptPath'])
        current = json.loads(path.read_text()) if path.exists() else None
        if current not in (record['receiptBefore'], record['receiptAfter']):
            raise ValueError('Installation receipt changed; refusing to overwrite it.')
        if record['receiptAfter'] is None:
            if path.exists():
                write_json(self.state / 'transactions' / (record['id'] + '-receipt.json'), current)
                path.unlink()
        else:
            write_json(path, record['receiptAfter'])

    def recover(self, validate):
        if not self.pending.exists():
            return 'No unfinished transaction.'
        record = json.loads(self.pending.read_text())
        app, candidate, previous = (Path(record[k]) for k in ('app', 'candidate', 'previous'))
        if not app.exists():
            if not previous.exists() or inventory(previous) != record['before']:
                raise ValueError('Recovery backup is missing or changed; manual inspection required.')
            move(previous, app)
            self._finish(record, 'rolled-back')
            return 'Original application restored; prepared candidate retained.'
        current = inventory(app)
        if current == record['before']:
            self._finish(record, 'rolled-back')
            return 'Original application retained; no installation committed.'
        if current != record['after'] or not previous.exists() or inventory(previous) != record['before']:
            raise ValueError('Recovery found unexpected application contents; no files replaced.')
        validate(app)
        self._commit_receipt(record)
        record['verification'] = {'installedInventory': 'passed', 'validator': 'passed', 'recovered': True}
        self._finish(record, 'committed')
        return 'Verified installation and receipt recovered.'
