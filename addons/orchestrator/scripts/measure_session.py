#!/usr/bin/env python3
"""Count subagent spawns, models and tokens for one Claude Code session log.

Usage: measure_session.py <session.jsonl>
Prints a JSON report to stdout and writes nothing. Subagent logs are read from
the sibling `<session>/subagents/agent-*.jsonl` files when they exist.
"""
import json
import sys
from collections import Counter
from pathlib import Path

TOKEN_FIELDS = {'input': 'input_tokens', 'output': 'output_tokens',
                'cache_read': 'cache_read_input_tokens', 'cache_write': 'cache_creation_input_tokens'}


def records(path):
    with open(path, encoding='utf-8') as handle:
        for raw in handle:
            try:
                yield json.loads(raw)
            except ValueError:
                continue


def read_log(path, spawns, counters):
    """Return (tokens, models) for one log; the last record per message id wins."""
    seen = {}
    for number, record in enumerate(records(path)):
        message = record.get('message')
        if not isinstance(message, dict) or message.get('role') != 'assistant':
            continue
        seen[message.get('id') or f'line-{number}'] = message
        for block in message.get('content') if isinstance(message.get('content'), list) else []:
            if block.get('type') != 'tool_use':
                continue
            name, data = block.get('name'), block.get('input') or {}
            if name == 'Agent':
                spawns['native'][data.get('model') or 'inherited'] += 1
            elif name and name.endswith('delegate_task'):
                spawns['delegate_task'][(data.get('target') or {}).get('model') or 'unspecified'] += 1
            elif name == 'SendMessage':
                counters['send_message'] += 1
    tokens, models = Counter(), Counter()
    for message in seen.values():
        usage = message.get('usage') or {}
        for key, field in TOKEN_FIELDS.items():
            tokens[key] += usage.get(field) or 0
        if usage and message.get('model'):
            models[message['model']] += 1
    return tokens, models


def main(session):
    session = Path(session)
    spawns = {'native': Counter(), 'delegate_task': Counter()}
    counters = Counter()
    main_tokens, main_models = read_log(session, spawns, counters)
    sub_tokens, sub_models = Counter(), Counter()
    files = sorted((session.with_suffix('') / 'subagents').glob('agent-*.jsonl'))
    for path in files:
        tokens, models = read_log(path, spawns, counters)
        sub_tokens.update(tokens)
        if models:
            sub_models[models.most_common(1)[0][0]] += 1
    total = main_tokens + sub_tokens
    json.dump({
        'spawns': {kind: dict(sorted(count.items())) for kind, count in spawns.items()},
        'send_message': counters['send_message'],
        'subagent_files': len(files),
        'subagent_models': dict(sorted(sub_models.items())),
        'main': {'models': dict(sorted(main_models.items())), 'tokens': dict(main_tokens)},
        'subagents': {'tokens': dict(sub_tokens)},
        'total_tokens': dict(total),
    }, sys.stdout, indent=2)
    print()


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('usage: measure_session.py <session.jsonl>')
    main(sys.argv[1])
