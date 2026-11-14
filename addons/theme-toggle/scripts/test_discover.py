"""Theme module discovery against small synthetic client layouts, plus optional real extracts."""
import json
import os
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import discover

def theme_chunk(snapshot, setter, subscribe, helper, store, exported):
    return (f'function {snapshot}(){{return {helper}()}}function {subscribe}(e){{let t={store}(e),n=other(e);return()=>{{t(),n()}}}}'
            f'function {setter}(e){{if(typeof window>`u`)return!1;try{{save(e)}}catch(e){{let t=1;return console.error(t),!1}}'
            f'return cache=null,apply(read(),{{suppressTransitions:!0}}),notify(),!0}}export{{{exported}}};')


# Layout of T3 0.1.7 and 0.1.9 (identical names, different chunk files) and a later layout with other names.
LAYOUT_A = theme_chunk('ye', 'Q', 'be', 'G', 'X', 'Q as c,ye as n,be as u')
LAYOUT_B = theme_chunk('aa', 'bb', 'cc', 'dd', 'ee', 'cc as z,aa as y,bb as x')
UNRELATED = 'function f(e){return e}export{f as a};'


class DiscoveryTests(unittest.TestCase):
    def test_both_known_layouts(self):
        for name, text, symbols in (('useTheme-A.js', LAYOUT_A, {'snapshot': 'n', 'setAppearanceMode': 'c', 'subscribe': 'u'}),
                                    ('useTheme-B.js', LAYOUT_B, {'snapshot': 'y', 'setAppearanceMode': 'x', 'subscribe': 'z'})):
            with self.subTest(name):
                found = discover.discover({name: text.encode(), 'other.js': UNRELATED.encode()})
                self.assertEqual((found['status'], found['chunk'], found['symbols']), ('attached', name, symbols))

    def test_failure_is_reported_not_raised_and_the_adapter_carries_the_reason(self):
        found = discover.discover({'other.js': UNRELATED.encode()})
        self.assertEqual(found['status'], 'unattached')
        adapter = discover.render_adapter(found)
        self.assertIn('const discoveryError = ' + json.dumps(found['reason']), adapter)
        self.assertNotIn('@@', adapter)
        self.assertNotIn('import * as chunk', adapter)

    def test_two_candidates_are_ambiguous(self):
        found = discover.discover({'a.js': LAYOUT_A.encode(), 'b.js': LAYOUT_B.encode()})
        self.assertEqual(found['status'], 'unattached')

    def test_unexported_function_is_not_attached(self):
        found = discover.discover({'a.js': LAYOUT_A.replace('Q as c,', '').encode()})
        self.assertEqual(found['status'], 'unattached')

    def test_rendered_adapter_imports_the_discovered_chunk(self):
        adapter = discover.render_adapter(discover.discover({'useTheme-A.js': LAYOUT_A.encode()}))
        self.assertIn("from '../useTheme-A.js'", adapter)
        self.assertIn('"snapshot": "n"', adapter)

    def test_real_client_extracts_when_provided(self):
        for variable, chunk in (('T3_ADDS_CLIENT_ASSETS_017', 'useTheme-DGh-F8xD.js'),
                                ('T3_ADDS_CLIENT_ASSETS_019', 'useTheme-CuZZWvKw.js')):
            if os.environ.get(variable):
                with self.subTest(variable):
                    found = discover.discover(discover.load_directory(Path(os.environ[variable])))
                    self.assertEqual((found['status'], found['chunk']), ('attached', chunk))


if __name__ == '__main__':
    unittest.main()
