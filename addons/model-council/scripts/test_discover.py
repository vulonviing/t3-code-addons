"""Client-module discovery against small synthetic layouts of T3 0.1.7 and 0.1.9, a failure case, and optional real extracts."""
import os
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import discover

MARKERS = 'x="data-chat-composer-form data-chat-composer-footer"'


def module(imports='', body='', exports=''):
    return f'{imports}{body}export{{{exports}}};'


def layout(names):
    """Synthetic client: provider chunks export the objects; consumer chunks use them through imports.

    `names` maps each binding to (chunk, alias, local name in the provider) so the two releases can differ.
    """
    files = {'_chat-X.js': MARKERS, 'rolldown-runtime-R.js': 'var i=1;export{i};'}
    imports, uses = [], []
    for index, (key, (chunk, alias, local)) in enumerate(names.items()):
        used = f'u{index}'
        imports.append(f'import{{{alias} as {used}}}from"./{chunk}";')
        uses.append({
            'registry': f'f({{registry:{used}}});',
            'draftStore': f'{used}.getState().getDraftSession(1);{used}.getState().markDraftThreadPromoting(1);',
            'orchestration': f'{used}.v2.commandOutput({{}});',
            'details': f'{used}.threadAtom(e);',
            'shells': f'{used}.threadShellAtom(e);',
            'server': f'{used}.configValueAtom(e);',
            'hasScope': f'{used}(e.environmentId,`orchestration:operate`);{used}(n,`orchestration:operate`);',
            'dateTime': f'{used}(e);',
        }[key])
        provider_body = {
            'registry': f'var {local}={{get(){{}},subscribe(){{}}}};/*registry*/',
            'draftStore': f'var {local}={{getState:()=>({{getDraftSession:1,markDraftThreadPromoting:1}})}};',
            'orchestration': f'var {local}={{v2:{{dispatchCommand:1,commandOutput:2}}}};',
            'details': f'var {local}={{threadAtom:1}};',
            'shells': f'var {local}={{threadShellAtom:1}};',
            'server': f'var {local}={{configValueAtom:1}};',
            'hasScope': f'function {local}(){{}}',
            'dateTime': f'var Tag=`~effect/DateTime`,Ul=e=>e,{local}=e=>{{if(Ul(e))return e;if(e instanceof Date)return 1;return 2}},{local}2={local};',
        }[key]
        text = files.get(chunk, '')
        files[chunk] = text.rsplit('export{', 1)[0] + provider_body + 'export{' + (text.rsplit('export{', 1)[1][:-2] + ',' if 'export{' in text else '') + f'{local} as {alias}}};'
    files['consumer-A.js'] = ''.join(imports) + 'function f(){}' + ''.join(uses) + 'export{f as a};'
    files['consumer-B.js'] = ''.join(imports) + ''.join(uses) + 'export{};'
    return {name: text.encode() for name, text in files.items()}


R17 = {'registry': ('utils-AAAA.js', 'al', 'q1'), 'draftStore': ('utils-AAAA.js', 'A', 'q2'),
       'orchestration': ('queries-BBBB.js', 'v', 'q3'), 'details': ('projectGrouping-CCCC.js', 'rt', 'q4'),
       'shells': ('projectGrouping-CCCC.js', 'it', 'q5'), 'server': ('themePalette-DDDD.js', 'ut', 'q6'),
       'hasScope': ('session-EEEE.js', 'r', 'q7'), 'dateTime': ('utils-AAAA.js', 'nS', 'qf')}
# 0.1.9 moved the chat atoms to another chunk and renamed aliases.
R19 = {'registry': ('utils-FFFF.js', 'yl', 'q1'), 'draftStore': ('utils-FFFF.js', 'A', 'q2'),
       'orchestration': ('orchestration-GGGG.js', 't', 'q3'), 'details': ('entities-HHHH.js', 'J', 'q4'),
       'shells': ('entities-HHHH.js', 'Y', 'q5'), 'server': ('themePalette-IIII.js', 'dt', 'q6'),
       'hasScope': ('session-JJJJ.js', 'r', 'q7'), 'dateTime': ('utils-FFFF.js', 'XS', 'bh')}


class DiscoveryTests(unittest.TestCase):
    def check_layout(self, names):
        found = discover.discover(layout(names))
        self.assertEqual(found['missing'], [])
        self.assertEqual({k: (v['chunk'], v['alias']) for k, v in found['bindings'].items()},
                         {k: (c, a) for k, (c, a, _) in names.items()})
        adapter = discover.render_adapter(found)
        self.assertNotIn('@@', adapter)
        for chunk, alias, _ in names.values():
            self.assertIn(f"import * as", adapter)
            self.assertIn(f"['{alias}']", adapter)
            self.assertIn(f"'../{chunk}'", adapter)
        self.assertIn('const MISSING = [];', adapter)

    def test_t3_017_layout(self):
        self.check_layout(R17)

    def test_t3_019_layout(self):
        self.check_layout(R19)

    def test_reexported_binding_resolves_to_the_chunk_that_exports_it(self):
        files = layout(R17)
        # A consumer imports `rt` through a barrel chunk that re-exports the provider's export.
        files['barrel-ZZZZ.js'] = b'import{rt as k}from"./projectGrouping-CCCC.js";export{k as w};'
        files['consumer-A.js'] = files['consumer-A.js'].replace(b'from"./projectGrouping-CCCC.js"', b'from"./barrel-ZZZZ.js"').replace(b'{rt as', b'{w as')
        files['consumer-B.js'] = files['consumer-B.js'].replace(b'from"./projectGrouping-CCCC.js"', b'from"./barrel-ZZZZ.js"').replace(b'{rt as', b'{w as')
        found = discover.discover(files)
        self.assertEqual(found['bindings']['details'], {'chunk': 'projectGrouping-CCCC.js', 'alias': 'rt'})

    def test_failure_lists_what_is_missing_and_renders_a_safe_adapter(self):
        names = {k: v for k, v in R19.items() if k not in ('shells', 'draftStore')}
        found = discover.discover(layout(names))
        self.assertEqual(set(found['missing']), {'the chat shell atoms', 'the new-chat draft store'})
        adapter = discover.render_adapter(found)
        self.assertIn('the chat shell atoms', adapter)
        self.assertNotIn('shells:', adapter)

    def test_missing_composer_markers_are_reported(self):
        files = layout(R19)
        files['_chat-X.js'] = b'nothing'
        self.assertIn('composer marker data-chat-composer-form', discover.discover(files)['missing'])

    def test_unrelated_client_finds_nothing_and_does_not_raise(self):
        found = discover.discover({'a-1.js': b'export{};'})
        self.assertEqual(found['bindings'], {})
        self.assertEqual(len(found['missing']), len(discover.BINDINGS) + 3)  # plus the DateTime constructor and two composer markers

    def test_real_client_extracts_when_provided(self):
        """T3_ADDS_CLIENT_ASSETS_017 / _019 point at extracted client assets kept outside the project."""
        expected = {'T3_ADDS_CLIENT_ASSETS_017': ('utils-BL51zcsk.js', 'al', 'it', 'nS'),
                    'T3_ADDS_CLIENT_ASSETS_019': ('utils-fcYT6KYI.js', 'yl', 'Y', 'XS')}
        for variable, (chunk, registry_alias, shells_alias, date_alias) in expected.items():
            if not os.environ.get(variable):
                continue
            with self.subTest(variable):
                found = discover.discover(discover.load_directory(Path(os.environ[variable])))
                self.assertEqual(found['missing'], [])
                self.assertEqual((found['bindings']['registry']['chunk'], found['bindings']['registry']['alias']), (chunk, registry_alias))
                self.assertEqual(found['bindings']['shells']['alias'], shells_alias)
                self.assertEqual(found['bindings']['dateTime'], {'chunk': chunk, 'alias': date_alias})


if __name__ == '__main__':
    unittest.main()
