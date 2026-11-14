"""Verify installer safety gates without touching macOS applications."""
import argparse
import json
import plistlib
import shutil
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import install
from lifecycle import inventory, write_json
from asar import Archive, digest


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.app = self.root / 'App.app'
        self.original = self.state / 'backups/original/App.app'
        for app, content in ((self.app, b'addon'), (self.original, b'original')):
            resources = app / 'Contents/Resources'
            resources.mkdir(parents=True)
            (resources / 'app.asar').write_bytes(content)
        self.receipt = self.state / 'backups/model-council-install.json'
        write_json(self.receipt, dict(app=str(self.app), backup='backups/original/App.app',
                   installedAsarHash=digest(b'addon'), originalInventory=inventory(self.original),
                   installedInventory=inventory(self.app), schemaVersion=2))
        for name, value in [('STATE', self.state), ('RECEIPT', self.receipt)]:
            context = patch.object(install, name, value)
            context.start(); self.addCleanup(context.stop)
        context = patch.object(install, 'verify_signed')
        context.start(); self.addCleanup(context.stop)

    def args(self, action):
        return argparse.Namespace(action=action, staged=self.state/'stage/App.app', candidate=None)

    def test_restore_uses_recorded_baseline_independent_of_new_source_compatibility(self):
        args = self.args('restore')
        def copy(command, source, target):
            self.assertEqual(command, 'ditto'); shutil.copytree(source, target)
        with patch.object(install, 'verify_original', side_effect=AssertionError('source guard must not gate restoration')), patch.object(install, 'run', side_effect=copy), patch.object(install, 'identity', return_value={'version': 'old'}):
            install.execute(args, self.app)
        self.assertEqual((self.app/'Contents/Resources/app.asar').read_bytes(), b'original')
        self.assertTrue(self.original.exists())
        self.assertFalse(self.receipt.exists())
        self.assertEqual(len(list((self.state/'transactions').glob('*-receipt.json'))), 1)

    def test_unrelated_file_change_prevents_withdrawal(self):
        (self.app/'unrelated').write_text('retain')
        with self.assertRaisesRegex(ValueError, 'changed since recording'):
            install.execute(self.args('restore'), self.app)
        self.assertEqual((self.app/'unrelated').read_text(), 'retain')
        self.assertTrue(self.receipt.exists())

    def test_changed_original_backup_prevents_withdrawal(self):
        (self.original/'unrelated').write_text('changed')
        with self.assertRaisesRegex(ValueError, 'changed since recording'):
            install.checked_receipt(self.app)

    def test_official_update_requires_withdrawal(self):
        with self.assertRaisesRegex(ValueError, 'Withdraw'):
            install.execute(self.args('install-official'), self.app)

    def test_old_ad_hoc_stage_cannot_bypass_persistent_signing(self):
        args = self.args('update')
        shutil.copytree(self.original, args.staged)
        write_json(args.staged.with_name(args.staged.name + '.prepared.json'),
                   dict(original=inventory(self.original), prepared=inventory(args.staged), sources={}))
        with patch.object(install, 'source_record', return_value={}), patch.object(install.signing, 'load', return_value={'sha1': 'A' * 40}):
            with self.assertRaisesRegex(ValueError, 'signing identity differs'):
                install.execute(args, self.app)
        self.assertFalse((self.state / 'transactions/pending.json').exists())
        self.assertEqual((self.app / 'Contents/Resources/app.asar').read_bytes(), b'addon')

    def install_official(self, live_team, candidate_team, versions, recorded=('A',)):
        self.receipt.unlink(missing_ok=True)
        candidate = self.root / 'Candidate.app'
        shutil.rmtree(candidate, ignore_errors=True)
        shutil.copytree(self.original, candidate)
        args = self.args('install-official'); args.candidate = candidate
        identities = [dict(bundleId='test', version=v) for v in versions]
        with patch.object(install, 'team', side_effect=[live_team, candidate_team]), \
                patch.object(install, 'recorded_teams', return_value=set(recorded)), \
                patch.object(install, 'identity', side_effect=identities):
            install.execute(args, self.app)

    def refused(self, pattern, *args, **kwargs):
        with self.assertRaisesRegex(ValueError, pattern):
            self.install_official(*args, **kwargs)
        self.assertEqual((self.app/'Contents/Resources/app.asar').read_bytes(), b'addon')
        self.assertFalse((self.state/'transactions/pending.json').exists())

    def test_locally_signed_app_accepts_same_version_candidate_from_the_recorded_team(self):
        self.install_official(None, 'A', ['0.1.9', '0.1.9'])
        self.assertEqual((self.app/'Contents/Resources/app.asar').read_bytes(), b'original')
        self.assertEqual(len(list((self.state/'backups').glob('*/App.app'))), 2)  # replaced app is kept
        for live in (None, 'not set'):
            with self.subTest(live=live):
                self.setUp()
                self.install_official(live, 'A', ['0.1.8', '0.1.9'])

    def test_wrong_team_candidate_is_refused(self):
        self.refused('distributor', 'not set', 'B', ['0.1.8', '0.1.9'])
        self.refused('distributor', 'A', 'B', ['0.1.8', '0.1.9'])
        self.refused('distributor', 'not set', 'A', ['0.1.8', '0.1.9'], recorded=())

    def test_older_candidate_is_refused(self):
        self.refused('newer', 'not set', 'A', ['0.1.9', '0.1.8'])
        self.refused('newer', 'A', 'A', ['0.1.9', '0.1.8'])

    def test_distributor_signed_app_refuses_same_version_but_accepts_newer(self):
        self.refused('newer', 'A', 'A', ['0.1.9', '0.1.9'])
        self.setUp()
        self.install_official('A', 'A', ['0.1.8', '0.1.9'])


INDEX = '<html>\n  <body>\n    <div id="root"></div>\n  </body>\n</html>\n'


def make_app(path, files, version):
    """Synthetic application bundle with a real ASAR archive; no T3 and no signing."""
    resources = path / 'Contents/Resources'
    resources.mkdir(parents=True)
    header = json.dumps({'files': {}}).encode()
    payload = struct.pack('<I', len(header)) + header
    payload += b'\0' * (-len(payload) % 4)
    pickle = struct.pack('<I', len(payload)) + payload
    archive_path = resources / 'app.asar'
    archive_path.write_bytes(struct.pack('<II', 4, len(pickle)) + pickle)
    header_hash = Archive(archive_path).rewrite(archive_path, {
        'package.json': json.dumps({'version': version, 't3codeCommitHash': 'abcdef012345'}).encode(),
        install.ENTRY: INDEX.encode(), **files})
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({
        'CFBundleIdentifier': 'com.example.t3', 'ElectronAsarIntegrity': {'Resources/app.asar': {'algorithm': 'SHA256', 'hash': header_hash}}}))
    return header_hash


class HostDiscoveryTests(unittest.TestCase):
    """The installer has no T3 version or hash gate and verifies the prepared archive against the original."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        context = patch.object(install, 'run')
        context.start(); self.addCleanup(context.stop)

    def prepared(self, original, tamper=None):
        archive = Archive(original / 'Contents/Resources/app.asar')
        found = install.discover(archive)
        files = install.replacements(archive, found)
        prepared = original.parent / 'prepared.app'
        shutil.copytree(original, prepared)
        if tamper:
            files = {**files, **tamper}
        header_hash = archive.rewrite(prepared / 'Contents/Resources/app.asar.new', files)
        (prepared / 'Contents/Resources/app.asar.new').replace(prepared / 'Contents/Resources/app.asar')
        plist = plistlib.loads((prepared / 'Contents/Info.plist').read_bytes())
        plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
        (prepared / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))
        return prepared, found

    def test_any_t3_version_and_unknown_layout_is_accepted_and_reports_what_is_missing(self):
        for version in ('0.1.7', '0.1.12', '9.9.9'):
            with self.subTest(version=version):
                original = self.root / version / 'App.app'
                make_app(original, {install.PREFIX + 'assets/unrelated.js': b'export{};'}, version)
                self.assertIsNotNone(install.verify_original(original))
                found = install.host_discovery(original)
                self.assertIn('the atom registry', found['missing'])
                prepared, _ = self.prepared(original)
                install.validate_prepared(prepared, original)
                adapter = Archive(prepared / 'Contents/Resources/app.asar').read(install.ASSETS + 'host.mjs').decode()
                self.assertIn('the atom registry', adapter)
                self.assertNotIn('@@', adapter)

    def test_prepared_archive_with_an_unexpected_host_change_is_refused(self):
        original = self.root / 'App.app'
        make_app(original, {install.PREFIX + 'assets/other.js': b'export{};'}, '0.1.9')
        prepared, _ = self.prepared(original, tamper={install.PREFIX + 'assets/other.js': b'changed'})
        with self.assertRaisesRegex(ValueError, 'Unexpected host change'):
            install.validate_prepared(prepared, original)

    def test_prepared_archive_missing_an_addon_file_is_refused(self):
        original = self.root / 'App.app'
        make_app(original, {}, '0.1.9')
        prepared, _ = self.prepared(original, tamper={install.ASSETS + 'host.mjs': b'tampered'})
        with self.assertRaisesRegex(ValueError, 'Addon mismatch'):
            install.validate_prepared(prepared, original)


OVERLAY_TAG = '<!-- t3-adds:other -->\n    <script type="module" src="/assets/other/ui.mjs"></script>\n  '


class LayeredTests(unittest.TestCase):
    """Model Council beside other addons: only its own entries are verified, withdrawn, and updated."""

    CHUNK = install.PREFIX + 'assets/chunk.js'

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.app = self.root / 'App.app'
        self.original = self.state / 'backups/original/App.app'
        make_app(self.original, {self.CHUNK: b'export{};'}, '0.1.9')
        shutil.copytree(self.original, self.app)
        self.sources = {install.ASSETS + 'ui.mjs': b'ui-v1', install.ASSETS + 'host.mjs': b'host-v1'}
        self.found = {'bindings': {}, 'missing': [], 'chunkSha256': {}}
        for context in (patch.object(install, 'STATE', self.state), patch.object(install, 'RECEIPT', self.state / 'backups/model-council-install.json'),
                        patch.object(install, 'verify_signed'), patch.object(install, 'sources', lambda found: dict(self.sources)),
                        patch.object(install, 'discover', lambda archive: self.found),
                        patch.object(install, 'source_record', lambda: {'src': 'x'}),
                        patch.object(install, 'run', lambda *a: shutil.copytree(a[1], a[2], symlinks=True) if a[0] == 'ditto' else None),
                        patch.object(install.signing, 'load', lambda state: {'sha1': 'A' * 40}),
                        patch.object(install.signing, 'sign', lambda staged, state: {'kind': 'test', 'sha1': 'A' * 40}),
                        patch.object(install.signing, 'verify', lambda path, config: None)):
            context.start(); self.addCleanup(context.stop)
        self.rewrite(self.app, {install.ENTRY: INDEX.replace('</body>', install.OWN_BLOCK + '</body>').encode(), **self.sources})
        self.receipt = dict(app=str(self.app), backup='backups/original/App.app', schemaVersion=2, signing={'sha1': 'A' * 40},
                            host={'bundleId': 'com.example.t3'}, ownedEntries={p: digest(d) for p, d in self.sources.items()},
                            hostDiscovery={'chunkSha256': {'chunk.js': digest(b'export{};')}},
                            installedAsarHash=digest((self.app / 'Contents/Resources/app.asar').read_bytes()),
                            originalInventory=inventory(self.original), installedInventory=inventory(self.app))
        write_json(install.RECEIPT, self.receipt)

    def rewrite(self, app, files, removals=()):
        archive_path = app / 'Contents/Resources/app.asar'
        archive = Archive(archive_path)
        rewritten = archive_path.with_suffix('.new')
        header_hash = archive.rewrite(rewritten, files, list(removals))
        rewritten.replace(archive_path)
        plist = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        plist['CFBundleIdentifier'] = 'com.example.t3'
        plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
        (app / 'Contents/Info.plist').write_bytes(plistlib.dumps(plist))

    def add_overlay(self):
        index = Archive(self.app / 'Contents/Resources/app.asar').read(install.ENTRY).decode()
        self.rewrite(self.app, {install.ENTRY: index.replace('</body>', OVERLAY_TAG + '</body>').encode(),
                                install.PREFIX + 'assets/other/ui.mjs': b'other'})

    def run_action(self, action):
        install.execute(argparse.Namespace(action=action, staged=self.state / 'stage/App.app', candidate=None), self.app)

    def index(self):
        return Archive(self.app / 'Contents/Resources/app.asar').read(install.ENTRY).decode()

    def test_overlay_modified_archive_passes_check(self):
        self.add_overlay()
        receipt, _ = install.checked_receipt(self.app)
        self.assertTrue(receipt['layered'])
        self.run_action('check')

    def test_unchanged_archive_still_uses_the_exact_path(self):
        receipt, _ = install.checked_receipt(self.app)
        self.assertNotIn('layered', receipt)

    def test_old_receipt_without_owned_entries_uses_archive_changes(self):
        del self.receipt['ownedEntries'], self.receipt['hostDiscovery']
        self.receipt['archiveChanges'] = [dict(path=p, before=None, after={'sha256': digest(d)}) for p, d in self.sources.items()]
        write_json(install.RECEIPT, self.receipt)
        self.add_overlay()
        self.assertTrue(install.checked_receipt(self.app)[0]['layered'])

    def test_tampering_with_a_model_council_file_fails(self):
        self.add_overlay()
        self.rewrite(self.app, {install.ASSETS + 'ui.mjs': b'tampered'})
        with self.assertRaisesRegex(ValueError, 'Model Council file changed'):
            install.checked_receipt(self.app)

    def test_missing_script_tag_fails(self):
        self.add_overlay()
        index = self.index().replace(install.OWN_BLOCK, '')
        self.rewrite(self.app, {install.ENTRY: index.encode()})
        with self.assertRaisesRegex(ValueError, 'entry'):
            install.checked_receipt(self.app)

    def test_official_update_that_replaced_the_archive_is_refused(self):
        official = self.root / 'Official.app'
        make_app(official, {self.CHUNK: b'export{};', install.PREFIX + 'assets/new.js': b'new'}, '0.1.10')
        shutil.rmtree(self.app); shutil.copytree(official, self.app)
        for action in ('check', 'restore', 'update'):
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, 'Installation changed since injection|Model Council file changed or missing'):
                self.run_action(action)
        self.assertTrue(install.RECEIPT.exists())
        self.assertEqual((self.app / 'Contents/Info.plist').read_bytes(), (official / 'Contents/Info.plist').read_bytes())

    def test_changed_official_file_beside_valid_model_council_entries_is_refused(self):
        self.add_overlay()
        self.rewrite(self.app, {self.CHUNK: b'export{changed};'})
        with self.assertRaisesRegex(ValueError, 'Installation changed since injection'):
            install.checked_receipt(self.app)

    def test_unrelated_asset_outside_an_addon_directory_is_refused(self):
        self.rewrite(self.app, {install.PREFIX + 'assets/injected.js': b'x'})
        with self.assertRaisesRegex(ValueError, 'Installation changed since injection'):
            install.checked_receipt(self.app)

    def test_stray_subdirectory_asset_is_refused_but_a_marked_overlays_files_are_accepted(self):
        self.add_overlay()
        self.rewrite(self.app, {install.PREFIX + 'assets/other/more/deep.js': b'ok'})
        self.assertTrue(install.checked_receipt(self.app)[0]['layered'])
        self.rewrite(self.app, {install.PREFIX + 'assets/evil/x.js': b'x'})
        with self.assertRaisesRegex(ValueError, 'Installation changed since injection'):
            install.checked_receipt(self.app)

    def test_asset_directory_of_an_addon_without_a_marked_script_line_is_refused(self):
        self.rewrite(self.app, {install.PREFIX + 'assets/other/ui.mjs': b'other'})
        with self.assertRaisesRegex(ValueError, 'Installation changed since injection'):
            install.checked_receipt(self.app)

    def test_unknown_file_inside_the_model_council_directory_is_refused(self):
        self.add_overlay()
        self.rewrite(self.app, {install.ASSETS + 'extra.mjs': b'x'})
        with self.assertRaisesRegex(ValueError, 'Installation changed since injection'):
            install.checked_receipt(self.app)

    def test_restore_with_an_overlay_removes_only_model_council_entries(self):
        self.add_overlay()
        before = install.logical_entries(self.app)
        self.run_action('restore')
        after = install.logical_entries(self.app)
        self.assertEqual({p for p in before.keys() | after.keys() if before.get(p) != after.get(p)},
                         set(self.sources) | {install.ENTRY})
        self.assertNotIn(install.MARKER, self.index())
        self.assertIn('<!-- t3-adds:other -->', self.index())
        self.assertEqual(after[install.PREFIX + 'assets/other/ui.mjs'], before[install.PREFIX + 'assets/other/ui.mjs'])
        self.assertFalse(install.RECEIPT.exists())
        self.assertEqual(len(list((self.state / 'transactions').glob('*-receipt.json'))), 1)
        self.assertEqual(len(list((self.state / 'backups').glob('*/App.app'))), 2)  # original + previous app

    def test_update_with_an_overlay_replaces_only_model_council_entries(self):
        self.add_overlay()
        self.sources = {install.ASSETS + 'ui.mjs': b'ui-v2', install.ASSETS + 'new.mjs': b'new'}
        self.run_action('update')
        archive = Archive(self.app / 'Contents/Resources/app.asar')
        self.assertEqual(archive.read(install.ASSETS + 'ui.mjs'), b'ui-v2')
        self.assertEqual(archive.read(install.PREFIX + 'assets/other/ui.mjs'), b'other')
        self.assertNotIn(install.ASSETS + 'host.mjs', install.logical_entries(self.app))
        self.assertEqual(self.index().count(install.MARKER), 1)
        written = json.loads(install.RECEIPT.read_text())
        self.assertEqual(set(written['ownedEntries']), set(self.sources))
        install.checked_receipt(self.app)  # the updated receipt matches the new archive again

    def test_failed_validation_rolls_back_a_layered_restore(self):
        self.add_overlay()
        before = install.logical_entries(self.app)
        with patch.object(install.signing, 'verify', side_effect=ValueError('boom')):
            with self.assertRaisesRegex(ValueError, 'boom'):
                self.run_action('restore')
        self.assertEqual(install.logical_entries(self.app), before)
        self.assertTrue(install.RECEIPT.exists())
        self.assertFalse((self.state / 'transactions/pending.json').exists())


class SignatureDriftTests(InstallerTests):
    """Overlay re-signing rewrites code bytes; only that difference may be tolerated."""

    MACHO = b'\xcf\xfa\xed\xfe'

    def setUp(self):
        super().setUp()
        for app in (self.app, self.original):
            (app / 'Contents/Frameworks').mkdir()
            (app / 'Contents/_CodeSignature').mkdir()
            (app / 'Contents/Frameworks/lib.dylib').write_bytes(self.MACHO + b'signed-A')
            (app / 'Contents/_CodeSignature/CodeResources').write_bytes(b'seal-A')
            (app / 'Contents/Info.plist').write_bytes(b'plist')
            (app / 'Contents/data.txt').write_bytes(b'data')
        self.write_receipt()
        compare = patch.object(install, 'unsigned_code_equal', return_value=True)
        self.compare = compare.start(); self.addCleanup(compare.stop)
        verify = patch.object(install.signing, 'verify')
        self.verify = verify.start(); self.addCleanup(verify.stop)

    def write_receipt(self):
        write_json(self.receipt, dict(app=str(self.app), backup='backups/original/App.app',
                   installedAsarHash=digest(b'addon'), originalInventory=inventory(self.original),
                   installedInventory=inventory(self.app), schemaVersion=2, signing={'sha1': 'A' * 40}))

    def resign(self):
        (self.app/'Contents/Frameworks/lib.dylib').write_bytes(self.MACHO + b'signed-B')
        (self.app/'Contents/_CodeSignature/CodeResources').write_bytes(b'seal-B')

    def test_signature_only_drift_is_accepted_after_pinned_verification(self):
        self.resign()
        receipt, _ = install.checked_receipt(self.app)
        self.assertEqual(receipt['acceptedSignatureDrift'], ['Contents/Frameworks/lib.dylib', 'Contents/_CodeSignature/CodeResources'])
        self.verify.assert_called_once_with(self.app, {'sha1': 'A' * 40})

    def test_accepted_drift_is_recorded_in_the_new_receipt_and_transaction(self):
        self.resign()
        args = self.args('update')
        shutil.copytree(self.original, args.staged)
        with patch.object(install, 'prepare', side_effect=lambda original, staged: shutil.copytree(original, staged, dirs_exist_ok=True)), \
                patch.object(install, 'identity', return_value={'version': 'x'}), patch.object(install, 'validate_prepared'), \
                patch.object(install, 'host_discovery', return_value={'bindings': {}, 'missing': [], 'chunkSha256': {}}), \
                patch.object(install, 'source_record', return_value={}), patch.object(install, 'archive_changes', return_value=[]), \
                patch.object(install.signing, 'load', return_value={'sha1': 'A' * 40}):
            shutil.rmtree(args.staged)
            write_json(args.staged.with_name(args.staged.name + '.prepared.json'), dict(signing={'sha1': 'A' * 40}))
            install.execute(args, self.app)
        written = json.loads(self.receipt.read_text())
        self.assertEqual(len(written['acceptedSignatureDrift']), 2)
        record = next((self.state / 'transactions').glob('[0-9a-f]*.json'))
        self.assertEqual(len(json.loads(record.read_text())['metadata']['acceptedSignatureDrift']), 2)

    def refuses(self, pattern='changed since recording'):
        with self.assertRaisesRegex(ValueError, pattern):
            install.checked_receipt(self.app)
        self.verify.assert_not_called()

    def test_non_signature_file_change_is_refused(self):
        self.resign(); (self.app/'Contents/data.txt').write_bytes(b'DATA')
        self.refuses()

    def test_non_code_file_with_signature_like_change_is_refused(self):
        (self.app/'Contents/Info.plist').write_bytes(b'PLIST')
        self.refuses()

    def test_changed_code_is_refused(self):
        self.resign()
        self.compare.return_value = False
        self.refuses()

    def test_size_change_is_refused(self):
        (self.app/'Contents/Frameworks/lib.dylib').write_bytes(self.MACHO + b'longer-signature')
        self.refuses()

    def test_mode_change_is_refused(self):
        self.resign(); (self.app/'Contents/Frameworks/lib.dylib').chmod(0o700)
        self.refuses()

    def test_added_file_is_refused(self):
        self.resign(); (self.app/'Contents/extra.dylib').write_bytes(self.MACHO + b'x')
        self.refuses()

    def test_removed_file_is_refused(self):
        self.resign(); (self.app/'Contents/data.txt').unlink()
        self.refuses()

    def test_symlink_target_change_is_refused(self):
        for app in (self.app, self.original):
            (app/'Contents/link').symlink_to('data.txt')
        self.write_receipt()
        (self.app/'Contents/link').unlink(); (self.app/'Contents/link').symlink_to('Info.plist')
        self.refuses()

    def test_asar_change_is_refused(self):
        (self.app/'Contents/Resources/app.asar').write_bytes(b'other')
        with self.assertRaisesRegex(ValueError, 'Installation changed'):
            install.checked_receipt(self.app)

    def test_changed_original_backup_is_refused_even_with_signature_drift(self):
        self.resign(); (self.original/'Contents/Frameworks/lib.dylib').write_bytes(self.MACHO + b'signed-C')
        self.refuses()

    def test_failed_pinned_verification_is_refused(self):
        self.resign(); self.verify.side_effect = ValueError('not signed by the pinned certificate')
        with self.assertRaisesRegex(ValueError, 'pinned certificate'):
            install.checked_receipt(self.app)

    def test_drift_without_a_pinned_signing_record_is_refused(self):
        self.resign()
        receipt = json.loads(self.receipt.read_text()); del receipt['signing']; write_json(self.receipt, receipt)
        self.refuses('no pinned signing record')


if __name__ == '__main__':
    unittest.main()
