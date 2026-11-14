#!/usr/bin/env python3
"""Tests for publish.py using a temporary git repository and a local bare remote."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import publish


def git(repo, *args):
    return subprocess.run(['git', '-C', str(repo), *args], capture_output=True, text=True, check=True).stdout


class PublishTests(unittest.TestCase):
    def make(self, remote=True):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        repo, bare = base / 'repo', base / 'remote.git'
        repo.mkdir()
        subprocess.run(['git', 'init', '-q', '-b', 'main', str(repo)], check=True)
        git(repo, 'config', 'user.email', 'dev@example.com')
        git(repo, 'config', 'user.name', 'Dev')
        (repo / 'README.md').write_text('hello\n')
        git(repo, 'add', '-A')
        git(repo, 'commit', '-q', '-m', 'init')
        if remote:
            subprocess.run(['git', 'init', '-q', '--bare', str(bare)], check=True)
            git(repo, 'remote', 'add', 'origin', str(bare))
        return repo, bare

    def dirty(self, repo):
        (repo / 'addons/alpha').mkdir(parents=True)
        (repo / 'addons/alpha/addon.json').write_text('{"id": "alpha"}\n')
        (repo / '.agents').mkdir()
        (repo / '.agents/notes.txt').write_text('tooling\n')
        (repo / 'README.md').write_text('hello again\n')

    def test_logical_commits_on_dated_branch_and_push(self):
        repo, bare = self.make()
        self.dirty(repo)
        message = publish.run_publish(repo, footer='Co-Authored-By: Test <noreply@example.com>', skip_tests=True,
                                      today='2030-01-02')
        self.assertIn('3 commit(s)', message)
        self.assertEqual(git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'update-2030-01-02')
        subjects = git(repo, 'log', '--format=%s', 'main..HEAD').split('\n')
        self.assertTrue(any('alpha' in s for s in subjects))
        self.assertIn('Co-Authored-By: Test', git(repo, 'log', '-1', '--format=%B'))
        self.assertIn('update-2030-01-02', git(bare, 'branch', '--list'))
        self.assertEqual(git(repo, 'status', '--porcelain').strip(), '')
        self.assertIn('init', git(repo, 'log', '--format=%s', 'main'))  # history intact

    def test_clean_tree_does_nothing(self):
        repo, _ = self.make()
        self.assertIsNone(publish.run_publish(repo, skip_tests=True))

    def test_privacy_findings_block_without_revealing_values(self):
        repo, bare = self.make()
        secret = 'ghp_' + 'A1b2C3d4' * 4
        home = '/' + 'Users' + '/' + 'realperson' + '/project'
        mail = 'someone' + '@' + 'private.org'
        (repo / 'leak.txt').write_text(f'token {secret}\npath {home}\nmail {mail}\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        text = str(caught.exception)
        self.assertIn('leak.txt:1 token', text)
        self.assertIn('leak.txt:2 personal-path', text)
        self.assertIn('leak.txt:3 email', text)
        self.assertNotIn(secret, text)
        self.assertNotIn('realperson', text)
        self.assertEqual(git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'main')  # nothing committed
        self.assertEqual(git(bare, 'branch', '--list').strip(), '')

    def test_placeholders_are_allowed(self):
        repo, _ = self.make()
        (repo / 'doc.md').write_text('See /Users/name/x and /home/user/y and a@example.com\n')
        self.assertEqual(publish.scan(repo), [])

    def test_no_remote_stops_with_clear_message(self):
        repo, _ = self.make(remote=False)
        (repo / 'a.txt').write_text('x\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        self.assertIn('No git remote', str(caught.exception))
        self.assertEqual(git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'main')

    def test_failing_addon_test_blocks(self):
        repo, _ = self.make()
        (repo / 'addons/alpha/scripts').mkdir(parents=True)
        (repo / 'addons/alpha/scripts/test_x.py').write_text('import sys; sys.exit(1)\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo)
        self.assertIn('alpha/test_x.py', str(caught.exception))

    def test_existing_update_branch_is_kept_and_never_forced(self):
        repo, bare = self.make()
        git(repo, 'switch', '-q', '-c', 'update-2030-01-01')
        (repo / 'a.txt').write_text('x\n')
        publish.run_publish(repo, skip_tests=True)
        self.assertEqual(git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'update-2030-01-01')
        (repo / 'b.txt').write_text('y\n')
        publish.run_publish(repo, skip_tests=True)
        self.assertEqual(git(repo, 'rev-list', '--count', 'main..update-2030-01-01').strip(), '2')


class ReviewFixTests(PublishTests):
    def test_unscannable_pending_paths_refuse_publish(self):
        repo, bare = self.make()
        (repo / 'blob.bin').write_bytes(b'\0\1\2')
        (repo / 'link').symlink_to('README.md')
        (repo / 'big.txt').write_text('x' * 50)
        old = publish.MAX_BYTES
        publish.MAX_BYTES = 20
        self.addCleanup(setattr, publish, 'MAX_BYTES', old)
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        text = str(caught.exception)
        for name in ('blob.bin', 'link', 'big.txt'):
            self.assertIn(name, text)
        self.assertEqual(git(repo, 'rev-parse', '--abbrev-ref', 'HEAD').strip(), 'main')
        self.assertEqual(git(bare, 'branch', '--list').strip(), '')

    def test_push_timeout_is_reported_and_prompts_are_disabled(self):
        repo, bare = self.make()
        hook = bare / 'hooks/pre-receive'
        hook.write_text('#!/bin/sh\nsleep 10\n')
        hook.chmod(0o755)
        (repo / 'a.txt').write_text('x\n')
        publish.PUSH_TIMEOUT = 1
        self.addCleanup(setattr, publish, 'PUSH_TIMEOUT', 60)
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        self.assertIn('timed out', str(caught.exception))
        seen = {}
        real = publish.subprocess.run
        def spy(*args, **kwargs):
            seen.update(kwargs.get('env') or {})
            seen['timeout'] = kwargs.get('timeout')
            return real(*args, **kwargs)
        publish.subprocess.run = spy
        self.addCleanup(setattr, publish.subprocess, 'run', real)
        publish.git(repo, 'status', network=True)
        self.assertEqual(seen['GIT_TERMINAL_PROMPT'], '0')
        self.assertIn('GIT_ASKPASS', seen)
        self.assertEqual(seen['timeout'], 1)

    def test_git_user_name_is_scanned_and_unpushed_commits_are_scanned(self):
        repo, bare = self.make()
        git(repo, 'config', 'user.name', 'Zed Quuxington')
        (repo / 'who.txt').write_text('by Zed Quuxington\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        self.assertIn('who.txt:1 local-identity', str(caught.exception))
        self.assertNotIn('Quuxington', str(caught.exception))
        (repo / 'who.txt').unlink()
        # A leak already committed on an unpushed update branch must be caught too, even with a clean new change.
        git(repo, 'switch', '-q', '-c', 'update-2030-05-05')
        (repo / 'old.txt').write_text('token ' + 'ghp_' + 'Z9y8X7w6' * 4 + '\n')
        git(repo, 'add', '-A')
        git(repo, 'commit', '-q', '-m', 'oops')
        (repo / 'old.txt').write_text('clean\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        self.assertIn('old.txt token', str(caught.exception))
        self.assertNotIn('Z9y8X7w6', str(caught.exception))
        self.assertEqual(git(bare, 'branch', '--list').strip(), '')

    def test_new_branch_is_based_on_main_not_current_branch(self):
        repo, _ = self.make()
        git(repo, 'switch', '-q', '-c', 'feature')
        (repo / 'feat.txt').write_text('f\n')
        git(repo, 'add', '-A')
        git(repo, 'commit', '-q', '-m', 'feature work')
        (repo / 'new.txt').write_text('n\n')
        publish.run_publish(repo, skip_tests=True, today='2031-01-01')
        self.assertEqual(git(repo, 'rev-parse', 'update-2031-01-01~1').strip(), git(repo, 'rev-parse', 'main').strip())
        self.assertNotIn('feature work', git(repo, 'log', '--format=%s', 'main..update-2031-01-01'))

    def test_existing_dated_branch_that_is_not_current_is_not_reused(self):
        repo, _ = self.make()
        git(repo, 'branch', 'update-2031-02-02')
        (repo / 'a.txt').write_text('x\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True, today='2031-02-02')
        self.assertIn('already exists', str(caught.exception))

    def test_partially_staged_file_stops_but_fully_staged_work_is_published(self):
        repo, bare = self.make()
        (repo / 'README.md').write_text('one\n')
        git(repo, 'add', 'README.md')
        (repo / 'README.md').write_text('one\ntwo\n')
        with self.assertRaises(RuntimeError) as caught:
            publish.run_publish(repo, skip_tests=True)
        self.assertIn('README.md', str(caught.exception))
        git(repo, 'add', 'README.md')
        (repo / 'other.txt').write_text('o\n')
        git(repo, 'add', 'other.txt')
        publish.run_publish(repo, skip_tests=True, today='2031-03-03')
        self.assertEqual(git(repo, 'status', '--porcelain').strip(), '')
        self.assertIn('update-2031-03-03', git(bare, 'branch', '--list'))


if __name__ == '__main__':
    unittest.main()
