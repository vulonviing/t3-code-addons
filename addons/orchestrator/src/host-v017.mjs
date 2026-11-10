// These exports are pinned by the installer to the exact installed bundle hashes.
import { al as registry, A as draftStore } from '../utils-BL51zcsk.js';
import { v as orchestration } from '../queries-0E2-XBJB.js';
import { rt as details, it as shells } from '../projectGrouping-aRBPi9Ux.js';
import { ut as server } from '../themePalette-owjsZZI0.js';
import { r as hasScope } from '../session-D2SVRPH0.js';

function unwrap(result) {
  if (result._tag === 'Success') return result.value;
  throw new Error(`T3 request failed: ${JSON.stringify(result.cause, (_k, v) => typeof v === 'bigint' ? String(v) : v).slice(0, 1200)}`);
}

export const host = {
  parent(ref) {
    if (!ref) return null;
    const thread = registry.get(shells.threadShellAtom(ref));
    return thread ? { ...thread, status: thread.source.status } : null;
  },
  projection(ref) { return registry.get(details.threadAtom(ref))?.projection ?? null; },
  canOperate(ref) { return hasScope(ref.environmentId, 'orchestration:operate'); },
  providers(ref) {
    const config = registry.get(server.configValueAtom(ref.environmentId));
    const projectId = ref.projectId ?? this.parent(ref)?.projectId;
    const overrides = config?.settings?.projectSettingsOverrides?.[projectId]?.providerInstances ?? {};
    return (config?.providers ?? []).filter((p) => (overrides[p.instanceId]?.enabled ?? p.enabled) && p.installed && p.status !== 'error');
  },
  async command(ref, command) {
    if (!this.canOperate(ref)) throw new Error('This connection does not have permission to modify chats.');
    return unwrap(await orchestration.v2.dispatchCommand.run(registry, { environmentId: ref.environmentId, input: command }));
  },
  observeParent(ref, listener) {
    return registry.subscribe(shells.threadShellAtom(ref), (thread) => listener(thread ? { ...thread, status: thread.source.status } : null), { immediate: true });
  },
  // Public store actions of the new-chat draft; the host's own first send uses the same ones.
  draft: {
    session: (draftId) => draftStore.getState().getDraftSession(draftId) ?? null,
    composer: (draftId) => draftStore.getState().getComposerDraft(draftId) ?? null,
    markPromoting: (draftId) => draftStore.getState().markDraftThreadPromoting(draftId),
    finalize: (draftId) => draftStore.getState().finalizePromotedDraftThread(draftId),
  },
  observe(ref, listener) {
    return registry.subscribe(details.threadAtom(ref), (value) => listener(value?.projection ?? null), { immediate: true });
  },
};
