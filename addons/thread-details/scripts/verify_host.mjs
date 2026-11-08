// Run in an external test copy with playwright-core installed. No server, account, or model calls.
// Usage: node scripts/verify_host.mjs /external/official-client-assets   (see extract_client.py)
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { chromium } from 'playwright-core';

const addon = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const assets = process.argv[2];
if (!assets) throw new Error('Usage: node scripts/verify_host.mjs /external/official-client-assets');
const browser = await chromium.launch({
  ...(process.env.T3_ADDS_TEST_BROWSER ? { executablePath: process.env.T3_ADDS_TEST_BROWSER } : {}),
  headless: true,
  args: ['--window-size=1400,900'],
});
try {
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  // Every request is fulfilled locally. No live T3 profile, authentication, or API is used.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/assets/')) {
      return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><head></head><body><div id="root"></div></body></html>' });
    }
    const relative = url.pathname.slice('/assets/'.length);
    const file = relative.startsWith('thread-details/')
      ? path.join(addon, 'src', relative.slice('thread-details/'.length)) : path.join(assets, relative);
    await route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'text/javascript', body: await fs.readFile(file) });
  });
  await page.goto('http://localhost:43179/env/thread1');
  const result = await page.evaluate(async () => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
    const [{ al: registry }, { rt: details }, { ut: server }] = await Promise.all([
      import('/assets/utils-BL51zcsk.js'), import('/assets/projectGrouping-aRBPi9Ux.js'), import('/assets/themePalette-owjsZZI0.js')]);
    check(typeof registry.subscribe === 'function' && typeof details.threadAtom === 'function'
      && typeof server.configValueAtom === 'function', 'Host exports');
    const ref = { environmentId: 'env', threadId: 'thread1' };
    const projection = {
      thread: { createdAt: new Date(Date.now() - 32 * 60000).toISOString() },
      providerThreads: [{ id: 'p', driver: 'claudeAgent' }],
      providerTurns: [{ providerThreadId: 'p', status: 'completed',
        turnTokenUsage: { usageStatus: 'complete', inputTokens: 120000, cachedInputTokens: 100000, outputTokens: 4830, models: ['claude-sonnet-5-5'] } }],
    };
    const providers = [{ instanceId: 'codex', driver: 'codex', displayName: 'Codex', enabled: true, installed: true,
      usageLimits: { checkedAt: new Date().toISOString(), windows: [{ id: 'w', kind: 'weekly', label: 'Weekly', usedPercent: 76, resetsAt: new Date(Date.now() + 3 * 86400000).toISOString(), windowDurationMins: 10080 }] } }];
    let observedThread = 0, observedConfig = 0, stopped = 0;
    registry.subscribe = (atom, listener, options) => {
      check(options.immediate, 'Observation contract');
      if (atom === details.threadAtom(ref)) { observedThread += 1; listener({ projection }); }
      else if (atom === server.configValueAtom('env')) { observedConfig += 1; listener({ providers }); }
      else throw new Error('Unexpected atom');
      return () => { stopped += 1; };
    };
    let intervals = 0;
    const realSetInterval = window.setInterval.bind(window);
    window.setInterval = (...args) => { intervals += 1; return realSetInterval(...args); };
    // T3's own thread-details card, as a stand-in: the addon only reads where it is.
    const card = document.createElement('div');
    card.setAttribute('data-thread-details-card', '');
    card.style.cssText = 'position:fixed;right:16px;top:60px;width:300px;height:200px';
    document.body.append(card);
    await import('/assets/thread-details/ui.mjs');
    await import('/assets/thread-details/ui.mjs?again');
    check(document.querySelectorAll('#t3-adds-thread-details').length === 1, 'Mounted exactly once');
    const ours = document.querySelector('#t3-adds-thread-details');
    const heads = () => [...ours.querySelectorAll('.head')];
    await wait(200);
    check(observedThread >= 1 && observedConfig === 1, 'Each source observed: ' + observedThread + '/' + observedConfig);
    check(!ours.hidden && heads().length === 2, 'Shown with two sections while T3\'s card is open');
    const below = () => { const a = card.getBoundingClientRect(), b = ours.getBoundingClientRect(); return [Math.round(b.top - a.bottom), Math.round(b.left - a.left), Math.round(b.width - a.width)]; };
    check(JSON.stringify(below()) === '[8,0,0]', 'Attached under the card with its width: ' + below());
    check(heads()[0].textContent.includes('125K · 32m') && heads()[1].textContent.includes('Codex 24%'), 'Summaries: ' + heads().map((h) => h.textContent).join('|'));
    check(ours.querySelector('.body').textContent.trim() === '', 'Sections start collapsed');
    heads()[0].click();
    await wait(50);
    const rows = [...ours.querySelectorAll('.model')];
    check(rows.length === 1 && rows[0].textContent.includes('sonnet-5-5') && rows[0].textContent.includes('125K'), 'Model rows: ' + rows.map((r) => r.textContent));
    check(rows[0].title.includes('120,000 in') && rows[0].title.includes('83% cached') && rows[0].title.includes('4,830 out') && rows[0].title.includes('1 turns'), 'Hover details: ' + rows[0].title);
    check(!ours.querySelector('.num'), 'No duplicate total inside the section');
    heads()[1].click();
    await wait(50);
    check(ours.textContent.includes('Codex') && ours.textContent.includes('resets in 2d 23h'), 'Plan rows with reset times: ' + ours.textContent);
    card.style.height = '320px';
    await wait(400);
    check(JSON.stringify(below()) === '[8,0,0]', 'Follows T3\'s card when it grows: ' + below());
    card.style.display = 'none';
    document.body.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    await wait(700);
    check(ours.hidden, 'Hidden when T3\'s card closes');
    card.style.display = '';
    document.body.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
    await wait(700);
    check(!ours.hidden, 'Back when it reopens');
    check(intervals <= 2, 'No polling timers: ' + intervals);
    history.pushState({}, '', '/settings/general');
    await wait(100);
    check(stopped >= 1, 'Observation stopped off a thread route');
    return { adapter: 'passed', placement: 'passed', usage: 'passed', plan: 'passed', follow: 'passed', routeChange: 'passed' };
  });
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
