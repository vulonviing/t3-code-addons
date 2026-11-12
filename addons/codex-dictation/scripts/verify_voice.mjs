// Explicit live-service check with synthetic audio, never the user's microphone.
// Usage: T3_ADDS_PLAYWRIGHT=/external/node_modules/playwright-core node scripts/verify_voice.mjs /external/sample.wav
import { createRequire } from 'node:module';
import { spawn } from 'node:child_process';
import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import assert from 'node:assert/strict';
import { createServer } from 'node:http';
const require = createRequire(import.meta.url);
const { chromium } = require(process.env.T3_ADDS_PLAYWRIGHT ?? 'playwright-core');
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const audio = await fs.readFile(process.argv[2]);
// AudioWorklet fetches bypass Playwright routing; serve real local module responses.
const server = createServer(async (request, response) => {
  const name = new URL(request.url, 'http://127.0.0.1').pathname;
  try {
    const module = /^\/src\/[a-z-]+\.mjs$/.test(name);
    const body = module ? await fs.readFile(path.join(root, name)) : '<!doctype html><title>Synthetic voice test</title>';
    response.writeHead(200, { 'Content-Type': module ? 'text/javascript' : 'text/html', 'Cache-Control': 'no-store' }); response.end(body);
  } catch { response.writeHead(404); response.end(); }
});
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
const origin = 'http://127.0.0.1:' + server.address().port;
const helper = spawn('python3', [path.join(root, 'scripts/bridge.py'), '--codex', process.env.T3_ADDS_CODEX ?? 'codex', '--port', '48175', '--origin', origin], { stdio: 'ignore' });
const browser = await chromium.launch({ headless: true, executablePath: process.env.T3_ADDS_TEST_BROWSER,
  // Match the installed Electron host's local-network policy.
  args: ['--disable-features=LocalNetworkAccessChecks', '--autoplay-policy=no-user-gesture-required'] });
const watchdog = setTimeout(() => void browser.close().catch(() => {}), 60000);
try {
  const context = await browser.newContext();
  await context.grantPermissions(['local-network-access'], { origin });
  const page = await context.newPage();
  page.on('console', message => { if (message.type() === 'error') console.error('Synthetic browser:', message.text()); });
  page.on('requestfailed', request => console.error('Synthetic request:', new URL(request.url()).pathname, request.failure()?.errorText));
  await page.goto(origin);
  const result = await page.evaluate(async (audio) => {
    const [{ createTranscript }, { createConnection }] = await Promise.all([import('/src/transcript.mjs'), import('/src/connection.mjs')]);
    const context = new AudioContext();
    const decoded = await context.decodeAudioData(Uint8Array.from(atob(audio), c => c.charCodeAt(0)).buffer);
    const destination = context.createMediaStreamDestination();
    const source = context.createBufferSource(); source.buffer = decoded; source.connect(destination);
    let pc, startedAt = 0, readyAt = 0, levels = 0, failure;
    const ended = new Promise(resolve => { source.onended = resolve; });
    class Peer extends RTCPeerConnection { constructor(...args) { super(...args); pc = this; } }
    const events = [], transcript = createTranscript(); let text = '';
    const call = async (url, value) => {
      // Deliberately delay negotiation while the synthetic speaker is already talking.
      if (url === '/start') await new Promise(resolve => setTimeout(resolve, 2000));
      const result = await fetch('http://127.0.0.1:48175' + url, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-T3-Dictation': '1' }, body: JSON.stringify(value) });
      const body = await result.json(); if (!result.ok) throw new Error(body.error); return body;
    };
    const connection = createConnection({ Peer, call,
      mediaDevices: { async getUserMedia() { startedAt = performance.now(); source.start(context.currentTime + .05); return destination.stream; } },
      onLevel(value) { if (value > .02) levels++; }, onError(error) { failure = error.message; },
      onEvent(event) { events.push(event); const value = transcript.accept(event); if (value !== null) text = value; },
    });
    try {
      await connection.start(); readyAt = performance.now();
      await ended; connection.mute(); await connection.drain();
      await new Promise(resolve => setTimeout(resolve, 5000));
      return { state: pc.connectionState, text, startupDelayMs: Math.round(readyAt - startedAt), levels, failure, events: events.map(e => ({ type: e.type })) };
    } finally { await connection.stop(); await context.close(); }
  }, audio.toString('base64'));
  console.log(JSON.stringify({ state: result.state, text: result.text, startupDelayMs: result.startupDelayMs, levelEvents: result.levels, failure: result.failure }));
  assert.equal(result.state, 'connected');
  assert.ok(result.text.trim(), 'Synthetic speech must produce a user transcript.');
  assert.ok(result.startupDelayMs >= 2000, 'Speech must begin before negotiation completes.');
  assert.ok(result.levels > 0, 'The actual capture pipeline must report speech levels.');
  assert.equal(result.failure, undefined);
  if (process.argv[3]) assert.ok(result.text.toLocaleLowerCase().startsWith(process.argv[3].toLocaleLowerCase()), 'The words spoken before connection readiness must survive.');
} finally { clearTimeout(watchdog); await browser.close(); helper.kill(); await new Promise(resolve => server.close(resolve)); }
