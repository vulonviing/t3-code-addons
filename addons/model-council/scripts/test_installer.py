"""Verify installer safety gates without touching macOS applications."""
import argparse
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
import install
from lifecycle import inventory, write_json
from asar import digest


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

    def test_official_update_rejects_team_mismatch_and_downgrade(self):
        self.receipt.unlink()
        candidate = self.root/'Candidate.app'
        shutil.copytree(self.original, candidate)
        args = self.args('install-official'); args.candidate = candidate
        for teams, versions, expected in [(['A','B'], ['0.1.6','0.1.7'], 'distributor'), (['A','A'], ['0.1.7','0.1.6'], 'newer')]:
            with self.subTest(expected=expected), patch.object(install, 'team', side_effect=teams), patch.object(install, 'identity', side_effect=[dict(bundleId='test', version=v) for v in versions]):
                with self.assertRaisesRegex(ValueError, expected):
                    install.execute(args, self.app)
            self.assertEqual((self.app/'Contents/Resources/app.asar').read_bytes(), b'addon')
            self.assertFalse((self.state/'transactions/pending.json').exists())


if __name__ == '__main__':
    unittest.main()
