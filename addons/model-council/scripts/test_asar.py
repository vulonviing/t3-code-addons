import json
import struct
import tempfile
import unittest
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest


class ArchiveTests(unittest.TestCase):
    def test_rewrite_preserves_original_bytes_links_and_unpacked_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, rewritten = Path(tmp) / 'app.asar', Path(tmp) / 'new.asar'
            data = b'original-content\0\xff'
            tree = {'files': {
                'keep.bin': {'offset': '0', 'size': len(data)},
                'edit.txt': {'offset': str(len(data)), 'size': 3},
                'native.node': {'unpacked': True, 'size': 5},
                'alias': {'link': 'keep.bin'},
            }}
            header = json.dumps(tree).encode()
            payload = struct.pack('<I', len(header)) + header
            payload += b'\0' * (-len(payload) % 4)
            pickle = struct.pack('<I', len(payload)) + payload
            original.write_bytes(struct.pack('<II', 4, len(pickle)) + pickle + data + b'old')
            archive = Archive(original)
            new_hash = archive.rewrite(rewritten, {'edit.txt': 'new content'.encode(), 'assets/module.mjs': b'export const ready = true;'})
            result = Archive(rewritten)
            self.assertEqual(result.read('keep.bin'), data)
            self.assertEqual(result.read('edit.txt'), 'new content'.encode())
            self.assertEqual(result.read('assets/module.mjs'), b'export const ready = true;')
            self.assertEqual(result.node('native.node'), tree['files']['native.node'])
            self.assertEqual(result.node('alias'), tree['files']['alias'])
            self.assertEqual(result.node('edit.txt')['integrity']['hash'], digest(result.read('edit.txt')))
            self.assertEqual(new_hash, digest(result.header_bytes))

    def test_removal_deletes_only_the_named_entries_and_prunes_emptied_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            original, rewritten = Path(tmp) / 'app.asar', Path(tmp) / 'new.asar'
            header = json.dumps({'files': {}}).encode()
            payload = struct.pack('<I', len(header)) + header
            payload += b'\0' * (-len(payload) % 4)
            pickle = struct.pack('<I', len(payload)) + payload
            original.write_bytes(struct.pack('<II', 4, len(pickle)) + pickle)
            Archive(original).rewrite(original, {'a/own/one.mjs': b'1', 'a/own/two.mjs': b'2', 'a/other/x.mjs': b'x', 'keep.txt': b'k'})
            Archive(original).rewrite(rewritten, {}, ['a/own/one.mjs', 'a/own/two.mjs'])
            result = Archive(rewritten)
            self.assertEqual(result.read('a/other/x.mjs'), b'x')
            self.assertEqual(result.read('keep.txt'), b'k')
            for gone in ('a/own/one.mjs', 'a/own'):
                with self.assertRaises(KeyError):
                    result.node(gone)
            with self.assertRaises(ValueError):
                Archive(original).rewrite(rewritten, {}, ['missing.txt'])


if __name__ == '__main__':
    unittest.main()
