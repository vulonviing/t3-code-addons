// Run in an external test copy with playwright-core installed. No server, account, or model calls.
// Usage: node scripts/verify_host.mjs /external/official-client-assets   (see extract_client.py)
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execFileSync } from 'node:child_process';
import { chromium } from 'playwright-core';

const addon = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assets = process.argv[2];
if (!assets) throw new Error('Usage: node scripts/verify_host.mjs /external/official-client-assets');
// The adapter is generated from the target client by signature, exactly as the installer does; nothing is pinned.
const discover = (...args) => execFileSync('python3', ['-I', path.join(addon, 'scripts/discover.py'), assets, ...args], { encoding: 'utf8' });
const found = JSON.parse(discover());
assert.deepEqual(found.missing, []);
const adapter = discover('--adapter');
const browser = await chromium.launch({
  ...(process.env.T3_ADDS_TEST_BROWSER ? { executablePath: process.env.T3_ADDS_TEST_BROWSER } : {}),
  headless: true,
});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  // Every request is fulfilled locally. No live T3 profile, authentication, or API is used.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/assets/')) {
      return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body><div id="root">'
        + '<form data-chat-composer-form="true"><div data-chat-composer-footer="true"><div data-chat-composer-actions="right"></div></div></form>'
        + '</div></body></html>' });
    }
    const relative = url.pathname.slice('/assets/'.length);
    if (relative === 'orchestrator/host.mjs') return route.fulfill({ contentType: 'text/javascript', body: adapter });
    const file = relative.startsWith('orchestrator/')
      ? path.join(addon, 'src', relative.slice('orchestrator/'.length)) : path.join(assets, relative);
    await route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'text/javascript', body: await fs.readFile(file) });
  });
  await page.goto('http://localhost:43179/');
  const draftChunk = found.bindings.draftStore;
  const result = await page.evaluate(async (draftChunk) => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    const { host } = await import('/assets/orchestrator/host.mjs');
    for (const name of ['parent', 'projection', 'canOperate', 'providers', 'command', 'observe']) check(typeof host[name] === 'function', `Host exposes ${name}`);
    check(host.unsupported() === '', 'Adapter reports no unsupported pieces');
    check(host.parent({ environmentId: 'none', threadId: 'none' }) === null, 'Unknown chat reads as absent');
    check(Array.isArray(host.providers({ environmentId: 'none', threadId: 'none' })), 'Providers read as a list');
    const draftStore = (await import(`/assets/${draftChunk.chunk}`))[draftChunk.alias];
    const actions = draftStore.getState();
    for (const name of ['getDraftSession', 'getComposerDraft', 'markDraftThreadPromoting', 'finalizePromotedDraftThread']) check(typeof actions[name] === 'function', `Draft store exposes ${name}`);
    for (const name of ['session', 'composer', 'markPromoting', 'finalize']) check(typeof host.draft[name] === 'function', `Host draft exposes ${name}`);
    check(typeof host.observeParent === 'function', 'Host exposes observeParent');
    const unknown = { environmentId: 'none', threadId: 'none' };
    let absent = null;
    const stopUnknown = host.observeParent(unknown, (parent) => { absent = parent; });
    check(typeof stopUnknown === 'function', 'observeParent returns an unsubscribe function');
    check(absent === null, 'Unknown thread observes as absent');
    stopUnknown();
    check(host.draft.session('none') === null && host.draft.composer('none') === null, 'Unknown draft reads as absent');
    await import('/assets/orchestrator/ui.mjs');
    await import('/assets/orchestrator/ui.mjs?again');
    check(document.querySelectorAll('#t3-adds-orchestrator').length <= 1, 'Mounted at most once');
    return { adapter: 'passed', mountedOnce: 'passed' };
  }, draftChunk);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
