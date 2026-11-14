// Real extracted T3 draft-store exports and fresh addon sources; synthetic voice transport only.
// No real microphone, live T3 account, or paid model calls.
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import fs from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.T3_ADDS_PLAYWRIGHT ?? 'playwright-core');
const addon = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assets = process.argv[2];
if (!assets) throw new Error('Pass the extracted official client assets directory.');
const found = JSON.parse(execFileSync('python3', [path.join(addon, 'scripts/discover.py'), assets], { encoding: 'utf8' }));
const adapter = execFileSync('python3', [path.join(addon, 'scripts/discover.py'), assets, '--adapter'], { encoding: 'utf8' });
const chunkUrl = `/assets/${found.chunk}`;
const browser = await chromium.launch({ headless: true, executablePath: process.env.T3_ADDS_TEST_BROWSER });
try {
  const page = await browser.newPage({ viewport: { width: 1100, height: 800 } });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/assets/')) return route.fulfill({ contentType: 'text/html', body: '<!doctype html><style>body{background:#171719;color:#ddd;--background:#171719;--foreground:#ddd}#root>:not(form){display:none!important}form{position:fixed;bottom:20px;left:20px;right:20px;height:140px;border:1px solid #555;border-radius:12px}textarea{position:absolute;top:8px;left:8px;right:8px;width:calc(100% - 16px);height:80px;background:transparent;color:inherit;border:0;resize:none}.footer{position:absolute;bottom:8px;left:8px;right:8px;height:40px;display:flex;align-items:center;gap:8px}.addon{display:inline-block;padding:6px;font:12px system-ui}.right{flex:1;min-width:0;display:flex;justify-content:flex-end;gap:8px}button{cursor:pointer}</style><div id="root"></div>' });
    const relative = url.pathname.slice('/assets/'.length);
    if (relative === 'codex-dictation/host.mjs') return route.fulfill({ contentType: 'text/javascript', body: adapter });
    const filename = relative.startsWith('codex-dictation/') ? path.join(addon, 'src', relative.slice('codex-dictation/'.length)) : path.join(assets, relative);
    await route.fulfill({ contentType: filename.endsWith('.css') ? 'text/css' : 'text/javascript', body: await fs.readFile(filename) });
  });
  await page.goto('http://localhost:43179/env/thread1');
  await page.evaluate(async ({ chunkUrl, alias }) => {
    const drafts = (await import(chunkUrl))[alias];
    const { host } = await import('/assets/codex-dictation/host.mjs');
    const { mountMicrophone } = await import('/assets/codex-dictation/widget.mjs');
    if (typeof drafts.getState().setPrompt !== 'function') throw new Error('Host draft-store export changed.');
    const form = document.createElement('form'); form.dataset.chatComposerForm = 'true';
    form.innerHTML = '<textarea aria-label="Host composer"></textarea><div class="footer" data-chat-composer-footer="true"><span class="addon" id="t3-adds-council-composer">Model Council</span><span class="addon" id="t3-adds-orchestrator">Orchestrator</span><div class="right" data-chat-composer-actions="right"><button type="submit">Send</button></div></div>';
    document.getElementById('root').append(form);
    const input = form.querySelector('textarea');
    drafts.getState().setPrompt(host.target(), 'Existing prompt'); input.value = host.prompt(host.target());
    drafts.subscribe(() => { input.value = host.prompt(host.target()); });
    input.oninput = () => drafts.getState().setPrompt(host.target(), input.value);
    window.sent = 0;
    form.onsubmit = e => { e.preventDefault(); window.sent++; drafts.getState().setPrompt(host.target(), ''); };
    input.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); form.requestSubmit(); } };
    window.originalComposer = form.innerHTML;
    window.voice = { starts: 0, muted: 0, closed: 0 };
    const connect = callbacks => {
      window.voice.events = callbacks;
      return { async start() { window.voice.starts++; await new Promise(resolve => { window.voice.ready = resolve; }); }, mute() { window.voice.muted++; }, async stop() { window.voice.closed++; } };
    };
    mountMicrophone({ connect });
    await import('/assets/codex-dictation/ui.mjs');
    await import('/assets/codex-dictation/ui.mjs?again');
  }, { chunkUrl, alias: found.alias });
  const mount = page.locator('#t3-adds-codex-dictation');
  await mount.waitFor({ state: 'visible', timeout: 3000 }).catch(async error => {
    console.error(JSON.stringify({ errors, layout: await page.evaluate(() => ({ hidden: document.hidden, form: !!document.querySelector('form'), footer: document.querySelector('.footer')?.getBoundingClientRect().toJSON(), widget: document.querySelector('#t3-adds-codex-dictation')?.outerHTML, route: location.pathname })) }));
    throw error;
  }); assert.equal(await mount.count(), 1);
  const bounds = await page.evaluate(() => {
    const a = document.querySelector('#t3-adds-orchestrator').getBoundingClientRect();
    const b = document.querySelector('#t3-adds-codex-dictation').getBoundingClientRect();
    return { gap: Math.round(b.left - a.right), sameRow: Math.abs((a.top + a.height / 2) - (b.top + b.height / 2)) < 3 };
  });
  assert.deepEqual(bounds, { gap: 6, sameRow: true });
  await page.evaluate(() => { const n = document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('.note'); n.querySelector('p').textContent = 'Test error.'; n.hidden = false; });
  await mount.getByRole('button', { name: 'Dismiss message' }).click();
  assert.equal(await page.evaluate(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('.note').hidden), true);
  async function assertToolbarPlacement() {
    await page.waitForFunction(() => {
      const a = document.querySelector('#t3-adds-orchestrator').getBoundingClientRect();
      const b = document.querySelector('#t3-adds-codex-dictation').getBoundingClientRect();
      const r = document.querySelector('[data-chat-composer-actions="right"] button').getBoundingClientRect();
      return Math.abs((a.top + a.height / 2) - (b.top + b.height / 2)) < 2 && b.left >= a.right && b.right < r.left;
    });
  }
  // Regression: a taller draft moves the toolbar without resizing the toolbar itself.
  await page.evaluate(() => { document.querySelector('form').style.height = '400px'; document.querySelector('form').style.bottom = '140px'; });
  await assertToolbarPlacement();
  await page.evaluate(() => { document.querySelector('form').style.height = '140px'; document.querySelector('form').style.bottom = '20px'; });
  await assertToolbarPlacement();
  const idle = await page.evaluate(async () => {
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    let reads = 0;
    const footer = document.querySelector('.footer'), original = footer.getBoundingClientRect;
    footer.getBoundingClientRect = function () { reads++; return original.call(this); };
    const messages = document.createElement('div'); document.getElementById('root').prepend(messages);
    for (let i = 0; i < 100; i++) messages.append(document.createTextNode('stream '));
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    footer.getBoundingClientRect = original; messages.remove();
    return { layoutReads: reads, voiceStarts: window.voice.starts };
  });
  assert.deepEqual(idle, { layoutReads: 0, voiceStarts: 0 });
  const emit = (id, text) => page.evaluate(({ id, text }) => window.voice.events.onEvent({ type: 'input_transcript.added', item: { id, type: 'input_transcript', text } }), { id, text });
  await mount.getByRole('button', { name: 'Start dictation' }).click();
  assert.equal(await mount.locator('button:not(.close)').getAttribute('data-phase'), 'connecting');
  assert.equal(await mount.locator('.label').textContent(), 'Connecting');
  assert.equal(await mount.locator('.spinner').isVisible(), true);
  if (process.env.T3_ADDS_TEST_SCREENSHOT) {
    await page.waitForFunction(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('button').getBoundingClientRect().width >= 123);
    await page.screenshot({ path: process.env.T3_ADDS_TEST_SCREENSHOT.replace(/\.png$/, '-connecting.png'), caret: 'initial' });
  }
  await page.evaluate(() => window.voice.ready());
  await mount.getByRole('button', { name: 'Stop dictation' }).waitFor();
  await page.waitForFunction(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('button').dataset.phase === 'recording');
  assert.equal(await mount.locator('.label').textContent(), 'Listening');
  await page.evaluate(() => window.voice.events.onLevel(.8));
  assert.equal(await mount.locator('button:not(.close)').evaluate(e => e.style.getPropertyValue('--level')), '0.800');
  await page.waitForFunction(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('.wave i:nth-child(3)').getBoundingClientRect().height > 12);
  if (process.env.T3_ADDS_TEST_SCREENSHOT) await page.screenshot({ path: process.env.T3_ADDS_TEST_SCREENSHOT.replace(/\.png$/, '-listening.png'), caret: 'initial' });
  await page.evaluate(() => { document.querySelector('form').style.height = '510px'; document.querySelector('form').style.bottom = '80px'; });
  await assertToolbarPlacement();
  await page.setViewportSize({ width: 350, height: 800 });
  await page.waitForFunction(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('button').hasAttribute('data-compact'));
  await assertToolbarPlacement();
  assert.equal(await mount.locator('.label').isVisible(), false);
  await page.setViewportSize({ width: 1100, height: 800 });
  await assertToolbarPlacement();
  await emit('a', 'Dictated');
  assert.equal(await page.getByRole('textbox', { name: 'Host composer' }).inputValue(), 'Existing prompt\nDictated');
  await mount.getByRole('button', { name: 'Stop dictation' }).click();
  assert.equal(await page.evaluate(() => window.voice.muted), 1);
  await emit('b', ' text.');
  await mount.getByRole('button', { name: 'Start dictation' }).waitFor();
  assert.equal(await page.getByRole('textbox', { name: 'Host composer' }).inputValue(), 'Existing prompt\nDictated text.');
  assert.equal(await page.evaluate(() => window.sent), 0);
  assert.equal(await page.evaluate(() => document.activeElement?.getAttribute('aria-label')), 'Host composer');
  await page.keyboard.press('Enter'); assert.equal(await page.evaluate(() => window.sent), 1);
  assert.equal(await page.getByRole('textbox', { name: 'Host composer' }).inputValue(), '');
  await emit('c', ' late'); assert.equal(await page.getByRole('textbox', { name: 'Host composer' }).inputValue(), '');
  const integrity = await page.evaluate(() => ({ untouched: document.querySelector('form').innerHTML === window.originalComposer, parent: document.querySelector('#t3-adds-codex-dictation').parentElement.tagName }));
  assert.deepEqual(integrity, { untouched: true, parent: 'BODY' });
  await page.evaluate(() => { history.pushState({}, '', '/draft/draft-1'); window.dispatchEvent(new PopStateEvent('popstate')); });
  await mount.getByRole('button', { name: 'Start dictation' }).click(); await page.evaluate(() => window.voice.ready()); await emit('a', 'New chat text.');
  await mount.getByRole('button', { name: 'Stop dictation' }).click();
  await mount.getByRole('button', { name: 'Start dictation' }).waitFor();
  assert.equal(await page.evaluate(async ({ chunkUrl, alias }) => (await import(chunkUrl))[alias].getState().getComposerDraft('draft-1').prompt, { chunkUrl, alias: found.alias }), 'New chat text.');
  await page.setViewportSize({ width: 350, height: 760 });
  await page.waitForFunction(() => {
    const b = document.querySelector('#t3-adds-codex-dictation').getBoundingClientRect();
    return b.left >= 0 && b.right <= innerWidth;
  });
  const narrow = await mount.boundingBox(); assert.ok(narrow.x >= 0 && narrow.x + narrow.width <= 350);
  const safeNarrow = await page.evaluate(() => {
    const b = document.querySelector('#t3-adds-codex-dictation').getBoundingClientRect();
    const f = document.querySelector('form').getBoundingClientRect();
    return b.top >= f.bottom || b.top >= document.querySelector('.footer').getBoundingClientRect().top;
  });
  assert.ok(safeNarrow, 'Narrow placement must never cover draft text');
  if (process.env.T3_ADDS_TEST_SCREENSHOT) await page.screenshot({ path: process.env.T3_ADDS_TEST_SCREENSHOT, caret: 'initial' });
  // Regression: no room below a full toolbar must not hide the microphone offscreen.
  await page.evaluate(() => {
    document.querySelector('form').style.bottom = '0';
    document.querySelector('.right button').style.width = '250px';
    window.dispatchEvent(new Event('resize'));
  });
  await page.waitForFunction(() => {
    const m = document.querySelector('#t3-adds-codex-dictation');
    const b = m.getBoundingClientRect(), f = document.querySelector('form').getBoundingClientRect();
    return !m.hidden && b.top >= 0 && b.bottom <= f.top;
  });
  // Backgrounding and navigation must retain one live session and its original draft.
  await page.setViewportSize({ width: 1100, height: 800 });
  await mount.getByRole('button', { name: 'Start dictation' }).click();
  await page.evaluate(() => window.voice.ready());
  await page.waitForFunction(() => document.querySelector('#t3-adds-codex-dictation').shadowRoot.querySelector('button').dataset.phase === 'recording');
  const mutedBeforeBackground = await page.evaluate(() => window.voice.muted);
  await page.evaluate(() => {
    window.dispatchEvent(new Event('blur'));
    Object.defineProperty(document, 'hidden', { configurable: true, get: () => true });
    document.dispatchEvent(new Event('visibilitychange'));
  });
  await emit('background', 'Background speech.');
  assert.equal(await page.evaluate(() => window.voice.muted), mutedBeforeBackground);
  await page.evaluate(() => {
    delete document.hidden;
    document.dispatchEvent(new Event('visibilitychange'));
    history.pushState({}, '', '/env/other-chat'); window.dispatchEvent(new PopStateEvent('popstate'));
  });
  await emit('continued', ' More speech.');
  const draftsAfterNavigation = await page.evaluate(async ({ chunkUrl, alias }) => {
    const drafts = (await import(chunkUrl))[alias].getState();
    return { original: drafts.getComposerDraft('draft-1').prompt, other: drafts.getComposerDraft({ environmentId: 'env', threadId: 'other-chat' })?.prompt ?? '' };
  }, { chunkUrl, alias: found.alias });
  assert.deepEqual(draftsAfterNavigation, { original: 'New chat text.\nBackground speech. More speech.', other: '' });
  await page.evaluate(() => { history.pushState({}, '', '/settings/general'); window.dispatchEvent(new PopStateEvent('popstate')); });
  await mount.waitFor({ state: 'visible' });
  await mount.getByRole('button', { name: 'Stop dictation' }).click();
  await mount.waitFor({ state: 'hidden' });
  assert.equal(await page.evaluate(() => window.voice.muted), mutedBeforeBackground + 1);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ hostExports: 'passed', backgroundRecording: 'passed', originalDraftAfterNavigation: 'passed', settingsStop: 'passed', dismissibleError: 'passed', placement: 'beside-orchestrator', flexWrapperGap: 'passed', fullToolbarAtWindowBottom: 'passed', connectingIndicator: 'passed', speechWave: 'passed', liveDraft: 'passed', immediateMute: 'passed', finalWords: 'passed', manualEnterSend: 'passed', noAutomaticSend: 'passed', newChat: 'passed', reactDOM: 'untouched', narrowWindow: 'passed', growingComposer: 'passed', compactRecording: 'passed', idleStreamingLayoutReads: idle.layoutReads }));
} finally { await browser.close(); }
