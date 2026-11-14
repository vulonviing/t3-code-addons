#!/usr/bin/env python3
"""Discover the T3 host modules Thread Details reads from, and render the host adapter for them.

T3 ships minified, hashed chunks, so chunk names and export aliases change between releases. Each module is
recognized by how the client uses it: the shared atom registry is the value handed to the registry context provider,
the thread-state object is the exported module value on which `.threadAtom(` is called, and the server-state object
is the exported value on which both `.configValueAtom(` and `.providersValueAtom(` are called. Nothing is pinned and
no version is consulted. Discovery never raises for an unsupported client; it returns an `unattached` record whose
reason the addon shows at runtime.

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
EXPORT = re.compile(r'export\s*\{([^}]*)\}\s*;?\s*(?://# sourceMappingURL=\S*\s*)?$')
PROVIDER = re.compile(r'(?<![\w$.])(' + IDENT + r')=' + IDENT + r'\(\);function ' + IDENT + r'\(\{children:e\}\)\{return\(0,'
                      + IDENT + r'\.createElement\)\(' + IDENT + r'\.Provider,\{value:\1\},e\)\}')
SAFE_CHUNK = re.compile(r'^[A-Za-z0-9_.-]+\.js$')
SAFE_ALIAS = re.compile(r'^' + IDENT + '$')
ROLES = ('registry', 'details', 'server')


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


def declared(text, name):
    return re.search(r'(?<![\w$.])' + re.escape(name) + r'=', text) is not None


def user_of(text, members):
    """Exported alias of the module-level value on which every member is called, or None."""
    table = exports(text)
    candidates = None
    for member in members:
        names = set(re.findall(r'(' + IDENT + r')\.' + member + r'\(', text))
        candidates = names if candidates is None else candidates & names
    aliases = sorted({table[name] for name in candidates or () if name in table and declared(text, name)})
    return aliases[0] if len(aliases) == 1 else None


def inspect(text):
    """Role -> export alias for whichever roles this module provides."""
    table = exports(text)
    roles = {}
    if b'threadAtom' in text.encode():
        alias = user_of(text, ['threadAtom'])
        if alias:
            roles['details'] = alias
    if 'configValueAtom' in text and 'providersValueAtom' in text:
        alias = user_of(text, ['configValueAtom', 'providersValueAtom'])
        if alias:
            roles['server'] = alias
    registries = {table[m.group(1)] for m in PROVIDER.finditer(text) if m.group(1) in table}
    if len(registries) == 1:
        roles['registry'] = next(iter(registries))
    return roles


def discover(assets):
    """assets: mapping of top-level client asset file name to bytes."""
    found = {role: [] for role in ROLES}
    for name, data in sorted(assets.items()):
        if not name.endswith('.js') or not (b'threadAtom' in data or b'configValueAtom' in data or b'.Provider,{value:' in data):
            continue
        for role, alias in inspect(data.decode('utf-8', 'replace')).items():
            found[role].append((name, alias, data))
    problems = [role for role in ROLES if len(found[role]) != 1]
    if problems:
        why = ', '.join(role + (' not found' if not found[role] else ' ambiguous') for role in problems)
        return {'status': 'unattached', 'reason': 'T3 host modules could not be identified (' + why + ').'}
    parts = {role: {'chunk': found[role][0][0], 'alias': found[role][0][1],
                    'chunkSha256': hashlib.sha256(found[role][0][2]).hexdigest()} for role in ROLES}
    if not all(SAFE_CHUNK.match(p['chunk']) and SAFE_ALIAS.match(p['alias']) for p in parts.values()):
        return {'status': 'unattached', 'reason': 'Discovered an unexpected chunk name or export alias.'}
    return {'status': 'attached', 'chunks': sorted({p['chunk'] for p in parts.values()}), 'parts': parts}


def render_adapter(found):
    if found['status'] == 'attached':
        lines = [f"import * as {role}Chunk from '../{found['parts'][role]['chunk']}';" for role in ROLES]
        lines += [f"const {role} = {role}Chunk[{json.dumps(found['parts'][role]['alias'])}];" for role in ROLES]
        lines.append('const discoveryError = null;')
    else:
        lines = [f'const {role} = null;' for role in ROLES] + [f"const discoveryError = {json.dumps(found['reason'])};"]
    return (ROOT / 'src/host.template').read_text().replace('// @@DISCOVERY@@', '\n'.join(lines))


def load_directory(directory):
    return {path.name: path.read_bytes() for path in sorted(Path(directory).glob('*.js'))}


if __name__ == '__main__':
    try:
        record = discover(load_directory(sys.argv[1]))
    except (IndexError, OSError) as error:
        print('Discovery failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
    print(render_adapter(record) if '--adapter' in sys.argv[2:] else json.dumps(record))
