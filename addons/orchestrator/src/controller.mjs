import { activationText, updateText, reminderText, endText } from './rules.mjs';

const BUSY = new Set(['preparing', 'queued', 'starting', 'running', 'waiting']);
const creation = { createdBy: 'user', creationSource: 'web' };

export function createController({ host, state, newId = () => crypto.randomUUID() }) {
  const resolveDefault = (ref) => {
    const model = state.defaultModel();
    if (!model) return null;
    const provider = host.providers(ref).find((p) => p.instanceId === model.instanceId);
    return provider?.models.some((m) => m.slug === model.slug && !m.isLegacy) ? model : null;
  };

  async function send(ref, text, messageId = newId()) {
    const parent = host.parent(ref);
    if (!parent) throw new Error('This chat is not available.');
    await host.command(ref, {
      type: 'message.dispatch', commandId: `orchestrator:${messageId}`, threadId: ref.threadId, messageId, text, attachments: [],
      modelSelection: structuredClone(parent.modelSelection),
      dispatchMode: { type: BUSY.has(parent.status) ? 'queue_after_active' : 'start_immediately' }, ...creation,
    });
    return messageId;
  }
  const requireOperate = (ref) => {
    if (!host.canOperate(ref)) throw new Error('This connection does not have permission to modify chats.');
  };

  return {
    resolveDefault,
    status(ref) {
      const { enabled, messageId } = state.activation(ref);
      if (!enabled) return 'off';
      return host.projection(ref)?.runs.some((run) => run.userMessageId === messageId) ? 'on' : 'starting';
    },
    async toggle(ref) {
      requireOperate(ref);
      if (state.activation(ref).enabled) {
        await send(ref, endText());
        state.setEnabled(ref, false);
      } else {
        const messageId = await send(ref, activationText(resolveDefault(ref), state.effort()));
        state.setEnabled(ref, true, messageId);
      }
    },
    async remind(ref) {
      if (!state.activation(ref).enabled) return;
      requireOperate(ref);
      await send(ref, reminderText(resolveDefault(ref), state.effort()));
    },
    effort: () => state.effort(),
    async setEffort(ref, value) {
      state.setEffort(value);
      if (!state.activation(ref).enabled) return;
      requireOperate(ref);
      await send(ref, updateText(resolveDefault(ref), state.effort()));
    },
    async setDefaultModel(ref, model) {
      state.setDefaultModel(model);
      if (!state.activation(ref).enabled) return;
      requireOperate(ref);
      await send(ref, updateText(resolveDefault(ref), state.effort()));
    },
  };
}
