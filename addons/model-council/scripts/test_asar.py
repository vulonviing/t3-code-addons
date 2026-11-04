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


if __name__ == '__main__':
    unittest.main()
