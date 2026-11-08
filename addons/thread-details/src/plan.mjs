export function routeRef(location) {
  const path = location.hash?.startsWith('#/') ? location.hash.slice(1) : location.pathname;
  const parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  return parts.length === 2 && !['settings', 'draft', 'onboarding'].includes(parts[0])
    ? { environmentId: parts[0], threadId: parts[1] } : null;
}

const NAMES = { claudeAgent: 'Claude', codex: 'Codex', cursor: 'Cursor', opencode: 'OpenCode', antigravity: 'Antigravity' };
const MAX_PROVIDERS = 4;

export function level(remaining) { return remaining <= 5 ? 'critical' : remaining <= 20 ? 'low' : 'ok'; }

export function formatResetsIn(ms) {
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return '<1m';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}

// One row per provider: its tightest window. A window past its reset time counts as full again.
export function summarize(providers, now = Date.now(), keepId = null) {
  const rows = [];
  for (const provider of providers ?? []) {
    if (!provider.enabled || !provider.installed) continue;
    const windows = (provider.usageLimits?.windows ?? []).map((window) => {
      const resetsAt = window.resetsAt ? Date.parse(window.resetsAt) : NaN;
      const expired = Number.isFinite(resetsAt) && resetsAt <= now;
      const used = expired ? 0 : Math.max(0, Math.min(100, window.usedPercent));
      const remaining = Math.round(100 - used);
      return { label: window.label, remaining, level: level(remaining),
        resetsInMs: Number.isFinite(resetsAt) && !expired ? resetsAt - now : null };
    });
    if (!windows.length) continue;
    const tightest = windows.reduce((a, b) => (b.remaining < a.remaining ? b : a));
    rows.push({ id: provider.instanceId, name: provider.displayName ?? NAMES[provider.driver] ?? provider.driver ?? provider.instanceId,
      ...tightest, windows, checkedAt: provider.usageLimits.checkedAt ?? null });
  }
  if (rows.length <= MAX_PROVIDERS) return rows;
  const keep = new Set([...rows].sort((a, b) => a.remaining - b.remaining).slice(0, MAX_PROVIDERS));
  // The provider the viewer is looking at is never dropped from the list.
  const wanted = rows.find((row) => row.id === keepId);
  if (wanted && !keep.has(wanted)) { keep.delete([...keep].pop()); keep.add(wanted); }
  return rows.filter((row) => keep.has(row));
}

// The provider shown by default is the one the chat's model belongs to; a viewer's pick wins; otherwise the tightest.
export function pickRow(rows, pinnedId, threadInstanceId) {
  return rows.find((row) => row.id === pinnedId) ?? rows.find((row) => row.id === threadInstanceId)
    ?? (rows.length ? rows.reduce((a, b) => (b.remaining < a.remaining ? b : a)) : null);
}

export function threadInstance(projection) {
  const thread = projection?.thread;
  return thread?.modelSelection?.instanceId ?? thread?.providerInstanceId ?? null;
}
