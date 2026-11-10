import test from 'node:test';
import assert from 'node:assert/strict';
import { createController } from '../src/controller.mjs';
import { createState } from '../src/state.mjs';
import { MARKER } from '../src/rules.mjs';

const ref = { environmentId: 'e', threadId: 't' };
const selection = { instanceId: 'claude', model: 'opus' };
const model = { instanceId: 'codex', slug: 'gpt-x', label: 'Codex / GPT X' };
const memory = () => { const map = new Map(); return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, String(v)), removeItem: (k) => map.delete(k) }; };

function setup({ status = 'idle', operate = true, fail = false, providers } = {}) {
  const commands = [];
  const fake = {
    status, runs: [],
    parent: () => ({ status: fake.status, modelSelection: selection }),
    projection: () => ({ runs: fake.runs }),
    providers: () => providers ?? [{ instanceId: 'codex', driver: 'codex', displayName: 'Codex', models: [{ slug: 'gpt-x', name: 'GPT X', isLegacy: false }] }],
    canOperate: () => operate,
    async command(_ref, command) { if (fail) throw new Error('boom'); commands.push(command); },
  };
  let n = 0;
  const state = createState(memory());
  return { fake, commands, state, controller: createController({ host: fake, state, newId: () => `id${++n}` }) };
}

test('toggle on dispatches one marked turn on the chat model and goes starting then on', async () => {
  const { fake, commands, controller } = setup();
  assert.equal(controller.status(ref), 'off');
  await controller.toggle(ref);
  assert.equal(commands.length, 1);
  const c = commands[0];
  assert.equal(c.type, 'message.dispatch'); assert.equal(c.threadId, 't'); assert.equal(c.messageId, 'id1');
  assert.equal(c.commandId, 'orchestrator:id1'); assert.ok(c.text.startsWith(MARKER));
  assert.deepEqual(c.attachments, []); assert.deepEqual(c.modelSelection, selection);
  assert.equal(c.dispatchMode.type, 'start_immediately');
  assert.equal(controller.status(ref), 'starting');
  fake.runs.push({ userMessageId: 'id1' });
  assert.equal(controller.status(ref), 'on');
});

test('a running chat gets the turn queued', async () => {
  const { commands, controller } = setup({ status: 'running' });
  await controller.toggle(ref);
  assert.equal(commands[0].dispatchMode.type, 'queue_after_active');
});

test('toggle off sends the end turn and returns to off', async () => {
  const { commands, controller } = setup();
  await controller.toggle(ref); await controller.toggle(ref);
  assert.equal(commands.length, 2); assert.match(commands[1].text, /ended/);
  assert.equal(controller.status(ref), 'off');
});

test('remind and setDefaultModel send turns only while on', async () => {
  const { commands, controller } = setup();
  await controller.remind(ref); await controller.setDefaultModel(ref, model);
  assert.equal(commands.length, 0);
  assert.deepEqual(controller.resolveDefault(ref), model);
  await controller.toggle(ref);
  await controller.remind(ref); await controller.setDefaultModel(ref, null);
  assert.equal(commands.length, 3);
});

test('permission failure and command failure leave the chat off', async () => {
  await assert.rejects(setup({ operate: false }).controller.toggle(ref), /permission/);
  const failing = setup({ fail: true });
  await assert.rejects(failing.controller.toggle(ref), /boom/);
  assert.equal(failing.controller.status(ref), 'off');
});

test('an unavailable stored default resolves to null and is left out of the rules', async () => {
  const { commands, controller, state } = setup({ providers: [] });
  state.setDefaultModel(model);
  assert.equal(controller.resolveDefault(ref), null);
  await controller.toggle(ref);
  assert.ok(!commands[0].text.includes('gpt-x'));
});

test('setEffort stores the choice and posts one update only while on', async () => {
  const { commands, controller, state } = setup();
  await controller.setEffort(ref, 'low');
  assert.equal(state.effort(), 'low');
  assert.equal(commands.length, 0);
  await controller.toggle(ref);
  await controller.setEffort(ref, 'medium');
  assert.equal(commands.length, 2);
  assert.match(commands[1].text, /medium/);
  assert.equal(controller.effort(), 'medium');
});

test('activation uses the stored effort', async () => {
  const { commands, controller } = setup();
  await controller.setEffort(ref, 'low');
  await controller.toggle(ref);
  assert.match(commands[0].text, /use low for every subagent/);
});

test('toggle on a draft promotes first, then sends the rules as the first turn of the real chat', async () => {
  const { commands, state, controller: base, fake } = setup();
  const order = [];
  const controller = createController({ host: { ...fake, async command(r, c) { order.push(c.type); return fake.command(r, c); } }, state, newId: () => 'id1',
    promote: async (draftId) => { order.push(`promote:${draftId}`); return ref; } });
  await controller.toggle({ ...ref, draftId: 'd1' });
  assert.deepEqual(order, ['promote:d1', 'message.dispatch']);
  assert.equal(state.activation(ref).enabled, true);
  assert.equal(commands.length, 1);
});

test('a failed promotion sends nothing and leaves the chat off', async () => {
  const { commands, state, fake } = setup();
  const controller = createController({ host: fake, state, promote: async () => { throw new Error('Pick a model first.'); } });
  await assert.rejects(controller.toggle({ ...ref, draftId: 'd1' }), /Pick a model first/);
  assert.equal(commands.length, 0);
  assert.equal(state.activation(ref).enabled, false);
});
