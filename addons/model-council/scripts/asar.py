"""Small ASAR reader/writer; preserves untouched files and unpacked entries."""
import copy
import hashlib
import json
import struct
from pathlib import Path


def digest(data):
    return hashlib.sha256(data).hexdigest()


class Archive:
    def __init__(self, path):
        self.path = Path(path)
        with self.path.open('rb') as stream:
            sizes = struct.unpack('<4I', stream.read(16))
            if sizes[0] != 4 or sizes[1] < sizes[3] + 8:
                raise ValueError('Unsupported ASAR header')
            self.header_bytes = stream.read(sizes[3])
            self.header = json.loads(self.header_bytes)
            self.base = 8 + sizes[1]

    def node(self, path):
        node = self.header
        for part in path.split('/'):
            node = node['files'][part]
        return node

    def read(self, path):
        node = self.node(path)
        if node.get('unpacked'):
            return Path(str(self.path) + '.unpacked', path).read_bytes()
        with self.path.open('rb') as stream:
            stream.seek(self.base + int(node['offset']))
            return stream.read(node['size'])

    def rewrite(self, output, replacements):
        tree = copy.deepcopy(self.header)
        for path in replacements:
            node = tree
            parts = path.split('/')
            for part in parts[:-1]:
                node = node.setdefault('files', {}).setdefault(part, {'files': {}})
            node.setdefault('files', {}).setdefault(parts[-1], {})
        entries = []

        def walk(node, prefix=''):
            for name, value in node.get('files', {}).items():
                path = f'{prefix}/{name}' if prefix else name
                if 'files' in value:
                    walk(value, path)
                elif not value.get('unpacked') and 'link' not in value:
                    entries.append((path, value))

        walk(tree)
        offset = 0
        block = 4 * 1024 * 1024
        for path, node in entries:
            if path in replacements:
                data = replacements[path]
                node.update(size=len(data), integrity={
                    'algorithm': 'SHA256', 'hash': digest(data), 'blockSize': block,
                    'blocks': [digest(data[i:i + block]) for i in range(0, len(data), block)],
                })
            node['offset'] = str(offset)
            offset += node['size']
        header = json.dumps(tree, ensure_ascii=False, separators=(',', ':')).encode()
        payload = struct.pack('<I', len(header)) + header
        payload += b'\0' * (-len(payload) % 4)
        header_pickle = struct.pack('<I', len(payload)) + payload
        with self.path.open('rb') as source, Path(output).open('wb') as target:
            target.write(struct.pack('<II', 4, len(header_pickle)))
            target.write(header_pickle)
            for path, node in entries:
                if path in replacements:
                    target.write(replacements[path])
                else:
                    original = self.node(path)
                    source.seek(self.base + int(original['offset']))
                    remaining = original['size']
                    while remaining:
                        chunk = source.read(min(remaining, block))
                        if not chunk:
                            raise ValueError(f'Truncated ASAR entry: {path}')
                        target.write(chunk)
                        remaining -= len(chunk)
        return digest(header)
