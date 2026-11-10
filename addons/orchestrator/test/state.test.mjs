import test from 'node:test';
import assert from 'node:assert/strict';
import { createState } from '../src/state.mjs';

const memory = () => { const map = new Map(); return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k) }; };
const broken = { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } };
const a = { environmentId: 'e', threadId: 'a' }, b = { environmentId: 'e', threadId: 'b' };
const model = { instanceId: 'codex', slug: 'gpt-x', label: 'Codex / GPT X' };

test('activation round trips per chat and survives a new state over the same storage', () => {
  const storage = memory();
  const state = createState(storage);
  assert.deepEqual(state.activation(a), { enabled: false, messageId: null });
  state.setEnabled(a, true, 'm1');
  assert.deepEqual(state.activation(a), { enabled: true, messageId: 'm1' });
  assert.equal(state.activation(b).enabled, false);
  assert.deepEqual(createState(storage).activation(a), { enabled: true, messageId: 'm1' });
  state.setEnabled(a, false);
  assert.deepEqual(state.activation(a), { enabled: false, messageId: null });
});

test('default model round trips and clears', () => {
  const state = createState(memory());
  assert.equal(state.defaultModel(), null);
  state.setDefaultModel(model);
  assert.deepEqual(state.defaultModel(), model);
  state.setDefaultModel(null);
  assert.equal(state.defaultModel(), null);
});

test('throwing storage still works in memory', () => {
  const state = createState(broken);
  state.setEnabled(a, true, 'm1'); state.setDefaultModel(model);
  assert.deepEqual(state.activation(a), { enabled: true, messageId: 'm1' });
  assert.deepEqual(state.defaultModel(), model);
});

test('corrupt stored JSON reads as off and no default', () => {
  const storage = memory();
  storage.setItem('t3-adds:orchestrator:chat:e:a', '{nope'); storage.setItem('t3-adds:orchestrator:model', '[[');
  const state = createState(storage);
  assert.equal(state.activation(a).enabled, false);
  assert.equal(state.defaultModel(), null);
});

test('effort defaults to by-task, persists, and rejects unknown values', () => {
  const storage = memory();
  const state = createState(storage);
  assert.equal(state.effort(), 'task');
  state.setEffort('low');
  assert.equal(state.effort(), 'low');
  assert.equal(createState(storage).effort(), 'low');
  state.setEffort('turbo');
  assert.equal(state.effort(), 'task');
  const blocked = createState(broken);
  blocked.setEffort('medium');
  assert.equal(blocked.effort(), 'medium');
});
