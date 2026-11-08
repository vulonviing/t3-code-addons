import test from 'node:test';
import assert from 'node:assert/strict';
import { summarize, formatResetsIn, level, routeRef, pickRow, threadInstance } from '../src/plan.mjs';

const NOW = Date.parse('2026-11-08T12:00:00.000Z');
const provider = (instanceId, driver, windows, extra = {}) => ({
  instanceId, driver, enabled: true, installed: true,
  usageLimits: { checkedAt: '2026-11-08T11:59:00.000Z', windows }, ...extra,
});
const window_ = (label, usedPercent, resetsAt) => ({ id: label, kind: 'other', label, usedPercent, ...(resetsAt && { resetsAt }) });

test('each provider shows its tightest window with its reset time', () => {
  const rows = summarize([
    provider('claude', 'claudeAgent', [window_('5-hour', 29, '2026-11-08T15:12:00.000Z'), window_('Weekly', 10, '2026-11-12T00:00:00.000Z')]),
    provider('codex', 'codex', [window_('Weekly', 82, '2026-11-10T00:00:00.000Z')]),
  ], NOW);
  assert.deepEqual(rows.map((r) => [r.name, r.label, r.remaining, r.level]), [['Claude', '5-hour', 71, 'ok'], ['Codex', 'Weekly', 18, 'low']]);
  assert.equal(rows[0].resetsInMs, 3 * 3600000 + 12 * 60000);
});

test('a window past its reset time counts as full again', () => {
  const [row] = summarize([provider('c', 'codex', [window_('5-hour', 100, '2026-11-08T11:00:00.000Z')])], NOW);
  assert.equal(row.remaining, 100);
  assert.equal(row.resetsInMs, null);
});

test('providers that are disabled, missing, or report no limits are left out', () => {
  const rows = summarize([
    provider('off', 'codex', [window_('w', 1)], { enabled: false }),
    provider('gone', 'codex', [window_('w', 1)], { installed: false }),
    provider('none', 'cursor', []),
    { instanceId: 'bare', driver: 'opencode', enabled: true, installed: true },
    provider('ok', 'codex', [window_('w', 40)]),
  ], NOW);
  assert.deepEqual(rows.map((r) => r.id), ['ok']);
  assert.deepEqual(summarize(null, NOW), []);
});

test('no more than four providers are shown, keeping the scarcest in configured order', () => {
  // Remaining percentages: p0 90, p1 10, p2 50, p3 5, p4 70, p5 20.
  const list = [90, 10, 50, 5, 70, 20].map((remaining, i) => provider(`p${i}`, 'codex', [window_('w', 100 - remaining)]));
  assert.deepEqual(summarize(list, NOW).map((r) => r.id), ['p1', 'p2', 'p3', 'p5']);
});

test('thresholds and duration formatting', () => {
  assert.deepEqual([100, 21, 20, 6, 5, 0].map(level), ['ok', 'ok', 'low', 'low', 'critical', 'critical']);
  assert.deepEqual([20000, 59 * 60000, 3 * 3600000 + 12 * 60000, 49 * 3600000].map(formatResetsIn), ['<1m', '59m', '3h 12m', '2d 1h']);
  assert.deepEqual(routeRef({ hash: '#/env/thread', pathname: '/' }), { environmentId: 'env', threadId: 'thread' });
});

test('the chat\'s own provider is shown by default, a viewer pick wins, and the tightest is the fallback', () => {
  const rows = summarize([
    provider('claude', 'claudeAgent', [window_('Session', 40, '2026-11-08T15:00:00.000Z'), window_('Weekly', 10, '2026-11-12T00:00:00.000Z')]),
    provider('codex', 'codex', [window_('Weekly', 90, '2026-11-12T00:00:00.000Z')]),
  ], NOW);
  assert.deepEqual(rows[0].windows.map((w) => [w.label, w.remaining]), [['Session', 60], ['Weekly', 90]]);
  assert.equal(pickRow(rows, null, 'claude').id, 'claude');
  assert.equal(pickRow(rows, 'codex', 'claude').id, 'codex');
  assert.equal(pickRow(rows, 'gone', 'gone').id, 'codex');
  assert.equal(pickRow([], null, 'claude'), null);
});

test('a provider the viewer is looking at is never dropped from a long list', () => {
  const list = [1, 2, 3, 4, 5].map((n) => provider(`p${n}`, 'codex', [window_('Weekly', n === 5 ? 1 : 50 + n, '2026-11-12T00:00:00.000Z')]));
  assert.ok(summarize(list, NOW, 'p5').some((row) => row.id === 'p5'));
  assert.ok(summarize(list, NOW, 'p4').some((row) => row.id === 'p4'));
});

test('the chat provider is read from the thread selection, falling back to the provider instance', () => {
  assert.equal(threadInstance({ thread: { modelSelection: { instanceId: 'codex' }, providerInstanceId: 'x' } }), 'codex');
  assert.equal(threadInstance({ thread: { providerInstanceId: 'claudeAgent' } }), 'claudeAgent');
  assert.equal(threadInstance(null), null);
});
