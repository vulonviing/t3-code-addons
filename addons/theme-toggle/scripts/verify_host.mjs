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
});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', (error) => errors.push(error.message));
  // Every request is fulfilled locally. No live T3 profile, authentication, or API is used.
  await page.route('**/*', async (route) => {
    const url = new URL(route.request().url());
    if (!url.pathname.startsWith('/assets/')) {
      return route.fulfill({ contentType: 'text/html', body: '<!doctype html><html><body><div id="root"></div>'
        + '<div style="position:fixed;top:14px;right:16px;display:flex;gap:6px">'
        + ['Toggle thread details panel', 'Toggle terminal drawer', 'Toggle right panel']
          .map((label) => `<button aria-label="${label}" style="width:28px;height:28px"></button>`).join('')
        + '</div></body></html>' });
    }
    const relative = url.pathname.slice('/assets/'.length);
    const file = relative.startsWith('theme-toggle/')
      ? path.join(addon, 'src', relative.slice('theme-toggle/'.length)) : path.join(assets, relative);
    await route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'text/javascript', body: await fs.readFile(file) });
  });
  await page.goto('http://localhost:43179/');
  const result = await page.evaluate(async () => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    const { host } = await import('/assets/theme-toggle/host-v017.mjs');
    const initial = host.snapshot();
    check(['light', 'dark'].includes(initial.resolvedTheme), 'Host snapshot exposes the resolved theme');
    await import('/assets/theme-toggle/ui.mjs');
    await import('/assets/theme-toggle/ui.mjs?again');
    const mounts = document.querySelectorAll('#t3-adds-theme-toggle');
    check(mounts.length === 1, 'Mounted exactly once');
    const buttons = [...mounts[0].shadowRoot.querySelectorAll('button')];
    check(buttons.length === 2, 'Two theme buttons');
    const [light, dark] = buttons;
    const pressed = () => [light, dark].map((b) => b.getAttribute('aria-pressed'));
    dark.click();
    check(document.documentElement.classList.contains('dark'), 'Dark class applied through T3');
    check(host.snapshot().resolvedTheme === 'dark' && host.snapshot().appearanceMode === 'dark', 'Dark mode stored');
    check(pressed().join() === 'false,true', 'Dark button reflects state');
    light.click();
    check(!document.documentElement.classList.contains('dark'), 'Dark class removed through T3');
    check(host.snapshot().appearanceMode === 'light' && pressed().join() === 'true,false', 'Light mode stored');
    // Aligned with T3's header buttons and outside the desktop window-drag region.
    await new Promise((resolve) => setTimeout(resolve, 600));
    const pill = mounts[0].shadowRoot.querySelector('.seg').getBoundingClientRect();
    const first = document.querySelector('button[aria-label^="Toggle thread details panel"]').getBoundingClientRect();
    check(Math.abs((pill.top + pill.height / 2) - (first.top + first.height / 2)) <= 1, 'Vertically centered on the header buttons');
    check(pill.right <= first.left && first.left - pill.right <= 14, 'Sits directly left of the header buttons');
    check(getComputedStyle(mounts[0]).getPropertyValue('-webkit-app-region') === 'no-drag', 'Excluded from the window-drag region');
    return { adapter: 'passed', toggle: 'passed', mountedOnce: 'passed', aligned: 'passed' };
  });
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
