#!/usr/bin/env python3
"""Discover T3's theme module in a client bundle and render the host adapter for it.

T3 ships minified, hashed chunks, so neither chunk names nor export aliases are stable across releases. The theme
module is recognized by what it contains: the external-store subscribe helper that returns one combined unsubscribe,
the zero-argument snapshot accessor placed directly before it, and the appearance-mode setter that suppresses theme
transitions. Nothing is pinned and no version is consulted. Discovery never raises for an unsupported client; it
returns an `unattached` record whose reason the addon shows at runtime.

Usage: discover.py <client assets directory> [--adapter]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
IDENT = r'[A-Za-z_$][\w$]*'
SUBSCRIBE = re.compile(r'function (' + IDENT + r')\((' + IDENT + r')\)\{let (' + IDENT + r')=(' + IDENT + r')\(\2\),('
                       + IDENT + r')=(' + IDENT + r')\(\2\);return\(\)=>\{\3\(\),\5\(\)\}\}')
EXPORT = re.compile(r'export\s*\{([^}]*)\}\s*;?\s*(?://# sourceMappingURL=\S*\s*)?$')
SAFE_CHUNK = re.compile(r'^[A-Za-z0-9_.-]+\.js$')
SAFE_ALIAS = re.compile(r'^' + IDENT + '$')


def exports(text):
    match = EXPORT.search(text.rstrip())
    result = {}
    for item in (match.group(1).split(',') if match else []):
        parts = item.split()
        if len(parts) == 3 and parts[1] == 'as':
            result.setdefault(parts[0], parts[2])
        elif len(parts) == 1:
            result.setdefault(parts[0], parts[0])
    return result


def inspect(text):
    """Export aliases of the three theme functions, or None when this module is not the theme module."""
    for match in SUBSCRIBE.finditer(text):
        subscribe = match.group(1)
        snapshot = re.search(r'function (' + IDENT + r')\(\)\{return ' + IDENT + r'\(\)\}function ' + re.escape(subscribe) + r'\(', text)
        setter = re.findall(r'function (' + IDENT + r')\((' + IDENT + r')\)\{if\(typeof window>`u`\)return!1;try\{' + IDENT
                            + r'\(\2\)\}catch\(.{0,300}?suppressTransitions:!0\}\)', text)
        if not snapshot or len(setter) != 1:
            continue
        table = exports(text)
        names = {'snapshot': snapshot.group(1), 'setAppearanceMode': setter[0][0], 'subscribe': subscribe}
        if all(name in table for name in names.values()):
            return {key: table[name] for key, name in names.items()}
    return None


def discover(assets):
    """assets: mapping of top-level client asset file name to bytes."""
    found = []
    for name, data in sorted(assets.items()):
        if not name.endswith('.js') or b'suppressTransitions' not in data:
            continue
        symbols = inspect(data.decode('utf-8', 'replace'))
        if symbols:
            found.append((name, symbols, data))
    if not found:
        return {'status': 'unattached', 'reason': 'The theme module this addon attaches to was not found in this T3 release.'}
    if len(found) > 1:
        return {'status': 'unattached', 'reason': 'More than one candidate theme module was found in this T3 release.'}
    name, symbols, data = found[0]
    if not SAFE_CHUNK.match(name) or not all(SAFE_ALIAS.match(value) for value in symbols.values()):
        return {'status': 'unattached', 'reason': 'Discovered an unexpected chunk name or export alias.'}
    return {'status': 'attached', 'chunk': name, 'symbols': symbols, 'chunkSha256': hashlib.sha256(data).hexdigest()}


def render_adapter(found):
    if found['status'] == 'attached':
        preamble = (f"import * as chunk from '../{found['chunk']}';\n"
                    f"const symbols = {json.dumps(found['symbols'])};\nconst discoveryError = null;")
    else:
        preamble = f"const chunk = null;\nconst symbols = {{}};\nconst discoveryError = {json.dumps(found['reason'])};"
    return (ROOT / 'src/host.template').read_text().replace('// @@DISCOVERY@@', preamble)


def load_directory(directory):
    return {path.name: path.read_bytes() for path in sorted(Path(directory).glob('*.js'))}


if __name__ == '__main__':
    try:
        record = discover(load_directory(sys.argv[1]))
    except (IndexError, OSError) as error:
        print('Discovery failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
    print(render_adapter(record) if '--adapter' in sys.argv[2:] else json.dumps(record))
