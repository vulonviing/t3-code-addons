import test from 'node:test';
import assert from 'node:assert/strict';
import { createPromoter, afterPromotion } from '../src/draft.mjs';

const session = { environmentId: 'e', threadId: 't', projectId: 'p', runtimeMode: 'full-access', branch: 'main', worktreePath: null };
const composer = { prompt: 'hi', activeProvider: 'claude', modelSelectionByProvider: { claude: { instanceId: 'claude', model: 'opus' } } };

function setup({ fail = false, noModel = false, noSession = false, hold = false, appears = true, existing = false } = {}) {
  const calls = [];
  let shell = existing ? { status: 'idle' } : null;
  const listeners = new Set();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  const host = {
    parent: () => shell,
    observeParent(_ref, cb) { listeners.add(cb); cb(shell); return () => listeners.delete(cb); },
    draft: {
      session: () => (noSession ? null : session),
      composer: () => (noModel ? { ...composer, modelSelectionByProvider: {} } : composer),
      markPromoting: (id) => calls.push(`mark:${id}`),
      finalize: (id) => calls.push(`finalize:${id}`),
    },
    async command(ref, command) {
      if (hold) await gate;
      if (fail) throw new Error('boom');
      calls.push(command);
      if (appears) setTimeout(() => { shell = { status: 'idle' }; listeners.forEach((cb) => cb(shell)); }, 0);
    },
  };
  return { host, calls, release, promote: createPromoter({ host, timeoutMs: 50 }) };
}

test('promotion creates the thread from the draft, then marks, finalizes and waits for the chat', async () => {
  const { promote, calls } = setup();
  assert.deepEqual(await promote('d1'), { environmentId: 'e', threadId: 't' });
  const [create, mark, finalize] = calls;
  assert.equal(create.type, 'thread.create');
  assert.equal(create.threadId, 't');
  assert.equal(create.commandId, 'draft-promote:d1');
  assert.deepEqual(create.modelSelection, composer.modelSelectionByProvider.claude);
  assert.equal(create.projectId, 'p');
  assert.equal(create.runtimeMode, 'full-access');
  assert.deepEqual([mark, finalize], ['mark:d1', 'finalize:d1']);
});

test('a failed create neither marks nor finalizes the draft', async () => {
  const { promote, calls } = setup({ fail: true });
  await assert.rejects(promote('d1'), /boom/);
  assert.deepEqual(calls, []);
});

test('a draft without a model asks for one and dispatches nothing', async () => {
  const { promote, calls } = setup({ noModel: true });
  await assert.rejects(promote('d1'), /Pick a model first\./);
  assert.deepEqual(calls, []);
});

test('a missing draft is reported', async () => {
  await assert.rejects(setup({ noSession: true }).promote('d1'), /no longer available/);
});

test('a double click shares one create', async () => {
  const { promote, calls, release } = setup({ hold: true });
  const first = promote('d1'), second = promote('d1');
  assert.equal(first, second);
  release();
  await first;
  assert.equal(calls.filter((c) => c.type === 'thread.create').length, 1);
});

test('a retry after the thread already exists skips the create', async () => {
  const { promote, calls } = setup({ existing: true });
  await promote('d1');
  assert.deepEqual(calls, ['mark:d1', 'finalize:d1']);
});

test('times out accurately after the draft was already promoted', async () => {
  const { promote, calls } = setup({ appears: false });
  await assert.rejects(promote('d1'), /chat was created but is not ready yet/);
  assert.deepEqual(calls.slice(1), ['mark:d1', 'finalize:d1']);
});

test('a failure after promotion says the chat exists and how to continue', async () => {
  await assert.rejects(afterPromotion(async () => { throw new Error('Transcript unavailable.'); }), /chat was created.*Transcript unavailable\..*Press Start again in the new chat/);
  assert.equal(await afterPromotion(async () => 7), 7);
});
