const PREFIX = 't3-adds:orchestrator:';
const chatKey = (ref) => `${PREFIX}chat:${ref.environmentId}:${ref.threadId}`;

export function createState(storage) {
  const memory = new Map();
  const read = (key) => {
    if (memory.has(key)) return memory.get(key);
    try { const raw = storage.getItem(key); return raw == null ? null : JSON.parse(raw); } catch { return null; }
  };
  const write = (key, value) => {
    memory.set(key, value ?? null);
    try { if (value == null) storage.removeItem(key); else storage.setItem(key, JSON.stringify(value)); } catch { /* session-only */ }
  };
  return {
    activation(ref) {
      const value = read(chatKey(ref));
      return value && value.enabled === true ? { enabled: true, messageId: value.messageId ?? null } : { enabled: false, messageId: null };
    },
    setEnabled(ref, enabled, messageId = null) { write(chatKey(ref), enabled ? { enabled: true, messageId } : null); },
    defaultModel() {
      const value = read(`${PREFIX}model`);
      return value && value.instanceId && value.slug ? value : null;
    },
    setDefaultModel(model) { write(`${PREFIX}model`, model); },
  };
}
