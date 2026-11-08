import test from 'node:test';
import assert from 'node:assert/strict';
import { routeRef, summarize, formatTokens, formatAge, shortModel, cliLabel } from '../src/usage.mjs';

const turn = (providerThreadId, model, input, cached, output, extra = {}) => ({
  providerThreadId, status: 'completed',
  turnTokenUsage: { usageStatus: 'complete', inputTokens: input, cachedInputTokens: cached, outputTokens: output, models: [model] },
  ...extra,
});
const projection = {
  thread: { createdAt: '2026-11-08T00:00:00.000Z' },
  providerThreads: [{ id: 'a', driver: 'claudeAgent' }, { id: 'b', driver: 'codex' }],
  providerTurns: [
    turn('a', 'claude-sonnet-5-5', 8000, 6000, 1000),
    turn('a', 'claude-opus-5-5', 1800, 900, 200),
    turn('b', 'gpt-5.5', 900, 0, 100),
    { providerThreadId: 'a', status: 'running' },
    { providerThreadId: 'a', status: 'completed', turnTokenUsage: { usageStatus: 'unavailable' } },
  ],
};

test('summarize totals processed tokens and attributes them to models and CLIs', () => {
  const usage = summarize(projection, Date.parse('2026-11-08T00:32:00.000Z'));
  assert.equal(usage.total, 12000);
  assert.equal(usage.input, 10700);
  assert.equal(usage.output, 1300);
  assert.equal(usage.turns, 3);
  assert.equal(usage.missing, 1, 'a running turn is not missing; a finished turn without data is');
  assert.deepEqual(usage.byModel.map((m) => [m.key, m.tokens]), [['claude-sonnet-5-5', 9000], ['claude-opus-5-5', 2000], ['gpt-5.5', 1000]]);
  assert.deepEqual(usage.byCli.map((c) => [c.key, c.tokens]), [['claude', 11000], ['codex', 1000]]);
  assert.equal(usage.byModel[0].share, 0.75);
  assert.equal(usage.ageMs, 32 * 60000);
  assert.ok(Math.abs(usage.cacheShare - 6900 / 10700) < 1e-9);
});

test('summarize handles an empty or missing projection', () => {
  for (const value of [null, {}, { providerTurns: [] }]) {
    const usage = summarize(value);
    assert.equal(usage.total, 0);
    assert.deepEqual(usage.byModel, []);
    assert.equal(usage.ageMs, null);
  }
});

test('turns that used several models are grouped together rather than guessed apart', () => {
  const usage = summarize({ providerTurns: [{ providerThreadId: 'x', turnTokenUsage: { usageStatus: 'complete', inputTokens: 10, outputTokens: 5, models: ['a', 'b'] } }] });
  assert.equal(usage.byModel[0].key, 'a + b');
  assert.equal(usage.byCli[0].key, 'unknown');
});

test('formatters', () => {
  assert.deepEqual([0, 999, 1000, 12400, 124830, 1500000, 12300000].map(formatTokens), ['0', '999', '1K', '12K', '125K', '1.5M', '12.3M']);
  assert.deepEqual([30000, 90000, 3600000 * 2 + 600000, 86400000 * 2 + 3600000 * 3].map(formatAge), ['<1m', '1m', '2h 10m', '2d 3h']);
  assert.equal(shortModel('claude-sonnet-5-5'), 'sonnet-5-5');
  assert.equal(shortModel('a-very-long-model-name-indeed'), 'a-very-long-mod…');
  assert.equal(cliLabel('claudeAgent'), 'claude');
  assert.equal(cliLabel('futureDriver'), 'futureDriver');
});

test('routeRef reads desktop hash routes and web paths, and ignores non-thread pages', () => {
  assert.deepEqual(routeRef({ hash: '#/env/thread', pathname: '/' }), { environmentId: 'env', threadId: 'thread' });
  assert.deepEqual(routeRef({ hash: '', pathname: '/env%201/t' }), { environmentId: 'env 1', threadId: 't' });
  assert.equal(routeRef({ hash: '', pathname: '/settings/appearance' }), null);
  assert.equal(routeRef({ hash: '', pathname: '/' }), null);
});

test('each model carries its own input, cached, output, and turn counts', () => {
  const usage = summarize({
    providerThreads: [{ id: 'a', driver: 'claudeAgent' }],
    providerTurns: [
      { providerThreadId: 'a', status: 'completed', turnTokenUsage: { usageStatus: 'complete', inputTokens: 800, cachedInputTokens: 600, outputTokens: 100, models: ['m1'] } },
      { providerThreadId: 'a', status: 'completed', turnTokenUsage: { usageStatus: 'complete', inputTokens: 200, cachedInputTokens: 0, outputTokens: 50, models: ['m1'] } },
      { providerThreadId: 'a', status: 'completed', turnTokenUsage: { usageStatus: 'complete', inputTokens: 100, cachedInputTokens: 10, outputTokens: 10, models: ['m2'] } },
    ],
  });
  assert.deepEqual(usage.byModel.map(({ key, tokens, input, cached, output, turns }) => ({ key, tokens, input, cached, output, turns })), [
    { key: 'm1', tokens: 1150, input: 1000, cached: 600, output: 150, turns: 2 },
    { key: 'm2', tokens: 110, input: 100, cached: 10, output: 10, turns: 1 },
  ]);
});
