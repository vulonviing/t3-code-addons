"""Helper rollback and ownership protection in external temporary directories."""
import json
from pathlib import Path
import tempfile
import sys
import unittest
from unittest.mock import patch
sys.dont_write_bytecode = True
import service


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.state = self.root / 'state'
        for name, value in {'STATE': self.state, 'RECEIPT': self.state / 'service.json',
                            'PENDING': self.state / 'service-pending.json', 'RUNTIME': self.state / 'runtime',
                            'PLIST': self.root / 'launch/helper.plist'}.items():
            p = patch.object(service, name, value); p.start(); self.addCleanup(p.stop)
        for p in [patch.object(service, 'launch'), patch.object(service, 'health'),
                  patch.object(service.shutil, 'which', return_value='/example/codex'),
                  patch.object(service.subprocess, 'run', return_value=type('Result', (), {'stdout': 'codex-cli 0.167.0\n'})())]:
            p.start(); self.addCleanup(p.stop)

    def test_install_then_remove_only_owned_files(self):
        service.manage('install')
        receipt = json.loads(service.RECEIPT.read_text())
        service.owned(receipt)
        other = self.root / 'unrelated'; other.write_text('keep')
        service.manage('remove')
        self.assertFalse(service.RECEIPT.exists())
        self.assertFalse(service.PLIST.exists())
        self.assertEqual(other.read_text(), 'keep')

    def test_failed_start_rolls_back_every_file_and_records_the_failure(self):
        with patch.object(service, 'launch', side_effect=lambda a: (_ for _ in ()).throw(ValueError('start failed')) if a == 'start' else None):
            with self.assertRaisesRegex(ValueError, 'start failed'):
                service.manage('install')
        self.assertFalse(service.PENDING.exists())
        self.assertFalse(service.PLIST.exists())
        self.assertFalse((service.RUNTIME / 'bridge.py').exists())
        records = list((self.state / 'service-transactions').glob('*.json'))
        self.assertEqual(json.loads(records[0].read_text())['status'], 'rolled-back')

    def test_changed_helper_is_never_removed(self):
        service.manage('install')
        helper = service.RUNTIME / 'bridge.py'; helper.write_text('unrelated change')
        with self.assertRaisesRegex(ValueError, 'changed unexpectedly'):
            service.manage('remove')
        self.assertEqual(helper.read_text(), 'unrelated change')


if __name__ == '__main__':
    unittest.main()
