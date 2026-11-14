"""Layered install, update, and withdrawal against a synthetic application. No macOS signing or real T3."""
import argparse
import json
import plistlib
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import install
from asar import Archive, digest

INDEX = '<html>\n  <body>\n    <div id="root"></div>\n  </body>\n</html>\n'


def write_archive(path, files):
    header = json.dumps({'files': {}}).encode()
    payload = struct.pack('<I', len(header)) + header
    payload += b'\0' * (-len(payload) % 4)
    pickle = struct.pack('<I', len(payload)) + payload
    Path(path).write_bytes(struct.pack('<II', 4, len(pickle)) + pickle)
    empty = Archive(path)
    return empty.rewrite(Path(path), files)


def overlay(app, files):
    """Stand in for another addon: add files and an index entry, keep plist integrity consistent."""
    archive_path = app / 'Contents/Resources/app.asar'
    archive = Archive(archive_path)
    index = archive.read(install.ENTRY).decode().replace('</body>', '<!-- t3-adds:other -->\n  </body>')
    files = {install.ENTRY: index.encode(), **files}
    rewritten = archive_path.with_suffix('.new')
    header_hash = archive.rewrite(rewritten, files)
    rewritten.replace(archive_path)
    info = app / 'Contents/Info.plist'
    plist = plistlib.loads(info.read_bytes())
    plist['ElectronAsarIntegrity']['Resources/app.asar']['hash'] = header_hash
    info.write_bytes(plistlib.dumps(plist))


class LayeredInstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        self.app = self.root / 'App.app'
        (self.app / 'Contents/Resources').mkdir(parents=True)
        verified = install.ADDON['compatibility']['verified'][-1]
        package = json.dumps({'version': verified['version'], 't3codeCommitHash': verified['commit']}).encode()
        header_hash = write_archive(self.app / 'Contents/Resources/app.asar', {
            'package.json': package, install.ENTRY: INDEX.encode(),
            install.PREFIX + 'assets/host.js': b'host', 'other.txt': b'keep'})
        (self.app / 'Contents/Info.plist').write_bytes(plistlib.dumps({
            'CFBundleIdentifier': 'com.example.t3',
            'ElectronAsarIntegrity': {'Resources/app.asar': {'algorithm': 'SHA256', 'hash': header_hash}}}))
        self.sources = {install.ASSETS + 'ui.mjs': b'ui-v1', install.ASSETS + 'old.mjs': b'old'}
        patches = [
            patch.object(install, 'STATE', self.state),
            patch.object(install, 'RECEIPT', self.state / 'installation.json'),
            patch.object(install, 'sources', lambda found: dict(self.sources)),
            patch.object(install, 'discover', lambda archive: {'chunk': 'host.js', 'alias': 'A', 'chunkSha256': 'x'}),
            patch.object(install, 'source_record', lambda: {'src': 'x'}),
            patch.object(install, 'verify_signed', lambda path: None),
            patch.object(install, 'verify_host', lambda app: Archive(Path(app) / 'Contents/Resources/app.asar')),
            patch.object(install, 'run', lambda *args: __import__('shutil').copytree(args[1], args[2], symlinks=True)),
            patch.object(install.signing, 'resolve', lambda app, state: {'sha1': 'A' * 40, 'keychain': None}),
            patch.object(install.signing, 'sign', lambda staged, config, state: {'kind': 'test', 'sha1': 'A' * 40}),
            patch.object(install.signing, 'verify', lambda path, config: None),
        ]
        for context in patches:
            context.start()
            self.addCleanup(context.stop)

    def run_action(self, action):
        install.execute(argparse.Namespace(action=action), self.app)

    def entries(self):
        return install.entries(self.app)

    def index(self):
        return Archive(self.app / 'Contents/Resources/app.asar').read(install.ENTRY).decode()

    def test_install_adds_only_the_addon_entry_and_assets_then_remove_restores_every_entry(self):
        original = self.entries()
        self.run_action('apply')
        installed = self.entries()
        self.assertEqual(set(installed) - set(original), set(self.sources))
        self.assertEqual(self.index().count(install.MARKER), 1)
        self.assertEqual({p for p in original if original[p] != installed.get(p)}, {install.ENTRY})
        receipt = json.loads((self.state / 'installation.json').read_text())
        self.assertEqual(receipt['ownedEntries'], {p: digest(d) for p, d in self.sources.items()})
        self.assertEqual(receipt['hostDiscovery']['chunk'], 'host.js')
        self.run_action('remove')
        self.assertEqual(self.entries(), original)
        self.assertEqual(self.index(), INDEX)
        self.assertFalse((self.state / 'installation.json').exists())
        self.assertEqual(len(list((self.state / 'transactions').glob('*-receipt.json'))), 1)
        self.assertEqual(len(list((self.state / 'backups').glob('*/App.app'))), 2)

    def test_removal_keeps_another_addons_changes_in_any_order(self):
        original = self.entries()
        self.run_action('apply')
        overlay(self.app, {install.PREFIX + 'assets/other/ui.mjs': b'other'})
        self.run_action('remove')
        remaining = self.entries()
        self.assertEqual(set(remaining) - set(original), {install.PREFIX + 'assets/other/ui.mjs'})
        self.assertIn('<!-- t3-adds:other -->', self.index())
        self.assertNotIn(install.MARKER, self.index())

    def test_removal_refuses_changed_addon_files_and_leaves_application_unchanged(self):
        self.run_action('apply')
        overlay(self.app, {install.ASSETS + 'ui.mjs': b'tampered'})
        before = self.entries()
        with self.assertRaisesRegex(ValueError, 'changed or missing'):
            self.run_action('remove')
        self.assertEqual(self.entries(), before)
        self.assertTrue((self.state / 'installation.json').exists())
        self.assertFalse((self.state / 'transactions/pending.json').exists())

    def test_apply_is_not_repeated_and_refuses_an_existing_entry(self):
        self.run_action('apply')
        with self.assertRaisesRegex(ValueError, 'receipt exists'):
            self.run_action('apply')
        (self.state / 'installation.json').unlink()
        with self.assertRaisesRegex(ValueError, 'already present'):
            self.run_action('apply')

    def test_update_replaces_sources_and_removes_files_no_longer_shipped(self):
        self.run_action('apply')
        self.sources = {install.ASSETS + 'ui.mjs': b'ui-v2', install.ASSETS + 'new.mjs': b'new'}
        self.run_action('update')
        archive = Archive(self.app / 'Contents/Resources/app.asar')
        self.assertEqual(archive.read(install.ASSETS + 'ui.mjs'), b'ui-v2')
        self.assertEqual(archive.read(install.ASSETS + 'new.mjs'), b'new')
        self.assertNotIn(install.ASSETS + 'old.mjs', self.entries())
        self.assertEqual(self.index().count(install.MARKER), 1)
        receipt = json.loads((self.state / 'installation.json').read_text())
        self.assertEqual(set(receipt['ownedEntries']), set(self.sources))

    def test_failed_validation_rolls_back_without_leaving_a_pending_transaction(self):
        original = self.entries()
        with patch.object(install.signing, 'verify', side_effect=ValueError('boom')):
            with self.assertRaisesRegex(ValueError, 'boom'):
                self.run_action('apply')
        self.assertEqual(self.entries(), original)
        self.assertFalse((self.state / 'transactions/pending.json').exists())
        self.assertFalse((self.state / 'installation.json').exists())

    def test_forget_archives_a_stale_receipt_only_when_the_addon_is_gone(self):
        self.run_action('apply')
        with self.assertRaisesRegex(ValueError, 'still present'):
            self.run_action('forget')

    def test_unsupported_host_build_is_rejected(self):
        patch.stopall()
        with patch.object(install, 'verify_signed', lambda path: None):
            package = json.loads(Archive(self.app / 'Contents/Resources/app.asar').read('package.json'))
            package['version'] = '9.9.9'
            overlay(self.app, {'package.json': json.dumps(package).encode()})
            with self.assertRaisesRegex(ValueError, 'Unsupported T3 build'):
                install.verify_host(self.app)
            package['version'] = '0.1.12'
            overlay(self.app, {'package.json': json.dumps(package).encode()})
            with self.assertRaisesRegex(ValueError, 'Unsupported T3 client'):
                install.verify_host(self.app)


if __name__ == '__main__':
    unittest.main()
