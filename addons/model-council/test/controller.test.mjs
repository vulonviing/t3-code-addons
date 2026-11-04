import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixtures.mjs';
import { CouncilController, awaitAnswer } from '../src/controller.mjs';

function environment({ failModel, stall = false, busyParent = false } = {}) {
  const commands = new Map(), projections = new Map(), observers = new Map(), records = new Map();
  const calls = [];
  const notify = (id) => observers.get(id)?.forEach((cb) => cb(projections.get(id)));
  const parent = { status: busyParent ? 'running' : 'idle', modelSelection: { instanceId: 'selected', model: 'selected-final' } };
  const host = {
    parent: () => parent,
    projection: (ref) => projections.get(ref.threadId),
    observe(ref, cb) {
      const listeners = observers.get(ref.threadId) ?? new Set(); observers.set(ref.threadId, listeners); listeners.add(cb);
      cb(projections.get(ref.threadId)); return () => listeners.delete(cb);
    },
    async command(_ref, command) {
      calls.push(command);
      if (commands.has(command.commandId)) return;
      commands.set(command.commandId, command);
      if (command.type === 'thread.create') projections.set(command.threadId, { runs: [], turnItems: [] });
      if (command.type === 'message.dispatch') {
        const projection = projections.get(command.threadId) ?? { runs: [], turnItems: [] };
        projections.set(command.threadId, projection);
        const run = { id: command.messageId + '-run', userMessageId: command.messageId, status: 'running' };
        projection.runs.push(run);
        if (!stall) {
          run.status = command.modelSelection.model === failModel ? 'failed' : 'completed';
          projection.turnItems.push({ id: command.messageId + '-answer', runId: run.id, type: 'assistant_message', text: `${command.modelSelection.model} says: ${command.text.startsWith('Model Council') ? 'FINAL' : command.text.includes('only peer-review') ? 'REVIEW' : 'OPINION'}` });
          notify(command.threadId);
        }
      }
    },
  };
  const storage = { async save(job) { records.set(job.id, structuredClone(job)); }, async get(id) { return records.get(id); } };
  return { host, storage, records, projections, observers, calls, commands, parent };
}

test('three models complete two rounds before one synthesis in original chat', async () => {
  const env = environment(), job = fixture();
  job.members.forEach((m, i) => { m.selection.options = [{ id: 'effort', value: i ? 'high' : 'medium' }]; });
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed');
  const dispatches = [...env.commands.values()].filter((c) => c.type === 'message.dispatch');
  assert.equal(dispatches.length, 7);
  assert.equal(dispatches.at(-1).threadId, 'parent');
  assert.equal(dispatches.at(-1).modelSelection.model, 'selected-final');
  const opinions = dispatches.filter((c) => c.text.includes('Independently assess'));
  assert.equal(new Set(opinions.map((c) => c.text)).size, 1);
  const reviews = dispatches.filter((c) => c.text.includes('only peer-review'));
  assert.equal(new Set(reviews.map((c) => c.text)).size, 1);
  assert.equal(job.members.every((m) => m.opinion && m.review), true);
  for (const member of job.members) {
    const create = [...env.commands.values()].find((c) => c.type === 'thread.create' && c.threadId === member.threadId);
    assert.deepEqual(create.modelSelection.options, member.selection.options);
    const turns = dispatches.filter((c) => c.threadId === member.threadId);
    assert.equal(turns.length, 2);
    assert.ok(turns.every((c) => JSON.stringify(c.modelSelection.options) === JSON.stringify(member.selection.options)));
  }
  assert.ok([...env.observers.values()].every((s) => s.size === 0));
});

test('failed member is reported; remaining two finish without fabricated opinion', async () => {
  const env = environment({ failModel: 'claude' }), job = fixture();
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed');
  assert.match(job.members[0].error, /failed/);
  const final = [...env.commands.values()].find((c) => c.threadId === 'parent');
  const missing = final.context.records.find((r) => r.payload.member === 'claude' && 'opinion' in r.payload);
  assert.equal(missing.payload.opinion, null);
  assert.match(missing.payload.error, /failed/);
});

test('no synthesis with fewer than two independent answers', async () => {
  const env = environment({ failModel: 'claude' }), job = fixture(); job.members.pop();
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'failed');
  assert.equal(env.calls.some((c) => c.type === 'message.dispatch' && c.threadId === 'parent'), false);
});

test('reloading after native acceptance reuses stable commands and does not bill duplicate turns', async () => {
  const env = environment(), job = fixture();
  await new CouncilController(env).start(job);
  const count = env.commands.size;
  const resumed = structuredClone(job); resumed.stage = 'opinions'; resumed.members.forEach((m) => { delete m.opinion; delete m.review; }); resumed.finalSent = false;
  await new CouncilController(env).start(resumed);
  assert.equal(resumed.stage, 'completed'); assert.equal(env.commands.size, count);
});

test('busy original chat holds synthesis until explicitly released', async () => {
  const env = environment({ busyParent: true }), job = fixture(), controller = new CouncilController(env);
  await controller.start(job);
  assert.equal(job.stage, 'ready'); assert.equal(job.finalSent, false);
  env.parent.status = 'idle'; await controller.finish(job);
  assert.equal(job.stage, 'completed');
});

test('resuming accepted synthesis waits for the existing final run even when parent is busy', async () => {
  const env = environment(), job = fixture(), controller = new CouncilController(env);
  await controller.start(job);
  const count = env.commands.size; job.stage = 'synthesis'; env.parent.status = 'running';
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed'); assert.equal(env.commands.size, count);
});

test('cancellation stops council children and never interrupts unrelated original work', async () => {
  const env = environment({ stall: true }), job = fixture(), controller = new CouncilController({ ...env, timeoutMs: 500 });
  const running = controller.start(job);
  await new Promise((resolve) => setTimeout(resolve, 10));
  await controller.cancel(job); await running;
  assert.equal(job.stage, 'cancelled');
  assert.equal(env.calls.filter((c) => c.type === 'thread.stop').length, 3);
  assert.equal(env.calls.some((c) => c.type === 'run.interrupt'), false);
  assert.ok([...env.observers.values()].every((s) => s.size === 0));
});

test('timeout releases subscriptions and returns an actionable error', async () => {
  const env = environment({ stall: true }), job = fixture();
  await new CouncilController({ ...env, timeoutMs: 5 }).start(job);
  assert.equal(job.stage, 'failed');
  assert.ok(job.members.every((m) => /timed out/.test(m.error)));
  assert.ok([...env.observers.values()].every((s) => s.size === 0));
});

test('pre-aborted wait never subscribes', async () => {
  const abort = new AbortController(); abort.abort();
  await assert.rejects(awaitAnswer({ observe() { throw new Error('must not subscribe'); } }, {}, 'x', abort.signal), { name: 'AbortError' });
});
