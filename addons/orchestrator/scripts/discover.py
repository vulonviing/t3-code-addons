#!/usr/bin/env python3
"""Discover the T3 client modules this addon imports and render the host adapter for them.

T3 ships minified, hashed chunks, so neither chunk names nor export aliases are stable across releases. Each module is
identified by how the rest of the client uses it (for example `X.threadShellAtom(...)`), following the import chain to
the chunk export that actually provides it. Results are generated at install time, never pinned. A binding that cannot
be found is reported by name; the rendered adapter then carries no import for it and the UI explains the problem.

Usage: discover.py <client assets directory> [--adapter]
"""
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parents[1]
ID = r'[A-Za-z_$][\w$]*'
IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*["\']\./([\w.\-]+\.js)["\']')
EXPORT = re.compile(r'export\s*\{([^}]*)\}\s*;?\s*(?://# sourceMappingURL=\S*\s*)?$')
SAFE_CHUNK = re.compile(r'^[A-Za-z0-9_.-]+\.js$')
SAFE_ALIAS = re.compile(r'^' + ID + '$')
MARKERS = ('data-chat-composer-form', 'data-chat-composer-footer')
BEFORE = r'(?<![\w$.])(' + ID + ')'

# name -> (usage pattern capturing the local name, required text in the providing chunk, description)
BINDINGS = {
    'registry': (r'registry:(' + ID + ')', 'registry', 'the atom registry'),
    'draftStore': (BEFORE + r'\.getState\(\)\.(?:getDraftSession|markDraftThreadPromoting|finalizePromotedDraftThread)\b',
                   'markDraftThreadPromoting', 'the new-chat draft store'),
    'orchestration': (BEFORE + r'\.v2\.(?:dispatchCommand|commandOutput|promptSuggestion)\b', 'v2:{dispatchCommand:',
                      'the orchestration command client'),
    'details': (BEFORE + r'\.threadAtom\b', 'threadAtom', 'the chat detail atoms'),
    'shells': (BEFORE + r'\.threadShellAtom\b', 'threadShellAtom', 'the chat shell atoms'),
    'server': (BEFORE + r'\.configValueAtom\b', 'configValueAtom', 'the server configuration atoms'),
    'hasScope': (BEFORE + r'\([\w$.]+,[`"\']orchestration:operate[`"\']\)', None, 'the permission check'),
}


class DiscoveryError(ValueError):
    pass


def pairs(body):
    result = []
    for item in body.split(','):
        parts = item.split()
        if len(parts) == 3 and parts[1] == 'as':
            result.append((parts[0], parts[2]))
        elif len(parts) == 1:
            result.append((parts[0], parts[0]))
    return result


def parse(assets):
    modules = {}
    for name, data in sorted(assets.items()):
        if not name.endswith('.js'):
            continue
        text = data.decode('utf-8', 'replace')
        imports = {}
        for match in IMPORT.finditer(text):
            for exported, local in pairs(match.group(1)):
                imports[local] = (match.group(2), exported)
        export = EXPORT.search(text.rstrip())
        exports = {alias: local for local, alias in pairs(export.group(1))} if export else {}
        modules[name] = {'text': text, 'imports': imports, 'exports': exports}
    return modules


def provider(modules, chunk, local):
    """Follow imported bindings to the last chunk export on the way; None when `local` is not imported."""
    last, seen = None, set()
    while (chunk, local) not in seen and local in modules.get(chunk, {}).get('imports', {}):
        seen.add((chunk, local))
        chunk, alias = modules[chunk]['imports'][local]
        last = (chunk, alias)
        local = modules.get(chunk, {}).get('exports', {}).get(alias)
        if local is None:
            break
    return last


def find(modules, pattern, required):
    votes = Counter()
    for name, module in modules.items():
        for match in re.finditer(pattern, module['text']):
            found = provider(modules, name, match.group(1))
            if found and (required is None or required in modules.get(found[0], {}).get('text', '')):
                votes[found] += 1
    ranked = votes.most_common(2)
    if not ranked:
        return None
    if len(ranked) > 1 and ranked[0][1] == ranked[1][1]:
        return 'ambiguous'
    return ranked[0][0]


def discover(assets):
    """assets: mapping of top-level client asset file name to bytes. Never raises for a missing binding.

    Returns {'bindings': {name: {'chunk', 'alias'}}, 'missing': [description, ...], 'chunkSha256': {chunk: sha256}}.
    """
    modules = parse(assets)
    text = ''.join(module['text'] for module in modules.values())
    missing = [f'composer marker {marker}' for marker in MARKERS if marker not in text]
    bindings = {}
    for name, (pattern, required, description) in BINDINGS.items():
        found = find(modules, pattern, required)
        if found == 'ambiguous':
            missing.append(f'{description} (ambiguous)')
        elif found is None:
            missing.append(description)
        elif not SAFE_CHUNK.match(found[0]) or not SAFE_ALIAS.match(found[1]):
            missing.append(f'{description} (unexpected export name)')
        else:
            bindings[name] = {'chunk': found[0], 'alias': found[1]}
    hashes = {b['chunk']: hashlib.sha256(assets[b['chunk']]).hexdigest() for b in bindings.values()}
    return {'bindings': bindings, 'missing': missing, 'chunkSha256': hashes}


def render_adapter(found):
    chunks = sorted({b['chunk'] for b in found['bindings'].values()})
    imports = ''.join(f"import * as c{i} from '../{chunk}';\n" for i, chunk in enumerate(chunks))
    table = ', '.join(f"{name}: c{chunks.index(b['chunk'])}['{b['alias']}']" for name, b in sorted(found['bindings'].items()))
    template = (ROOT / 'src/host.template').read_text()
    return (template.replace('@@IMPORTS@@\n', imports).replace('@@BINDINGS@@', '{ ' + table + ' }')
            .replace('@@MISSING@@', json.dumps(found['missing'])))


def load_directory(directory):
    return {path.name: path.read_bytes() for path in sorted(Path(directory).glob('*.js'))}


if __name__ == '__main__':
    try:
        record = discover(load_directory(sys.argv[1]))
        print(render_adapter(record) if '--adapter' in sys.argv[2:] else json.dumps(record, indent=1))
    except (IndexError, OSError) as error:
        print('Discovery failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
