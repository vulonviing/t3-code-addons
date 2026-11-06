"""Exercise recovery using disposable bundles, never an installed application."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.dont_write_bytecode = True
from lifecycle import Transaction, inventory, write_json


class TransactionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.app = self.root / 'App.app'
        self.candidate = self.root / 'Candidate.app'
        for folder, value in ((self.app, 'original'), (self.candidate, 'prepared')):
            folder.mkdir()
            (folder / 'data').write_text(value)
        self.receipt = self.root / 'receipt.json'
        write_json(self.receipt, {'old': True})
        self.tx = Transaction(self.root / 'state')

    def start(self):
        return self.tx.start(self.app, self.candidate, self.receipt, {'new': True}, {'action': 'test'})

    def test_commit_records_every_change_and_retains_previous(self):
        record = self.start()
        self.tx.execute(lambda app: None)
        self.assertEqual((self.app / 'data').read_text(), 'prepared')
        self.assertEqual((Path(record['previous']) / 'data').read_text(), 'original')
        self.assertEqual(json.loads(self.receipt.read_text()), {'new': True})
        self.assertFalse(self.tx.pending.exists())
        saved = json.loads((self.tx.state / 'transactions' / (record['id'] + '.json')).read_text())
        self.assertEqual(saved['status'], 'committed')
        self.assertEqual(saved['changes'][0]['path'], 'data')

    def test_failed_verification_rolls_back_without_deleting_candidate(self):
        self.start()
        def reject(app):
            raise ValueError('signature failed')
        with self.assertRaises(ValueError):
            self.tx.execute(reject)
        self.assertEqual((self.app / 'data').read_text(), 'original')
        self.assertEqual((self.candidate / 'data').read_text(), 'prepared')
        self.assertEqual(json.loads(self.receipt.read_text()), {'old': True})

    def test_interrupted_swaps_recover_at_each_write_boundary(self):
        # Interrupt before either rename and before/after either journal update.
        for fail_at in range(1, 5):
            with self.subTest(fail_at=fail_at), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                app, candidate = root / 'app', root / 'candidate'
                for folder, value in ((app, 'old'), (candidate, 'new')):
                    folder.mkdir(); (folder / 'file').write_text(value)
                receipt = root / 'receipt.json'
                write_json(receipt, {'old': True})
                tx = Transaction(root / 'state')
                tx.start(app, candidate, receipt, {'new': True}, {})
                count = 0
                real_rename, real_write = os.rename, write_json
                def step(function, *args):
                    nonlocal count
                    count += 1
                    if count == fail_at:
                        raise RuntimeError('simulated process exit')
                    return function(*args)
                with patch('lifecycle.os.rename', side_effect=lambda *args: step(real_rename, *args)), patch('lifecycle.write_json', side_effect=lambda *args: step(real_write, *args)):
                    with self.assertRaises(RuntimeError):
                        tx.execute(lambda app: None)
                tx.recover(lambda app: None)
                installed = (app / 'file').read_text()
                self.assertIn(installed, ('old', 'new'))
                self.assertEqual(json.loads(receipt.read_text()), {installed: True})
                self.assertFalse(tx.pending.exists())

    def test_changed_bundle_blocks_execution_and_recovery(self):
        self.start()
        (self.app / 'unrelated').write_text('preserve me')
        with self.assertRaises(ValueError):
            self.tx.execute(lambda app: None)
        with self.assertRaises(ValueError):
            self.tx.recover(lambda app: None)
        self.assertEqual((self.app / 'unrelated').read_text(), 'preserve me')

    def test_pending_transaction_blocks_second_start(self):
        self.start()
        with self.assertRaises(ValueError):
            self.start()

    def test_receipt_failure_can_be_recovered_after_install(self):
        self.start()
        with patch.object(self.tx, '_commit_receipt', side_effect=OSError('disk full')):
            with self.assertRaises(OSError):
                self.tx.execute(lambda app: None)
        self.tx.recover(lambda app: None)
        self.assertEqual(json.loads(self.receipt.read_text()), {'new': True})

    def test_repeated_recovery_is_a_noop(self):
        self.start(); self.tx.execute(lambda app: None)
        self.assertEqual(self.tx.recover(lambda app: None), 'No unfinished transaction.')

    def test_removal_archives_receipt(self):
        self.tx.start(self.app, self.candidate, self.receipt, None, {'action': 'restore'})
        self.tx.execute(lambda app: None)
        self.assertFalse(self.receipt.exists())
        self.assertEqual(len(list((self.tx.state / 'transactions').glob('*-receipt.json'))), 1)

    def test_inventory_detects_permissions_and_symlink_changes(self):
        (self.app / 'alias').symlink_to('data')
        before = inventory(self.app)
        (self.app / 'data').chmod(0o700)
        self.assertNotEqual(inventory(self.app), before)
        (self.app / 'alias').unlink()
        (self.app / 'alias').symlink_to('missing')
        self.assertEqual(inventory(self.app)['alias']['target'], 'missing')


if __name__ == '__main__':
    unittest.main()
