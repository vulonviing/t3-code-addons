"""Host module discovery against small synthetic client layouts, plus optional real extracts."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import discover

PROVIDER = 'IY=FH();function Prov({children:e}){return(0,Q.createElement)(DY.Provider,{value:IY},e)}'
DETAILS = 'M=me(j.stateAtom);function v(e){return M.threadAtom(e)}'
SERVER = 'S=y(Se,{});function w(e){return S.configValueAtom(e)??S.providersValueAtom(e)}'


def chunk(body, exported):
    return f'var {body};export{{{exported}}};'


# T3 0.1.7 layout: three chunks. T3 0.1.9 layout: other chunk files and aliases (the thread object moved chunks).
LAYOUT_017 = {'utils-A.js': chunk(PROVIDER, 'IY as al'), 'projectGrouping-A.js': chunk(DETAILS, 'M as rt'),
              'themePalette-A.js': chunk(SERVER, 'S as ut')}
LAYOUT_019 = {'utils-B.js': chunk(PROVIDER.replace('IY', '_$'), '_$ as yl'),
              'entities-B.js': chunk(DETAILS.replace('M', 'z'), 'z as J'), 'themePalette-B.js': chunk(SERVER.replace('S', 'C'), 'C as dt')}
CONSUMER = {'consumer.js': 'import{ut as E}from"./themePalette-A.js";function f(e){return E.configValueAtom(e)??E.providersValueAtom(e)}export{f as a};'}


def assets(layout, **extra):
    return {name: text.encode() for name, text in {**layout, **CONSUMER, **extra}.items()}


class DiscoveryTests(unittest.TestCase):
    def test_both_known_layouts(self):
        for layout, expected in ((LAYOUT_017, {'registry': 'al', 'details': 'rt', 'server': 'ut'}),
                                 (LAYOUT_019, {'registry': 'yl', 'details': 'J', 'server': 'dt'})):
            with self.subTest(sorted(layout)[0]):
                found = discover.discover(assets(layout))
                self.assertEqual(found['status'], 'attached')
                self.assertEqual({role: part['alias'] for role, part in found['parts'].items()}, expected)

    def test_failure_is_reported_not_raised_and_the_adapter_carries_the_reason(self):
        broken = {k: v for k, v in LAYOUT_019.items() if not k.startswith('entities')}
        found = discover.discover(assets(broken))
        self.assertEqual(found['status'], 'unattached')
        self.assertIn('details not found', found['reason'])
        adapter = discover.render_adapter(found)
        self.assertIn('const discoveryError = ' + json.dumps(found['reason']), adapter)
        self.assertNotIn('import * as', adapter)
        self.assertNotIn('@@', adapter)

    def test_two_candidates_are_ambiguous(self):
        found = discover.discover(assets(LAYOUT_017, **{'dup.js': chunk(DETAILS.replace('M', 'q'), 'q as zz')}))
        self.assertEqual(found['status'], 'unattached')
        self.assertIn('ambiguous', found['reason'])

    def test_rendered_adapter_imports_the_discovered_chunks(self):
        adapter = discover.render_adapter(discover.discover(assets(LAYOUT_019)))
        self.assertIn("from '../entities-B.js'", adapter)
        self.assertIn('detailsChunk["J"]', adapter)

    def test_real_client_extracts_when_provided(self):
        for variable, chunks in (('T3_ADDS_CLIENT_ASSETS_017', ['projectGrouping-aRBPi9Ux.js', 'themePalette-owjsZZI0.js', 'utils-BL51zcsk.js']),
                                 ('T3_ADDS_CLIENT_ASSETS_019', ['entities-kmkJFwMa.js', 'themePalette-oA-712GZ.js', 'utils-fcYT6KYI.js'])):
            if os.environ.get(variable):
                with self.subTest(variable):
                    found = discover.discover(discover.load_directory(Path(os.environ[variable])))
                    self.assertEqual((found['status'], found['chunks']), ('attached', chunks))


if __name__ == '__main__':
    unittest.main()
