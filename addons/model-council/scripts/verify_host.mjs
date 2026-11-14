// Run in an external test copy with playwright-core installed. No server or model calls.
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
      return route.fulfill({ contentType: 'text/html', body: '<div id="root"><form data-chat-composer-form="true"><div data-chat-composer-footer="true"><span data-chat-composer-actions="right"></span></div></form></div>' });
    }
    const relative = url.pathname.slice('/assets/'.length);
    if (relative === 'model-council/host.mjs') return route.fulfill({ contentType: 'text/javascript', body: adapter });
    const file = relative.startsWith('model-council/')
      ? path.join(addon, 'src', relative.slice('model-council/'.length)) : path.join(assets, relative);
    await route.fulfill({ contentType: file.endsWith('.css') ? 'text/css' : 'text/javascript', body: await fs.readFile(file) });
  });
  await page.goto('http://localhost:43179/env/parent');
  const b = found.bindings;
  const result = await page.evaluate(async (b) => {
    const check = (value, message) => { if (!value) throw new Error(message); };
    const pick = async (name) => (await import(`/assets/${b[name].chunk}`))[b[name].alias];
    const [registry, dateTime, details, shells, server, orchestration, draftStore] = await Promise.all(
      ['registry', 'dateTime', 'details', 'shells', 'server', 'orchestration', 'draftStore'].map(pick));
    // The session atoms live in the permission check's chunk; find the export that carries them.
    const sessions = Object.values(await import(`/assets/${b.hasScope.chunk}`)).find((value) => typeof value?.sessionStateAtom === 'function');
    check(sessions, 'Session atoms export');
    const { host } = await import('/assets/model-council/host.mjs');
    check(host.unsupported() === '', 'Adapter reports no unsupported pieces');
    check(typeof registry.get === 'function' && typeof registry.subscribe === 'function', 'Registry export');
    check(typeof details.threadAtom === 'function' && typeof shells.threadShellAtom === 'function', 'Thread exports');
    check(typeof server.configValueAtom === 'function', 'Server export');
    const ref = { environmentId: 'env', threadId: 'parent' };
    const iso = '2026-01-01T00:00:00.000Z';
    const nativeTime = dateTime(iso);
    check(nativeTime.epochMilliseconds === Date.parse(iso), 'Native DateTime decoding');
    check(Number.isNaN(new Date(nativeTime).getTime()), 'Native DateTime reproduces the old settlement date bug');
    const projection = { runs: [], turnItems: [] };
    const shell = { projectId: 'project', source: { status: 'idle', updatedAt: nativeTime }, updatedAt: iso,
      modelSelection: { instanceId: 'first', model: 'first' }, settledOverride: null };
    const enabled = { instanceId: 'first', enabled: true, installed: true, status: 'ready', models: [{ slug: 'first', name: 'First' }] };
    const config = { providers: [enabled,
      { ...enabled, instanceId: 'disabled' }, { ...enabled, instanceId: 'missing', installed: false },
      { ...enabled, instanceId: 'broken', status: 'error' }],
      settings: { projectSettingsOverrides: { project: { providerInstances: { disabled: { enabled: false } } } } } };
    const atoms = new Map([
      [shells.threadShellAtom(ref), shell], [details.threadAtom(ref), { projection }],
      [server.configValueAtom('env'), config],
      [sessions.sessionStateAtom('env'), { _tag: 'Success', value: { authenticated: true, permissions: ['orchestration:operate'] } }],
    ]);
    registry.get = (atom) => { check(atoms.has(atom), 'Unexpected atom read'); return atoms.get(atom); };
    check(host.parent(ref).status === 'idle' && host.parent(ref).updatedAt === iso, 'Parent shell');
    check(host.projection(ref) === projection, 'Projection');
    check(host.canOperate(ref), 'Scope grant');
    check(host.providers(ref).length === 1 && host.providers(ref)[0] === enabled, 'Provider overrides');
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
    let observed = false, stopped = false;
    registry.subscribe = (atom, listener, options) => {
      check(atom === details.threadAtom(ref) && options.immediate, 'Observation contract');
      listener({ projection }); return () => { stopped = true; };
    };
    host.observe(ref, (value) => { observed = value === projection; })();
    check(observed && stopped, 'Observation and disposal');
    let calls = 0;
    orchestration.v2.dispatchCommand.run = async (value, request) => {
      check(value === registry && request.environmentId === 'env', 'Command scope');
      const command = request.input;
      if (command.type === 'thread.auto-settle') {
        check(command.snapshotAt._tag === 'Utc' && command.snapshotAt.toJSON() === iso, 'Settlement RPC DateTime encoding');
        check(command.commandId === 'settle-once', 'Stable settlement identity');
      }
      calls += 1; return { _tag: 'Success', value: { accepted: true } };
    };
    const command = { type: 'thread.auto-settle', threadId: 'member', commandId: 'settle-once', snapshotAt: iso };
    check((await host.command(ref, command)).accepted, 'Command result');
    check(command.snapshotAt === iso, 'Persisted input remains serializable');
    orchestration.threadTranscript.run = async (value, request) => {
      check(value === registry && request.input.threadId === ref.threadId, 'Transcript scope');
      return { _tag: 'Success', value: { entries: [] } };
    };
    check((await host.transcript(ref)).entries.length === 0, 'Transcript result');
    check(host.href(ref) === '/env/parent', 'Web route');
    window.desktopBridge = {};
    check(host.href(ref) === '#/env/parent', 'Desktop route');
    delete window.desktopBridge;
    await import('/assets/model-council/ui.mjs');
    check(document.querySelector('#t3-adds-council-composer')?.shadowRoot.querySelector('button'), 'Composer launcher');
    document.querySelector('#t3-adds-council-composer').shadowRoot.querySelector('button').click();
    await new Promise((resolve) => setTimeout(resolve, 30));
    const dialog = document.querySelector('#t3-adds-model-council').shadowRoot.querySelector('dialog');
    check(dialog.open && dialog.textContent.includes('Model Council'), 'Council dialog');
    dialog.close();
    atoms.set(sessions.sessionStateAtom('env'), { _tag: 'Success', value: { authenticated: true, permissions: [] } });
    let refused = false;
    try { await host.command(ref, command); } catch (error) { refused = /permission/.test(error.message); }
    check(refused && calls === 1, 'Denied commands never dispatch');
    return { adapter: 'passed', settlementDateTime: 'passed', uiMount: 'passed', nativeModelCalls: 0 };
  }, b);
  assert.deepEqual(errors, []);
  console.log(JSON.stringify(result));
} finally {
  await browser.close();
}
