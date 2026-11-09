#!/usr/bin/env python3
"""Extract the installed application's client assets into an external directory for host verification."""
import sys
from pathlib import Path

sys.dont_write_bytecode = True
from asar import Archive

PREFIX = 'apps/server/dist/client/'


def main():
    if len(sys.argv) != 3:
        raise SystemExit('Usage: extract_client.py "/path/to/T3 Code (Beta).app" /external/empty/directory')
    archive = Archive(Path(sys.argv[1]) / 'Contents/Resources/app.asar')
    output = Path(sys.argv[2])
    if output.exists() and any(output.iterdir()):
        raise SystemExit('Output directory must be empty.')

    resolved_output = output.resolve()

    def walk(node, prefix=''):
        for name, value in node.get('files', {}).items():
            if name in ('', '.', '..') or '/' in name or '\\' in name or '\0' in name:
                raise SystemExit(f'Unsafe archive entry name {name!r} under {prefix or "<root>"}; nothing was written for it.')
            path = f'{prefix}/{name}' if prefix else name
            if 'files' in value:
                walk(value, path)
            elif path.startswith(PREFIX) and 'link' not in value and not value.get('unpacked'):
                target = output / path[len(PREFIX):]
                if resolved_output not in target.resolve().parents:
                    raise SystemExit(f'Archive entry {path!r} resolves outside the output directory; nothing was written for it.')
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(path))

    walk(archive.header)
    print(f'Extracted client assets to {output}')


if __name__ == '__main__':
    main()
