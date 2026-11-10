import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name('measure_session.py')


def line(role, model=None, usage=None, content=None, mid=None):
    message = {'role': role, 'content': content if content is not None else []}
    if model: message['model'] = model
    if usage: message['usage'] = usage
    if mid: message['id'] = mid
    return json.dumps({'type': role, 'message': message})


def use(name, **inputs):
    return {'type': 'tool_use', 'name': name, 'input': inputs}


USAGE = {'input_tokens': 10, 'output_tokens': 5, 'cache_read_input_tokens': 100, 'cache_creation_input_tokens': 20}


class MeasureTest(unittest.TestCase):
    def run_script(self, session):
        result = subprocess.run([sys.executable, str(SCRIPT), str(session)], capture_output=True, text=True, check=True)
        return json.loads(result.stdout)

    def make_session(self, root):
        session = Path(root) / 'abc.jsonl'
        session.write_text('\n'.join([
            line('assistant', 'claude-opus-5-5', USAGE, [use('Agent', model='haiku'), use('Agent'), use('SendMessage', to='x')], mid='m1'),
            line('assistant', 'claude-opus-5-5', USAGE, [use('mcp__t3-code__delegate_task', target={'model': 'gpt-x'})], mid='m2'),
            line('user'),
        ]) + '\n')
        sub = Path(root) / 'abc' / 'subagents'
        sub.mkdir(parents=True)
        (sub / 'agent-1.jsonl').write_text(line('assistant', 'claude-sonnet-5-5', USAGE, mid='s1') + '\n')
        (sub / 'agent-1.meta.json').write_text(json.dumps({'model': 'sonnet'}))
        return session

    def test_counts_agents_models_and_tokens(self):
        with tempfile.TemporaryDirectory() as root:
            report = self.run_script(self.make_session(root))
        self.assertEqual(report['spawns']['native'], {'haiku': 1, 'inherited': 1})
        self.assertEqual(report['spawns']['delegate_task'], {'gpt-x': 1})
        self.assertEqual(report['send_message'], 1)
        self.assertEqual(report['subagent_files'], 1)
        self.assertEqual(report['subagent_models'], {'claude-sonnet-5-5': 1})
        self.assertEqual(report['main']['models'], {'claude-opus-5-5': 2})
        self.assertEqual(report['main']['tokens']['output'], 10)
        self.assertEqual(report['subagents']['tokens']['cache_read'], 100)
        self.assertEqual(report['total_tokens']['input'], 30)

    def test_repeated_message_ids_count_once(self):
        with tempfile.TemporaryDirectory() as root:
            session = Path(root) / 's.jsonl'
            session.write_text('\n'.join([line('assistant', 'm', USAGE, mid='same')] * 3) + '\n')
            report = self.run_script(session)
        self.assertEqual(report['main']['tokens']['output'], 5)

    def test_reports_no_subagents_dir(self):
        with tempfile.TemporaryDirectory() as root:
            session = Path(root) / 's.jsonl'
            session.write_text(line('assistant', 'm', USAGE, mid='a') + '\n')
            report = self.run_script(session)
        self.assertEqual(report['subagent_files'], 0)


if __name__ == '__main__':
    unittest.main()
