#!/usr/bin/env python3
"""Tests for update_all.py against fake addon folders and a fake app folder. Nothing real is touched."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).parent))
import update_all

FAKE = '''
import json, os, sys
from pathlib import Path
ID = {id!r}
BUNDLE = {bundle!r}
root = Path(os.environ['T3_ADDS_STATE_DIR']) / ID
action = sys.argv[1]
app = Path(sys.argv[sys.argv.index('--app') + 1])
manifest = app / 'apps.json'
receipt = root / ('backups/model-council-install.json' if BUNDLE else 'installation.json')
fail = os.environ.get('FAKE_FAIL', '').split(',')
def apps(): return json.loads(manifest.read_text()) if manifest.exists() else []
def save(v): manifest.write_text(json.dumps(v))
if action == 'setup-signing':
    (root / 'signing').mkdir(parents=True, exist_ok=True); (root / 'signing/identity.json').write_text('{{}}')
elif action == 'apply':
    if not (root / 'signing/identity.json').exists(): sys.exit('Persistent signing is not configured.')
    once = root / 'once-apply'
    if ID in os.environ.get('FAKE_APPLY_ONCE', '').split(',') and not once.exists():
        once.write_text('x'); sys.exit('flaky apply')
    if ID in fail: sys.exit('Installation stopped: Unsupported T3 build')
    if receipt.exists(): sys.exit('receipt exists')
    receipt.parent.mkdir(parents=True, exist_ok=True); receipt.write_text('{{}}'); save(apps() + [ID])
elif action in ("remove", "restore"):
    if ID in os.environ.get('FAKE_REMOVE_FAIL', '').split(','): sys.exit('locked')
    if not receipt.exists(): sys.exit('nothing')
    receipt.unlink(); save([a for a in apps() if a != ID])
elif action == 'check':
    once = root / 'once-check'
    if ID in os.environ.get('FAKE_CHECK_ONCE', '').split(',') and not once.exists():
        once.parent.mkdir(parents=True, exist_ok=True); once.write_text('x'); sys.exit('flaky check')
    if ID in os.environ.get('FAKE_CHECK_FAIL', '').split(','): sys.exit('entry missing')
    if receipt.exists() and ID not in apps(): sys.exit('receipt without addon')
elif action == 'forget':
    if ID in apps(): sys.exit('still present')
    receipt.unlink()
elif action == 'install-official':
    if ID in os.environ.get('FAKE_OFFICIAL_FAIL', '').split(','): sys.exit('bad candidate')
    cand = Path(sys.argv[sys.argv.index('--candidate') + 1]); (app / 'version').write_text(cand.name); cand.unlink()
'''


class Fixture:
    def __init__(self, test):
        self.tmp = tempfile.TemporaryDirectory()
        test.addCleanup(self.tmp.cleanup)
        base = Path(self.tmp.name)
        self.state, self.app, self.addons = base / 'state', base / 'app', base / 'addons'
        self.app.mkdir()
        os.environ['T3_ADDS_STATE_DIR'] = str(self.state)
        os.environ.pop('FAKE_FAIL', None)
        for key in ('FAKE_CHECK_FAIL', 'FAKE_APPLY_ONCE', 'FAKE_CHECK_ONCE', 'FAKE_REMOVE_FAIL'):
            os.environ.pop(key, None)
        for addon_id, bundle in (('council', True), ('alpha', False), ('beta', False)):
            folder = self.addons / addon_id
            (folder / 'scripts').mkdir(parents=True)
            (folder / 'addon.json').write_text(json.dumps({'id': addon_id}))
            body = FAKE.format(id=addon_id, bundle=bundle)
            if bundle:
                body += "\n# 'restore'\n"
            (folder / 'scripts/install.py').write_text(body)

    def run(self, *extra):
        lines = []
        restarts = []
        self.published = []
        code = update_all.run(update_all.build_args(['--app', str(self.app), '--addons', str(self.addons), *extra]),
                              restarter=restarts.append, out=lines.append,
                              publisher=lambda: self.published.append(1) or 'Published.')
        return code, '\n'.join(lines), restarts

    def installed(self):
        manifest = self.app / 'apps.json'
        return sorted(json.loads(manifest.read_text())) if manifest.exists() else []

    def receipt(self, addon_id, bundle=False):
        return self.state / addon_id / ('backups/model-council-install.json' if bundle else 'installation.json')

    def seed(self, ids):
        for addon_id in ids:
            bundle = addon_id == 'council'
            path = self.receipt(addon_id, bundle)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('{}')
        (self.app / 'apps.json').write_text(json.dumps(ids))


class UpdateAllTests(unittest.TestCase):
    def test_success_replugs_everything_and_restarts_once(self):
        f = Fixture(self)
        f.seed(['council', 'alpha', 'beta'])
        cand = f.state.parent / 'T3-1.0.0.app'
        cand.write_text('x')
        code, out, restarts = f.run('--candidate', str(cand))
        self.assertEqual(code, 0, out)
        self.assertEqual(f.installed(), ['alpha', 'beta', 'council'])
        self.assertEqual((f.app / 'version').read_text(), 'T3-1.0.0.app')
        self.assertEqual(len(restarts), 1)
        self.assertEqual(out.count('attached'), 3)
        self.assertTrue((f.state / 'alpha/signing/identity.json').exists())  # signing set up without a prompt

    def test_signing_identity_is_shared_not_regenerated(self):
        f = Fixture(self)
        f.seed(['council', 'alpha'])
        f.run()
        council = (f.state / 'council/signing/identity.json').read_text()
        self.assertEqual((f.state / 'alpha/signing/identity.json').read_text(), council)

    def test_one_failure_is_reported_and_others_continue(self):
        f = Fixture(self)
        f.seed(['council', 'alpha', 'beta'])
        os.environ['FAKE_FAIL'] = 'alpha'
        code, out, restarts = f.run()
        self.assertEqual(code, 1)
        self.assertEqual(f.installed(), ['beta', 'council'])
        self.assertIn('alpha', out)
        self.assertIn('Unsupported T3 build', out)
        self.assertEqual(len(restarts), 1)
        wanted = json.loads((f.state / 'lifecycle/wanted.json').read_text())['wanted']
        self.assertIn('alpha', wanted)  # still wanted, so a later run retries it
        os.environ.pop('FAKE_FAIL')
        code, out, _ = f.run()
        self.assertEqual(code, 0, out)
        self.assertEqual(f.installed(), ['alpha', 'beta', 'council'])

    def test_interruption_is_repaired_by_rerun(self):
        f = Fixture(self)
        f.seed(['council', 'alpha', 'beta'])
        # Simulate a run that died after the wanted list was saved and the addons were withdrawn.
        update_all.write_json(f.state / 'lifecycle/wanted.json', {'wanted': ['council', 'alpha', 'beta'], 'updated': None})
        for addon_id in ('alpha', 'beta', 'council'):
            f.receipt(addon_id, addon_id == 'council').unlink()
        (f.app / 'apps.json').write_text('[]')
        code, out, _ = f.run()
        self.assertEqual(code, 0, out)
        self.assertEqual(f.installed(), ['alpha', 'beta', 'council'])

    def test_rerun_with_everything_attached_changes_nothing_but_still_succeeds(self):
        f = Fixture(self)
        f.seed(['council', 'alpha'])
        self.assertEqual(f.run()[0], 0)
        self.assertEqual(f.run()[0], 0)
        self.assertEqual(f.installed(), ['alpha', 'council'])

    def test_stale_overlay_receipt_after_official_update_is_forgotten(self):
        f = Fixture(self)
        f.seed(['alpha'])
        (f.app / 'apps.json').write_text('[]')  # official updater replaced the app; receipt is stale
        code, out, _ = f.run()
        self.assertEqual(code, 0, out)
        self.assertEqual(f.installed(), ['alpha'])

    def test_failed_check_is_reported_not_fatal(self):
        f = Fixture(self)
        f.seed(['alpha', 'beta'])
        os.environ['FAKE_CHECK_FAIL'] = 'alpha'
        code, out, _ = f.run()
        self.assertEqual(code, 1)
        self.assertIn('check: entry missing', out)
        self.assertIn('beta', out)

    def test_drop_stops_wanting_an_addon(self):
        f = Fixture(self)
        f.seed(['alpha', 'beta'])
        os.environ['FAKE_FAIL'] = 'alpha'
        f.run()
        os.environ.pop('FAKE_FAIL')
        code, out, _ = f.run('--drop', 'alpha')
        self.assertEqual(f.installed(), ['beta'])
        self.assertEqual(code, 0)

    def test_missing_candidate_is_a_note_not_a_stop(self):
        f = Fixture(self)
        f.seed(['alpha'])
        code, out, _ = f.run('--candidate', str(f.state / 'gone.app'))
        self.assertEqual(code, 0)
        self.assertIn('candidate not found', out)
        self.assertEqual(f.installed(), ['alpha'])

    def test_no_restart_flag(self):
        f = Fixture(self)
        f.seed(['alpha'])
        self.assertEqual(f.run('--no-restart')[2], [])


class ReviewFixTests(unittest.TestCase):
    def test_hand_withdrawn_addon_is_not_reapplied(self):
        f = Fixture(self)
        f.seed(['alpha', 'beta'])
        self.assertEqual(f.run()[0], 0)
        f.receipt('beta').unlink()  # user withdrew beta by hand
        (f.app / 'apps.json').write_text('["alpha"]')
        self.assertEqual(f.run()[0], 0)
        self.assertEqual(f.installed(), ['alpha'])
        self.assertNotIn('beta', json.loads((f.state / 'lifecycle/wanted.json').read_text())['wanted'])

    def test_unwithdrawable_overlay_blocks_update_and_stays_installed(self):
        f = Fixture(self)
        f.seed(['council', 'alpha'])
        cand = f.state.parent / 'T3-2.0.0.app'
        cand.write_text('x')
        os.environ['FAKE_REMOVE_FAIL'] = 'alpha'
        self.addCleanup(os.environ.pop, 'FAKE_REMOVE_FAIL', None)
        code, out, _ = f.run('--candidate', str(cand))
        self.assertEqual(code, 1)
        self.assertTrue(cand.exists())  # official update was not installed
        self.assertFalse((f.app / 'version').exists())
        self.assertIn('NOT installed: could not withdraw alpha', out)
        self.assertNotIn('Left withdrawn: alpha', out)
        self.assertIn('alpha', f.installed())

    def test_zip_staging_is_removed_after_success_and_failure(self):
        f = Fixture(self)
        f.seed(['council'])
        staging = f.state / 'lifecycle/staging'
        def fake_prepare(candidate, root):
            folder = root / 'lifecycle/staging/x'
            (folder / 'T3.app').mkdir(parents=True)
            return folder / 'T3.app', folder
        original = update_all.prepare_candidate
        update_all.prepare_candidate = fake_prepare
        self.addCleanup(setattr, update_all, 'prepare_candidate', original)
        zipped = f.state.parent / 'T3.zip'
        zipped.write_text('x')
        for fail in ('', 'council'):
            os.environ['FAKE_OFFICIAL_FAIL'] = fail
            f.seed(['council'])
            f.run('--candidate', str(zipped))
            self.assertFalse(list(staging.glob('*')) if staging.exists() else [], fail)
        os.environ.pop('FAKE_OFFICIAL_FAIL')


class SelfHealTests(unittest.TestCase):
    def test_flaky_apply_and_check_heal_with_one_retry(self):
        f = Fixture(self)
        f.seed(['alpha', 'beta'])
        os.environ['FAKE_APPLY_ONCE'] = 'alpha'
        os.environ['FAKE_CHECK_ONCE'] = 'beta'
        self.addCleanup(os.environ.pop, 'FAKE_APPLY_ONCE', None)
        self.addCleanup(os.environ.pop, 'FAKE_CHECK_ONCE', None)
        code, out, restarts = f.run()
        self.assertEqual(code, 0, out)
        self.assertEqual(f.installed(), ['alpha', 'beta'])
        self.assertEqual(len(restarts), 1)

    def test_hard_failure_prints_exact_next_command_and_others_stay(self):
        f = Fixture(self)
        f.seed(['alpha', 'beta'])
        os.environ['FAKE_FAIL'] = 'alpha'
        code, out, _ = f.run()
        self.assertEqual(code, 1)
        self.assertIn('next: cd "' + str(f.addons / 'alpha') + '" && python3 scripts/install.py apply --app "' + str(f.app) + '"', out)
        self.assertEqual(f.installed(), ['beta'])
        self.assertEqual(f.published, [])  # nothing is published unless everything attached

    def test_publish_runs_only_when_all_attached_and_not_disabled(self):
        f = Fixture(self)
        f.seed(['alpha'])
        f.run()
        self.assertEqual(f.published, [1])
        f.run('--no-publish')
        self.assertEqual(f.published, [])

    def test_publish_failure_does_not_fail_the_update(self):
        f = Fixture(self)
        f.seed(['alpha'])
        lines = []
        def boom():
            raise RuntimeError('Privacy scan blocked publishing')
        code = update_all.run(update_all.build_args(['--app', str(f.app), '--addons', str(f.addons)]),
                              restarter=lambda app: None, out=lines.append, publisher=boom)
        self.assertEqual(code, 0)
        self.assertIn('Publish skipped: Privacy scan blocked publishing', '\n'.join(lines))


if __name__ == '__main__':
    unittest.main()
