import { contribution, opinionPrompt, reviewPrompt, synthesisMessage } from './protocol.mjs';

const TERMINAL = new Set(['completed', 'failed', 'cancelled', 'interrupted', 'rolled_back']);
const creation = { createdBy: 'user', creationSource: 'web' };
const cancelled = () => new DOMException('The council was stopped.', 'AbortError');

export function awaitAnswer(host, ref, messageId, signal, timeoutMs = 15 * 60_000) {
  return new Promise((resolve, reject) => {
    let stop, settled = false;
    const finish = (error, value) => {
      if (settled) return;
      settled = true; clearTimeout(timer); stop?.(); signal?.removeEventListener('abort', abort);
      error ? reject(error) : resolve(value);
    };
    const abort = () => finish(cancelled());
    const timer = setTimeout(() => finish(new Error('The model response timed out (15-minute limit).')), timeoutMs);
    if (signal?.aborted) { abort(); return; }
    signal?.addEventListener('abort', abort, { once: true });
    try {
      stop = host.observe(ref, (projection) => {
        if (!projection) return;
        const run = projection.runs.find((r) => r.userMessageId === messageId);
        if (!run || !TERMINAL.has(run.status)) return;
        const items = projection.turnItems ?? projection.visibleTurnItems.map((e) => e.item);
        if (run.status !== 'completed') {
          const failure = items.findLast((i) => i.runId === run.id && i.type === 'error');
          finish(new Error(failure?.failure?.message ?? `The model turn ended with status: ${run.status}.`)); return;
        }
        const messages = items.filter((i) => i.runId === run.id && i.type === 'assistant_message' && i.text?.trim());
        if (messages.length === 0) {
          const plans = items.filter((i) => i.runId === run.id && i.type === 'proposed_plan' && i.markdown?.trim());
          if (plans.length) { finish(null, plans.map((i) => i.markdown).join('\n\n')); return; }
          finish(new Error('The model did not produce a visible answer.')); return;
        }
        finish(null, messages.map((i) => i.text).join('\n\n'));
      });
      if (settled) stop?.();
    } catch (error) { finish(error); }
  });
}

export class CouncilController {
  constructor({ host, storage, changed = () => {}, timeoutMs }) {
    this.host = host; this.storage = storage; this.changed = changed; this.timeoutMs = timeoutMs;
    this.running = new Map();
    this.stops = new Map();
  }
  async persist(job) { await this.storage.save(job); this.changed(job); }
  async ensureActive(job, signal) {
    const stored = await this.storage.get(job.id);
    if (signal.aborted || job.cancelRequested || stored?.cancelRequested) throw cancelled();
  }
  start(job) {
    if (this.running.has(job.id)) return this.running.get(job.id).promise;
    const abort = new AbortController();
    const promise = this.execute(job, abort.signal).finally(() => this.running.delete(job.id));
    this.running.set(job.id, { abort, promise });
    return promise;
  }
  async send(job, threadId, messageId, prompt, selection) {
    const message = typeof prompt === 'string' ? { text: prompt } : prompt;
    return this.host.command(job.ref, {
      type: 'message.dispatch', commandId: `council:${job.id}:${messageId}`, threadId, messageId, ...message,
      attachments: [], modelSelection: selection, dispatchMode: { type: 'start_immediately' }, ...creation,
    });
  }
  async memberTurn(job, member, stage, signal, prompt) {
    const ref = { environmentId: job.ref.environmentId, threadId: member.threadId };
    try {
      await this.ensureActive(job, signal);
      if (!member.created) {
        await this.host.command(job.ref, {
          type: 'thread.create', commandId: `council:${job.id}:${member.threadId}:create`, threadId: member.threadId,
          projectId: job.parent.projectId, title: `Model Council · ${member.label} · ${job.question.slice(0, 55)}`,
          modelSelection: member.selection, runtimeMode: job.parent.runtimeMode, interactionMode: 'plan',
          branch: job.parent.branch, worktreePath: job.parent.worktreePath, ...creation,
        });
        member.created = true; await this.persist(job);
      }
      await this.ensureActive(job, signal);
      await this.send(job, member.threadId, member[`${stage}MessageId`], prompt, member.selection);
      await this.ensureActive(job, signal);
      const answer = await awaitAnswer(this.host, ref, member[`${stage}MessageId`], signal, this.timeoutMs);
      member[stage] = contribution(answer, member.label); delete member.error;
    } catch (error) {
      if (signal.aborted || error.name === 'AbortError') { await this.stopMember(job, member); throw error; }
      member.error = error.message;
      await this.stopMember(job, member);
    }
    await this.persist(job);
  }
  async execute(job, signal) {
    try {
      if (['completed', 'cancelled', 'failed'].includes(job.stage)) return;
      await this.persist(job);
      if (job.cancelRequested) { await this.cancel(job); return; }
      if (job.stage === 'opinions') {
        const prompt = opinionPrompt(job);
        await Promise.allSettled(job.members.filter((m) => !m.opinion && !m.error).map((m) => this.memberTurn(job, m, 'opinion', signal, prompt)));
        await this.ensureActive(job, signal);
        if (job.members.filter((m) => m.opinion).length < 2) throw new Error('The council needs at least two independent opinions. Check the member chats.');
        job.stage = 'reviews'; await this.persist(job);
      }
      if (job.stage === 'reviews') {
        const prompt = reviewPrompt(job);
        await Promise.allSettled(job.members.filter((m) => m.opinion && !m.review && !m.error).map((m) => this.memberTurn(job, m, 'review', signal, prompt)));
        await this.ensureActive(job, signal);
        if (!job.members.some((m) => m.review)) throw new Error('The peer-review round could not be completed.');
        job.stage = 'synthesis'; await this.persist(job);
      }
      await this.ensureActive(job, signal);
      if (job.stage === 'synthesis') {
        // Do not interrupt or queue behind unrelated work in the original chat.
        const parent = this.host.parent(job.ref);
        if (!job.finalSent && (!parent || ['preparing', 'queued', 'starting', 'running', 'waiting'].includes(parent.status))) {
          job.stage = 'ready'; await this.persist(job); return;
        }
        if (!job.finalSent) {
          if (!job.finalPrepared) {
            job.finalSelection = structuredClone(parent.modelSelection);
            job.finalPrepared = true; await this.persist(job);
          }
          await this.send(job, job.ref.threadId, job.finalMessageId, synthesisMessage(job), job.finalSelection);
          job.finalSent = true; await this.persist(job);
        }
        await awaitAnswer(this.host, job.ref, job.finalMessageId, signal, this.timeoutMs);
        job.stage = 'completed'; await this.persist(job);
      }
    } catch (error) {
      job.stage = signal.aborted || error.name === 'AbortError' ? 'cancelled' : 'failed'; job.error = error.message;
      await this.stopChildren(job); await this.persist(job);
    }
  }
  async finish(job) {
    if (job.stage !== 'ready') return;
    job.stage = 'synthesis'; await this.persist(job); return this.start(job);
  }
  async stopMember(job, member) {
    if (!member.created) return;
    const key = `${job.id}:${member.threadId}`;
    if (!this.stops.has(key)) this.stops.set(key, (async () => {
      try { await this.host.command(job.ref, { type: 'thread.stop', commandId: `council:${job.id}:${member.threadId}:stop`, threadId: member.threadId, reason: 'Model Council stopped' }); }
      catch (error) { member.stopError = error.message; }
    })());
    await this.stops.get(key);
  }
  async stopChildren(job) { await Promise.all(job.members.map((m) => this.stopMember(job, m))); }
  async cancel(job) {
    job.cancelRequested = true; await this.persist(job);
    this.running.get(job.id)?.abort.abort();
    await this.stopChildren(job);
    // Only interrupt our final run, never newer work in the user's chat.
    if (job.finalSent) {
      const run = this.host.projection(job.ref)?.runs.find((r) => r.userMessageId === job.finalMessageId);
      if (run && !TERMINAL.has(run.status)) {
        await this.host.command(job.ref, { type: 'run.interrupt', commandId: `council:${job.id}:final:stop`, threadId: job.ref.threadId, runId: run.id, reason: 'Model Council stopped' });
      }
    }
    job.stage = 'cancelled'; await this.persist(job);
  }
}
