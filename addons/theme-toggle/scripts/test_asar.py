import json
import struct
import tempfile
import unittest
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive, digest


def make(path, tree, data):
    header = json.dumps(tree).encode()
    payload = struct.pack('<I', len(header)) + header
    payload += b'\0' * (-len(payload) % 4)
    pickle = struct.pack('<I', len(payload)) + payload
    path.write_bytes(struct.pack('<II', 4, len(pickle)) + pickle + data)


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
            make(original, tree, data + b'old')
            archive = Archive(original)
            new_hash = archive.rewrite(rewritten, {'edit.txt': b'new content', 'assets/module.mjs': b'export const ready = true;'})
            result = Archive(rewritten)
            self.assertEqual(result.read('keep.bin'), data)
            self.assertEqual(result.read('edit.txt'), b'new content')
            self.assertEqual(result.read('assets/module.mjs'), b'export const ready = true;')
            self.assertEqual(result.node('native.node'), tree['files']['native.node'])
            self.assertEqual(result.node('alias'), tree['files']['alias'])
            self.assertEqual(result.node('edit.txt')['integrity']['hash'], digest(result.read('edit.txt')))
            self.assertEqual(new_hash, digest(result.header_bytes))

    def test_removal_deletes_only_named_entries_and_prunes_emptied_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, added, removed = (Path(tmp) / name for name in ('base.asar', 'added.asar', 'removed.asar'))
            make(base, {'files': {'keep.txt': {'offset': '0', 'size': 4}, 'assets': {'files': {'host.js': {'offset': '4', 'size': 3}}}}}, b'keepabc')
            Archive(base).rewrite(added, {'assets/addon/ui.mjs': b'ui', 'assets/addon/host.mjs': b'host'})
            self.assertEqual(Archive(added).read('assets/addon/ui.mjs'), b'ui')
            Archive(added).rewrite(removed, {}, ['assets/addon/ui.mjs', 'assets/addon/host.mjs'])
            result = Archive(removed)
            self.assertEqual(result.read('keep.txt'), b'keep')
            self.assertEqual(result.read('assets/host.js'), b'abc')
            with self.assertRaises(KeyError):
                result.node('assets/addon')

    def test_removal_of_missing_entry_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp) / 'base.asar'
            make(base, {'files': {'keep.txt': {'offset': '0', 'size': 4}}}, b'keep')
            with self.assertRaises(ValueError):
                Archive(base).rewrite(Path(tmp) / 'out.asar', {}, ['missing/file.js'])


if __name__ == '__main__':
    unittest.main()
