// Promotes T3's new-chat draft into a real chat so that messages can be dispatched.
// Only the host's public store actions and the existing command path are used.
export const DRAFT_TIMEOUT_MS = 15_000;

function waitForParent(host, ref, timeoutMs) {
  return new Promise((resolve, reject) => {
    let stop = null;
    let done = false;
    const finish = (error) => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      stop?.();
      if (error) reject(error); else resolve();
    };
    const timer = setTimeout(() => finish(new Error('The chat was created but is not ready yet. Use the button again in the new chat.')), timeoutMs);
    stop = host.observeParent(ref, (parent) => { if (parent) finish(); });
    if (done) stop?.();
  });
}

export function createPromoter({ host, timeoutMs = DRAFT_TIMEOUT_MS }) {
  const inflight = new Map();

  async function run(draftId) {
    const session = host.draft.session(draftId);
    if (!session) throw new Error('This new chat is no longer available.');
    const ref = { environmentId: session.environmentId, threadId: session.threadId };
    if (!host.parent(ref)) {
      const composer = host.draft.composer(draftId);
      const selection = composer?.modelSelectionByProvider?.[composer?.activeProvider];
      if (!selection?.model) throw new Error('Pick a model first.');
      const runtimeMode = session.runtimeMode ?? composer?.runtimeMode;
      if (!runtimeMode) throw new Error('Pick an access mode first.');
      await host.command(ref, {
        type: 'thread.create', commandId: `draft-promote:${draftId}`, threadId: ref.threadId,
        projectId: session.projectId, title: 'New chat', modelSelection: structuredClone(selection),
        runtimeMode, interactionMode: session.interactionMode ?? composer?.interactionMode ?? 'default',
        branch: session.branch ?? null, worktreePath: session.worktreePath ?? null,
        createdBy: 'user', creationSource: 'web',
      });
    }
    await host.draft.markPromoting(draftId);
    await host.draft.finalize(draftId);
    await waitForParent(host, ref, timeoutMs);
    return ref;
  }

  // One promotion per draft at a time; a double click shares the same work.
  return function promote(draftId) {
    if (!inflight.has(draftId)) inflight.set(draftId, run(draftId).finally(() => inflight.delete(draftId)));
    return inflight.get(draftId);
  };
}
