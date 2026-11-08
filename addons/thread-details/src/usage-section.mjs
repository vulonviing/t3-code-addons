import { make } from './dom.mjs';
import { routeRef, summarize, formatTokens, formatAge } from './usage.mjs';

export function usageSection(host, update) {
  let projection = null, key = null, stop = () => {};
  const tick = () => {
    const ref = routeRef(window.location);
    const next = ref ? `${ref.environmentId}/${ref.threadId}` : null;
    if (next === key) return;
    key = next;
    stop();
    projection = null;
    stop = ref ? host.observeThread(ref, (value) => { projection = value; update(); }) : () => {};
  };
  return {
    id: 'chat-usage',
    title: 'This chat',
    tick,
    summary() {
      const usage = key ? summarize(projection) : null;
      if (!usage || !usage.total) return '';
      return usage.ageMs === null ? formatTokens(usage.total) : `${formatTokens(usage.total)} \u00b7 ${formatAge(usage.ageMs)}`;
    },
    render(body) {
      if (!key) return body.append(make('div', 'empty', 'No chat open'));
      const usage = summarize(projection);
      if (!usage.total) return body.append(make('div', 'empty', 'No usage yet'));
      // One row per model, stacked: name, tokens, and a bar for its share. Hovering a row shows where its tokens went.
      // The total and age are already in the section header; models with no tokens add nothing.
      for (const model of usage.byModel.filter((item) => item.tokens > 0)) {
        const row = make('div', 'model');
        const line = make('div', 'top');
        line.append(make('span', 'name', model.key.replace(/^claude-/, '')), make('span', 'tok', formatTokens(model.tokens)));
        const bar = make('div', 'thin');
        const fill = make('b');
        fill.style.width = `${(model.share * 100).toFixed(1)}%`;
        bar.append(fill);
        row.append(line, bar);
        row.title = `${model.key}\n${model.input.toLocaleString()} in (${Math.round(model.input ? (model.cached / model.input) * 100 : 0)}% cached)\n`
          + `${model.output.toLocaleString()} out\n${model.turns} turns \u00b7 ${Math.round(model.share * 100)}% of this chat`;
        body.append(row);
      }
      body.title = `${usage.input.toLocaleString()} in (${Math.round(usage.cacheShare * 100)}% cached) · `
        + `${usage.output.toLocaleString()} out · ${usage.turns} turns${usage.missing ? ` · ${usage.missing} without usage data` : ''}`;
    },
  };
}
