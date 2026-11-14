"""Draft-store discovery against small synthetic client layouts, plus optional real extracts."""
import os
import sys
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
import discover

STORE_BODY = ('create((t,n)=>({draftsByThreadKey:{},getComposerDraft:e=>lookup(t(),e),'
              'setPrompt:(e,r)=>{n(s=>({...s}))},other:1}))')
# Layout of T3 0.1.7 / 0.1.9: the exported alias points at an alias of the created store.
LAYOUT_ALIAS = ('function lookup(){}var Y9=' + STORE_BODY + ',X9=Y9;function sync(e){return Y9.getState()}'
                'export{X9 as A,sync as z};\n//# sourceMappingURL=utils-AAAA.js.map')
# Hypothetical later layout: different names, store exported directly, other exported declarations before it.
LAYOUT_DIRECT = ('let helper=1;const q=' + STORE_BODY + ';export{helper as h,q as drafts};')
CONSUMER = 'let a=s.getState(),{getComposerDraft:y,setPrompt:p}=a;a.setPrompt(1,2);export{y as a};'
MARKERS = 'x="data-chat-composer-form data-chat-composer-footer data-chat-composer-actions"'


def client(**chunks):
    files = {name: text.encode() for name, text in chunks.items()}
    files['_chat-X.js'] = MARKERS.encode()
    files['consumer-X.js'] = CONSUMER.encode()
    return files


class DiscoveryTests(unittest.TestCase):
    def test_aliased_store_layout(self):
        found = discover.discover(client(**{'utils-AAAA.js': LAYOUT_ALIAS}))
        self.assertEqual((found['chunk'], found['alias']), ('utils-AAAA.js', 'A'))
        self.assertEqual(len(found['chunkSha256']), 64)

    def test_direct_export_layout_and_consumer_chunks_are_ignored(self):
        found = discover.discover(client(**{'store-ZZZZ.js': LAYOUT_DIRECT}))
        self.assertEqual((found['chunk'], found['alias']), ('store-ZZZZ.js', 'drafts'))

    def test_missing_store_is_refused_with_a_clear_error(self):
        with self.assertRaisesRegex(discover.DiscoveryError, 'draft store'):
            discover.discover(client())

    def test_missing_composer_markers_are_refused(self):
        files = {'utils-AAAA.js': LAYOUT_ALIAS.encode(), '_chat-X.js': b'nothing'}
        with self.assertRaisesRegex(discover.DiscoveryError, 'data-chat-composer-form'):
            discover.discover(files)

    def test_two_stores_are_ambiguous(self):
        with self.assertRaisesRegex(discover.DiscoveryError, 'Ambiguous'):
            discover.discover(client(**{'a-1.js': LAYOUT_ALIAS, 'b-2.js': LAYOUT_DIRECT}))

    def test_rendered_adapter_has_discovered_names_and_no_placeholders(self):
        found = discover.discover(client(**{'utils-AAAA.js': LAYOUT_ALIAS}))
        adapter = discover.render_adapter(found)
        self.assertIn("from '../utils-AAAA.js'", adapter)
        self.assertIn("chunk['A']", adapter)
        self.assertNotIn('@@', adapter)

    def test_real_client_extracts_when_provided(self):
        """T3_ADDS_CLIENT_ASSETS_017 / _019 point at extracted client assets kept outside the project."""
        for variable, chunk in (('T3_ADDS_CLIENT_ASSETS_017', 'utils-BL51zcsk.js'),
                                ('T3_ADDS_CLIENT_ASSETS_019', 'utils-fcYT6KYI.js')):
            if not os.environ.get(variable):
                continue
            with self.subTest(variable):
                found = discover.discover(discover.load_directory(Path(os.environ[variable])))
                self.assertEqual((found['chunk'], found['alias']), (chunk, 'A'))


if __name__ == '__main__':
    unittest.main()
