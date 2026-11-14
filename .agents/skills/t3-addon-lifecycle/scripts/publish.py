#!/usr/bin/env python3
"""Privacy-scan the repository, run addon tests, commit in logical groups on update-<date>, and push.

    python3 publish.py [--repo DIR] [--footer LINE] [--skip-tests] [--dry-run]

Never force-pushes, never rewrites history, never creates a repository or a remote. Any scan finding, test
failure, missing remote, or push failure stops the publish with a clear message and a non-zero exit code.
The commit footer comes from --footer or the T3_ADDS_COMMIT_FOOTER environment variable. Standard library only.
"""
import argparse
import datetime
import getpass
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
MAX_BYTES = 2_000_000
PUSH_TIMEOUT = 60
PLACEHOLDER_USERS = {'name', 'user', 'username', 'you', 'me', 'example', 'someone', 'shared', 'runner'}
SAFE_EMAIL = re.compile(r'(@example\.(com|org)$|^noreply@|@users\.noreply\.github\.com$|@localhost$)', re.I)
_pk = '-----BEGIN ' + r'[A-Z ]*' + 'PRIVATE KEY' + '-----'
PATTERNS = [
    ('token', re.compile(r'\b(gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|sk-[A-Za-z0-9_-]{20,}'
                         r'|AKIA[0-9A-Z]{16}|xox[abprs]-[A-Za-z0-9-]{10,}|AIza[0-9A-Za-z_-]{30,})\b')),
    ('private-key', re.compile(_pk)),
    ('credential', re.compile(r'(?i)\b(api[_-]?key|secret|token|passw(or)?d|credential)s?\b\s*[:=]\s*["\'][^"\'\s]{12,}["\']')),
    ('cookie', re.compile(r'(?i)\b(set-)?cookie\s*[:=]\s*["\'][^"\']{16,}["\']')),
]
HOME = re.compile(r'(?<![\w.])(/Users|/home)/([A-Za-z0-9._-]+)')
EMAIL = re.compile(r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}')


def git(repo, *args, check=True, network=False):
    env, timeout = None, None
    if network:  # a credential prompt or a hung connection must never stall an update
        env = dict(os.environ, GIT_TERMINAL_PROMPT='0', GIT_ASKPASS=shutil.which('true') or '/usr/bin/true',
                   SSH_ASKPASS=shutil.which('true') or '/usr/bin/true')
        env.setdefault('GIT_SSH_COMMAND', 'ssh -o BatchMode=yes -o ConnectTimeout=20')
        timeout = PUSH_TIMEOUT
    try:
        result = subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, env=env, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise RuntimeError(f'git {args[0]} timed out after {PUSH_TIMEOUT}s')
    if check and result.returncode:
        detail = (result.stderr or result.stdout).strip().splitlines()
        raise RuntimeError(f'git {args[0]} failed' + (': ' + detail[-1] if detail else ''))
    return result.stdout


def repo_root(start):
    out = subprocess.run(['git', '-C', str(start), 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if out.returncode:
        raise RuntimeError('Not inside a git repository.')
    return Path(out.stdout.strip())


def local_identities(repo):
    names = set()
    for value in (getpass.getuser(), socket.gethostname().split('.')[0],
                  git(repo, 'config', 'user.email', check=False).strip(),
                  git(repo, 'config', 'user.name', check=False).strip()):
        if value and len(value) >= 4 and value.lower() not in ('root', 'localhost'):
            names.add(value)
    return names


def line_kinds(line, identities):
    """Kinds of sensitive content in one line. Never returns the matched text."""
    kinds = []
    for match in HOME.finditer(line):
        user = match.group(2)
        if user.lower() not in PLACEHOLDER_USERS and not user.startswith(('<', '$', '{')):
            kinds.append('personal-path')
    for match in EMAIL.finditer(line):
        if not SAFE_EMAIL.search(match.group(0)):
            kinds.append('email')
    kinds += [kind for kind, pattern in PATTERNS if pattern.search(line)]
    lowered = line.lower()
    if any(identity.lower() in lowered for identity in identities):
        kinds.append('local-identity')
    return kinds


def scannable(path):
    """File bytes if the scan can read them, else None (symlink, oversize, binary, unreadable)."""
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return None if b'\0' in data[:4096] else data


def scan(repo):
    """Return findings as (relative path, line number, kind). Matched text is never returned."""
    files = git(repo, 'ls-files', '-z', '--cached', '--others', '--exclude-standard').split('\0')
    identities = local_identities(repo)
    findings = []
    for name in filter(None, files):
        data = scannable(Path(repo) / name)
        if data is None:
            continue
        for number, line in enumerate(data.decode('utf-8', 'replace').splitlines(), 1):
            findings += [(name, number, kind) for kind in line_kinds(line, identities)]
    return sorted(set(findings))


def pending_paths(repo):
    return [path for paths in groups(repo).values() for path in paths]


def unscanned_pending(repo):
    """Pending paths the scan cannot read (symlink, binary, over 2 MB). Deletions are fine."""
    result = []
    for name in pending_paths(repo):
        path = Path(repo) / name
        if os.path.lexists(path) and scannable(path) is None and not path.is_dir():
            result.append(name)
    return sorted(set(result))


def base_ref(repo, remote):
    for ref in (f'refs/remotes/{remote}/HEAD', 'refs/heads/main', 'refs/heads/master',
                f'refs/remotes/{remote}/main', f'refs/remotes/{remote}/master'):
        if git(repo, 'rev-parse', '--verify', '--quiet', ref, check=False).strip():
            return ref
    return 'HEAD'


def scan_commits(repo, base, remote, branch):
    """Scan lines added by commits that would be pushed. Returns (commit, path, kind); no values."""
    pushed = f'refs/remotes/{remote}/{branch}'
    start = pushed if git(repo, 'rev-parse', '--verify', '--quiet', pushed, check=False).strip() else base
    if git(repo, 'rev-parse', '--verify', '--quiet', 'HEAD', check=False).strip() == '':
        return []
    log = git(repo, 'log', '-p', '--no-color', '--format=@@commit %h', '-U0', f'{start}..HEAD', check=False)
    identities = local_identities(repo)
    findings, commit, path = set(), '', ''
    for line in log.splitlines():
        if line.startswith('@@commit '):
            commit = line.split()[1]
        elif line.startswith('+++ '):
            path = line[6:] if line.startswith('+++ b/') else line[4:]
        elif line.startswith('+') and not line.startswith('+++'):
            findings.update((commit, path, kind) for kind in line_kinds(line[1:], identities))
    return sorted(findings)


def run_tests(repo):
    """Run each addon's Python tests that exist. Return a list of failure descriptions."""
    failures = []
    for addon in sorted((Path(repo) / 'addons').glob('*')) if (Path(repo) / 'addons').is_dir() else []:
        for test in sorted((addon / 'scripts').glob('test_*.py')) if (addon / 'scripts').is_dir() else []:
            try:
                result = subprocess.run([sys.executable, '-B', str(test)], cwd=addon, capture_output=True, text=True,
                                        timeout=300)
                if result.returncode:
                    failures.append(f'{addon.name}/{test.name}')
            except subprocess.TimeoutExpired:
                failures.append(f'{addon.name}/{test.name} (timeout)')
    return failures


def groups(repo):
    """Pending paths grouped for logical commits: one per addon, then the skill/docs, then anything else."""
    status = git(repo, 'status', '--porcelain', '-z', '--untracked-files=all').split('\0')
    paths = []
    iterator = iter(filter(None, status))
    for entry in iterator:
        code, path = entry[:2], entry[3:]
        paths.append(path)
        if code[0] in 'RC':  # porcelain -z lists the original path next; keep both so the rename commits whole
            paths.append(next(iterator, path))
    result = {}
    for path in paths:
        parts = path.split('/')
        if parts[0] == 'addons' and len(parts) > 2:
            key = ('addon', parts[1])
        elif parts[0] == '.agents':
            key = ('lifecycle', 'lifecycle tooling')
        else:
            key = ('docs', 'repository docs and config')
        result.setdefault(key, []).append(path)
    return result


def choose_remote(repo):
    remotes = git(repo, 'remote').split()
    if not remotes:
        raise RuntimeError('No git remote is configured. Add one yourself (git remote add origin URL); '
                           'this tool never creates a repository.')
    return 'origin' if 'origin' in remotes else remotes[0]


def run_publish(repo=None, footer=None, skip_tests=False, dry_run=False, today=None):
    """Return a short status message, or None when there is nothing to publish. Raises RuntimeError on a block."""
    repo = repo_root(repo or Path(__file__).resolve().parent)
    if not git(repo, 'status', '--porcelain').strip():
        return None
    findings = scan(repo)
    if findings:
        lines = [f'  {path}:{number} {kind}' for path, number, kind in findings[:20]]
        more = f'\n  ... and {len(findings) - 20} more' if len(findings) > 20 else ''
        raise RuntimeError(f'Privacy scan blocked publishing ({len(findings)} finding(s); values not shown):\n'
                           + '\n'.join(lines) + more)
    skipped = unscanned_pending(repo)
    if skipped:
        raise RuntimeError('Publishing refused: these pending paths cannot be privacy-scanned (symlink, binary, or '
                           'over 2 MB). Remove or ignore them, or commit them yourself:\n'
                           + '\n'.join('  ' + name for name in skipped))
    staged = set(filter(None, git(repo, 'diff', '--cached', '--name-only', '-z').split('\0')))
    partial = staged & set(filter(None, git(repo, 'diff', '--name-only', '-z').split('\0')))
    if partial:
        raise RuntimeError('Publishing stopped: staged and unstaged changes in the same file would be mixed up: '
                           + ', '.join(sorted(partial)) + '. Stage or unstage them yourself first.')
    if not skip_tests:
        failed = run_tests(repo)
        if failed:
            raise RuntimeError('Addon tests failed, not publishing: ' + ', '.join(failed))
    remote = choose_remote(repo)
    base = base_ref(repo, remote)
    branch = git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip()
    target = branch if branch.startswith('update-') else 'update-' + (today or datetime.date.today().isoformat())
    if target != branch and git(repo, 'rev-parse', '--verify', '--quiet', 'refs/heads/' + target, check=False).strip():
        raise RuntimeError(f'Branch {target} already exists but is not checked out. Switch to it yourself '
                           '(git switch ' + target + ') or delete it, then publish again.')
    already = scan_commits(repo, base, remote, target) if target == branch else []
    if already:
        raise RuntimeError('Privacy scan blocked publishing unpushed commits (values not shown):\n'
                           + '\n'.join(f'  commit {c} {p} {k}' for c, p, k in already[:20]))
    if dry_run:
        return 'Dry run: scan and tests passed; would commit and push to ' + remote + '.'
    if target != branch:
        git(repo, 'switch', '-c', target, base if base != 'HEAD' else 'HEAD')
        branch = target
    footer = footer if footer is not None else os.environ.get('T3_ADDS_COMMIT_FOOTER', '')
    commits = 0
    for (kind, name), paths in sorted(groups(repo).items()):
        subject = {'addon': f'chore({name}): update after T3 update', 'lifecycle': 'chore: update addon lifecycle tooling',
                   'docs': 'docs: update repository docs and config'}[kind]
        git(repo, 'reset', '-q', check=False)
        git(repo, 'add', '-A', '--', *paths)
        if not git(repo, 'diff', '--cached', '--name-only').strip():
            continue
        message = subject + ('\n\n' + footer if footer else '')
        git(repo, 'commit', '-q', '-m', message)
        commits += 1
    try:
        git(repo, 'push', '-u', remote, branch, network=True)
    except RuntimeError as error:
        raise RuntimeError(f'Committed {commits} commit(s) on {branch} but the push failed: {error}')
    return f'Published {commits} commit(s) to {remote}/{branch}.'


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--repo', type=Path)
    parser.add_argument('--footer')
    parser.add_argument('--skip-tests', action='store_true')
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args(argv)
    try:
        message = run_publish(args.repo, args.footer, args.skip_tests, args.dry_run)
    except RuntimeError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(message or 'Working tree is clean; nothing to publish.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
