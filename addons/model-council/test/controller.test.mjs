import test from 'node:test';
import assert from 'node:assert/strict';
import { fixture } from './fixtures.mjs';
import { CouncilController, awaitAnswer } from '../src/controller.mjs';

function environment({ failModel, stall = false, busyParent = false, answer, settleFailure = false, onDispatch } = {}) {
  const commands = new Map(), projections = new Map(), observers = new Map(), records = new Map();
  const calls = [], threads = new Map();
  const notify = (id) => observers.get(id)?.forEach((cb) => cb(projections.get(id)));
  const parent = { status: busyParent ? 'running' : 'idle', modelSelection: { instanceId: 'selected', model: 'selected-final' } };
  const host = {
    parent: (ref) => ref.threadId === 'parent' ? parent : threads.get(ref.threadId),
    projection: (ref) => projections.get(ref.threadId),
    observe(ref, cb) {
      const listeners = observers.get(ref.threadId) ?? new Set(); observers.set(ref.threadId, listeners); listeners.add(cb);
      cb(projections.get(ref.threadId)); return () => listeners.delete(cb);
    },
    async command(_ref, command) {
      calls.push(command);
      if (commands.has(command.commandId)) return;
      commands.set(command.commandId, command);
      if (command.type === 'thread.create') {
        projections.set(command.threadId, { runs: [], turnItems: [] });
        threads.set(command.threadId, { status: 'idle', updatedAt: '2026-01-01T00:00:00.000Z', settledOverride: null });
      }
      if (command.type === 'thread.auto-settle') {
        if (settleFailure) throw new Error('Settlement unavailable.');
        const updatedAt = threads.get(command.threadId).updatedAt;
        assert.equal(command.snapshotAt, updatedAt.toJSON?.() ?? updatedAt);
        threads.get(command.threadId).settledOverride = 'settled';
      }
      if (command.type === 'thread.stop') {
        for (const run of projections.get(command.threadId)?.runs ?? []) if (run.status === 'running') run.status = 'interrupted';
      }
      if (command.type === 'message.dispatch') {
        const projection = projections.get(command.threadId) ?? { runs: [], turnItems: [] };
        projections.set(command.threadId, projection);
        const run = { id: command.messageId + '-run', userMessageId: command.messageId, status: 'running' };
        projection.runs.push(run);
        if (!stall) {
          run.status = command.modelSelection.model === failModel ? 'failed' : 'completed';
          projection.turnItems.push({ id: command.messageId + '-answer', runId: run.id, type: 'assistant_message', text: answer?.(command) ?? `${command.modelSelection.model} says: ${command.text.startsWith('Model Council') ? 'FINAL' : command.text.includes('Peer-review round') ? 'REVIEW' : 'OPINION'}` });
          onDispatch?.(command, { projections, threads });
          notify(command.threadId);
        }
      }
    },
  };
  const storage = { async save(job) { records.set(job.id, structuredClone(job)); }, async get(id) { return records.get(id); } };
  return { host, storage, records, projections, observers, calls, commands, parent, threads };
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
  const reviews = dispatches.filter((c) => c.text.includes('Peer-review round'));
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
  const resumed = structuredClone(job); resumed.stage = 'opinions'; resumed.round = 2; delete resumed.stopReason; resumed.members.forEach((m) => { delete m.opinion; delete m.review; m.reviews = []; delete m.done; }); resumed.finalSent = false;
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

const dispatchesFor = (env, member) => env.calls.filter((c) => c.type === 'message.dispatch' && c.threadId === member.threadId);
const roundOf = (command) => Number(/Peer-review round (\d+)/.exec(command.text)?.[1] ?? 1);

test('ten-round limit is enforced when models omit the control line', async () => {
  const env = environment(), job = fixture(); job.maxRounds = 10;
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed'); assert.equal(job.roundsCompleted, 10);
  assert.equal(job.stopReason, 'round-limit');
  assert.ok(job.members.every((m) => dispatchesFor(env, m).length === 10));
  for (let round = 2; round <= 10; round++) {
    const prompts = env.calls.filter((c) => c.type === 'message.dispatch' && roundOf(c) === round);
    assert.equal(new Set(prompts.map((c) => c.text)).size, 1);
  }
  assert.equal(env.calls.filter((c) => c.type === 'message.dispatch' && c.threadId === 'parent').length, 1);
});

test('individual members finish early while others continue with their last positions', async () => {
  const env = environment({ answer: (c) => `${c.modelSelection.model} position round ${roundOf(c)}\n{"councilStatus":"${roundOf(c) >= (c.modelSelection.model === 'claude' ? 2 : 3) ? 'done' : 'continue'}"}` });
  const job = fixture(); job.maxRounds = 5;
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed'); assert.equal(job.roundsCompleted, 3);
  assert.equal(job.stopReason, 'members-finished');
  assert.deepEqual(job.members.map((m) => dispatchesFor(env, m).length), [2, 3, 3]);
  const thirdRound = env.calls.find((c) => c.type === 'message.dispatch' && roundOf(c) === 3);
  assert.match(thirdRound.text, /claude position round 2/);
  assert.match(thirdRound.text, /finished debating/);
  assert.ok(job.members.every((m) => m.done));
  const final = env.calls.find((c) => c.type === 'message.dispatch' && c.threadId === 'parent');
  assert.equal(final.context.records[0].payload.stopReason, 'members-finished');
});

test('reload during a later round reuses accepted message IDs and preserves early exits', async () => {
  const job = fixture(); job.maxRounds = 5;
  let saved;
  const env = environment({ onDispatch(c) {
    if (roundOf(c) === 3 && !saved) saved = structuredClone(env.records.get(job.id));
  }, answer: (c) => `${c.modelSelection.model} round ${roundOf(c)}\n{"councilStatus":"${c.modelSelection.model === 'claude' && roundOf(c) >= 2 ? 'done' : 'continue'}"}` });
  await new CouncilController(env).start(job);
  const count = env.commands.size;
  assert.equal(saved.round, 3);
  await new CouncilController(env).start(saved);
  assert.equal(saved.stage, 'completed'); assert.equal(env.commands.size, count);
  assert.equal(saved.members[0].reviews.length, 1);
  assert.equal(saved.members[0].done, true);
});

test('legacy unfinished jobs retain two rounds and their accepted review IDs', async () => {
  const env = environment(), job = fixture();
  job.version = 1; delete job.maxRounds; delete job.round;
  job.members.forEach((m) => delete m.reviews);
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed'); assert.equal(job.maxRounds, 2);
  assert.ok(job.members.every((m) => m.reviews[0].messageId === m.reviewMessageId));
});

test('completed councils settle only their member chats, after the final answer', async () => {
  const env = environment(), job = fixture();
  await new CouncilController(env).start(job);
  const settles = env.calls.filter((c) => c.type === 'thread.auto-settle');
  assert.deepEqual(settles.map((c) => c.threadId), job.members.map((m) => m.threadId));
  assert.ok(job.members.every((m) => m.settled));
  assert.equal(job.cleanupPending, false);
  const finalIndex = env.calls.findIndex((c) => c.type === 'message.dispatch' && c.threadId === 'parent');
  assert.ok(settles.every((c) => env.calls.indexOf(c) > finalIndex));
});

test('settlement failure is visible without losing the completed council', async () => {
  const env = environment({ settleFailure: true }), job = fixture();
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed');
  assert.ok(job.members.every((m) => /unavailable/.test(m.settleError)));
});

test('settlement snapshots decode native Effect DateTime values before persistence', async () => {
  const timestamp = '2026-01-01T00:00:00.000Z';
  const env = environment({ onDispatch(command, { threads }) {
    if (command.threadId === 'parent') {
      for (const thread of threads.values()) thread.updatedAt = {
        _tag: 'Utc', epochMilliseconds: Date.parse(timestamp),
        toString: () => `DateTime.Utc(${timestamp})`, toJSON: () => timestamp,
      };
    }
  } });
  const job = fixture();
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed');
  assert.ok(job.members.every((member) => member.settled && member.settleSnapshotAt === timestamp));
  assert.equal(env.calls.filter((command) => command.type === 'thread.auto-settle').length, 3);
});

test('settlement skips member chats reused for unrelated work or pinned by the user', async () => {
  const job = fixture();
  const env = environment({ onDispatch(c, { projections, threads }) {
    if (c.threadId === 'parent') {
      projections.get(job.members[0].threadId).runs.push({ status: 'running', userMessageId: 'unrelated' });
      threads.get(job.members[1].threadId).pinnedAt = '2026-01-01T00:00:00.000Z';
    }
  } });
  await new CouncilController(env).start(job);
  assert.equal(job.stage, 'completed');
  assert.match(job.members[0].settleError, /unrelated work/);
  assert.match(job.members[1].settleError, /pinned/);
  assert.equal(job.members[2].settled, true);
});

test('pending settlement resumes after reload without resending model turns', async () => {
  const env = environment(), job = fixture();
  await new CouncilController(env).start(job);
  const count = env.commands.size;
  job.cleanupPending = true; job.members.forEach((m) => delete m.settled);
  await new CouncilController(env).start(job);
  assert.equal(env.commands.size, count);
  assert.ok(job.members.every((m) => m.settled));
  assert.equal(job.cleanupPending, false);
});
