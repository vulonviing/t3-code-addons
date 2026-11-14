#!/usr/bin/env python3
"""Discover T3's composer draft store in a client bundle and render the host adapter for it.

T3 ships minified, hashed chunks, so neither the chunk name nor its export alias is stable across releases. The draft
store is identified by what it is: a module that defines an object with `getComposerDraft` and `setPrompt` actions and
exports that object. The result is generated, never pinned.

Usage: discover.py <client assets directory> [--adapter]
"""
import hashlib
import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
SELECTORS = ('data-chat-composer-form', 'data-chat-composer-footer', 'data-chat-composer-actions')
IDENT = r'[A-Za-z_$][\w$]*'
GET_DEF = re.compile(r'[,{]getComposerDraft:(?:\(?[\w$,\s]*\)?=>|function)')
SET_DEF = re.compile(r'[,{]setPrompt:(?:\(?[\w$,\s]*\)?=>|function)')
EXPORT = re.compile(r'export\s*\{([^}]*)\}\s*;?\s*(?://# sourceMappingURL=\S*\s*)?$')
SAFE_CHUNK = re.compile(r'^[A-Za-z0-9_.-]+\.js$')
SAFE_ALIAS = re.compile(r'^' + IDENT + '$')


class DiscoveryError(ValueError):
    pass


def exports(text):
    """Return [(local, alias)] from the module's final export list."""
    match = EXPORT.search(text.rstrip())
    if not match:
        return []
    pairs = []
    for item in match.group(1).split(','):
        parts = item.split()
        if len(parts) == 3 and parts[1] == 'as':
            pairs.append((parts[0], parts[2]))
        elif len(parts) == 1:
            pairs.append((parts[0], parts[0]))
    return pairs


ALIAS_ASSIGN = re.compile(r'[,;\s](' + IDENT + r')=(' + IDENT + r')(?=[;,)])')
DECLARATION = re.compile(r'(?<![\w$.])(' + IDENT + r')=(?![=>])')


def store_alias(text):
    """Export alias of the object defining both draft actions, or None when this module is not the store."""
    get, put = GET_DEF.search(text), SET_DEF.search(text)
    pairs = exports(text)
    if not (get and put and pairs):
        return None
    assigned = dict(ALIAS_ASSIGN.findall(text))

    def origin(name):
        # Follow plain `a=b;` re-assignments back to the name that was created.
        seen = set()
        while name in assigned and name not in seen:
            seen.add(name)
            name = assigned[name]
        return name

    owners = {}
    for local, alias in pairs:
        owners.setdefault(origin(local), alias)
    # The store is the nearest exported declaration preceding its action definitions.
    best = None
    for match in DECLARATION.finditer(text, 0, get.start()):
        if match.group(1) in owners:
            best = match.group(1)
    return owners.get(best)


def discover(assets):
    """assets: mapping of top-level client asset file name to bytes. Returns the discovery record."""
    text = ''.join(data.decode('utf-8', 'replace') for name, data in sorted(assets.items()) if name.endswith('.js'))
    missing = [s for s in SELECTORS if s not in text]
    if missing:
        raise DiscoveryError('The T3 client no longer contains the composer markers this addon positions itself by: '
                             + ', '.join(missing) + '.')
    found = []
    for name, data in sorted(assets.items()):
        if not name.endswith('.js') or b'getComposerDraft' not in data or b'setPrompt' not in data:
            continue
        alias = store_alias(data.decode('utf-8', 'replace'))
        if alias:
            found.append((name, alias, data))
    if not found:
        raise DiscoveryError('Could not find the T3 composer draft store (a module exporting an object with '
                             'getComposerDraft and setPrompt). This T3 release is not supported by this addon.')
    if len(found) > 1:
        raise DiscoveryError('Ambiguous T3 draft store: ' + ', '.join(name for name, _, _ in found) + '.')
    name, alias, data = found[0]
    if not SAFE_CHUNK.match(name) or not SAFE_ALIAS.match(alias):
        raise DiscoveryError('Discovered an unexpected chunk name or export alias.')
    return {'chunk': name, 'alias': alias, 'chunkSha256': hashlib.sha256(data).hexdigest()}


def render_adapter(found):
    template = (ROOT / 'src/host.template').read_text()
    return template.replace('@@CHUNK@@', found['chunk']).replace('@@ALIAS@@', found['alias'])


def load_directory(directory):
    return {path.name: path.read_bytes() for path in sorted(Path(directory).glob('*.js'))}


if __name__ == '__main__':
    try:
        record = discover(load_directory(sys.argv[1]))
        print(render_adapter(record) if '--adapter' in sys.argv[2:] else json.dumps(record))
    except (DiscoveryError, IndexError, OSError) as error:
        print('Discovery failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
