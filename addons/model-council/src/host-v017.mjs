// These exports are pinned by the installer to the exact installed bundle hashes.
import { al as registry, nS as dateTime } from '../utils-BL51zcsk.js';
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
    const projectId = this.parent(ref)?.projectId;
    const overrides = config?.settings?.projectSettingsOverrides?.[projectId]?.providerInstances ?? {};
    return (config?.providers ?? []).filter((p) => (overrides[p.instanceId]?.enabled ?? p.enabled) && p.installed && p.status !== 'error');
  },
  async command(ref, command) {
    if (!this.canOperate(ref)) throw new Error('This connection does not have permission to modify chats.');
    // Council records persist ISO strings; the native RPC command takes decoded Effect DateTime values.
    const input = command.type === 'thread.auto-settle'
      ? { ...command, snapshotAt: dateTime(command.snapshotAt) } : command;
    return unwrap(await orchestration.v2.dispatchCommand.run(registry, { environmentId: ref.environmentId, input }));
  },
  async transcript(ref) {
    return unwrap(await orchestration.threadTranscript.run(registry, { environmentId: ref.environmentId, input: { threadId: ref.threadId } }));
  },
  observe(ref, listener) {
    return registry.subscribe(details.threadAtom(ref), (value) => listener(value?.projection ?? null), { immediate: true });
  },
  href(ref) {
    const route = `/${encodeURIComponent(ref.environmentId)}/${encodeURIComponent(ref.threadId)}`;
    return window.desktopBridge ? `#${route}` : route;
  },
};
