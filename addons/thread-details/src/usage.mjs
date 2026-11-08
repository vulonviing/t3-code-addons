export function routeRef(location) {
  const path = location.hash?.startsWith('#/') ? location.hash.slice(1) : location.pathname;
  const parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent);
  return parts.length === 2 && !['settings', 'draft', 'onboarding'].includes(parts[0])
    ? { environmentId: parts[0], threadId: parts[1] } : null;
}

const CLI = { claudeAgent: 'claude', codex: 'codex', cursor: 'cursor', opencode: 'opencode', antigravity: 'antigravity' };

export function cliLabel(driver) { return CLI[driver] ?? driver ?? 'unknown'; }

export function shortModel(name) {
  const text = String(name ?? 'unknown').replace(/^claude-/, '');
  return text.length > 16 ? text.slice(0, 15) + '…' : text;
}

// Input includes cache reads and writes, so the headline is processed tokens, not billed tokens.
export function summarize(projection, now = Date.now()) {
  const threads = new Map((projection?.providerThreads ?? []).map((thread) => [thread.id, thread]));
  const models = new Map(), clis = new Map();
  let input = 0, output = 0, cached = 0, counted = 0, missing = 0;
  for (const turn of projection?.providerTurns ?? []) {
    const usage = turn.turnTokenUsage;
    if (!usage || usage.usageStatus === 'unavailable') {
      if (turn.status !== 'running' && turn.status !== 'queued') missing += 1;
      continue;
    }
    const used = (usage.inputTokens ?? 0) + (usage.outputTokens ?? 0);
    input += usage.inputTokens ?? 0;
    output += usage.outputTokens ?? 0;
    cached += usage.cachedInputTokens ?? 0;
    counted += 1;
    const model = usage.models?.length ? usage.models.join(' + ') : 'unknown';
    const entry = models.get(model) ?? { tokens: 0, input: 0, cached: 0, output: 0, turns: 0 };
    entry.tokens += used;
    entry.input += usage.inputTokens ?? 0;
    entry.cached += usage.cachedInputTokens ?? 0;
    entry.output += usage.outputTokens ?? 0;
    entry.turns += 1;
    models.set(model, entry);
    const cli = cliLabel(threads.get(turn.providerThreadId)?.driver);
    clis.set(cli, { tokens: (clis.get(cli)?.tokens ?? 0) + used });
  }
  const total = input + output;
  const rank = (map) => [...map].sort((a, b) => b[1].tokens - a[1].tokens)
    .map(([key, entry]) => ({ key, ...entry, share: total ? entry.tokens / total : 0 }));
  const created = Date.parse(projection?.thread?.createdAt ?? '');
  return {
    total, input, output, cached, turns: counted, missing,
    cacheShare: input ? cached / input : 0,
    byModel: rank(models), byCli: rank(clis),
    ageMs: Number.isFinite(created) ? Math.max(0, now - created) : null,
  };
}

export function formatTokens(count) {
  if (count < 1000) return String(count);
  if (count < 1e6) return (count / 1e3).toFixed(count < 1e4 ? 1 : 0).replace(/\.0$/, '') + 'K';
  return (count / 1e6).toFixed(count < 1e7 ? 2 : 1).replace(/\.?0+$/, '') + 'M';
}

export function formatAge(ms) {
  const minutes = Math.floor(ms / 60000);
  if (minutes < 1) return '<1m';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ${minutes % 60}m`;
  return `${Math.floor(hours / 24)}d ${hours % 24}h`;
}
