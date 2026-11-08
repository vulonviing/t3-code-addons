import { make } from './dom.mjs';
import { routeRef, summarize, formatResetsIn, pickRow, threadInstance } from './plan.mjs';

export function planSection(host, update, repaint) {
  let providers = null, environmentId = null, threadKey = null, threadProvider = null, pinned = null;
  let stopProviders = () => {}, stopThread = () => {};
  // The last chat's environment keeps the section useful on pages that have no chat of their own. A pick the viewer
  // makes lasts for the current chat only; the next chat starts from its own provider again.
  const tick = () => {
    const ref = routeRef(window.location);
    if (!ref) return;
    if (ref.environmentId !== environmentId) {
      environmentId = ref.environmentId;
      stopProviders();
      providers = null;
      stopProviders = host.observeProviders(environmentId, (value) => { providers = value; update(); });
    }
    const key = `${ref.environmentId}/${ref.threadId}`;
    if (key !== threadKey) {
      threadKey = key;
      pinned = null;
      threadProvider = null;
      stopThread();
      stopThread = host.observeThread(ref, (projection) => { threadProvider = threadInstance(projection); update(); });
    }
  };
  const rows = () => (environmentId === null ? [] : summarize(providers, Date.now(), pinned ?? threadProvider));
  return {
    id: 'plan-left',
    title: 'Plan left',
    tick,
    summary() {
      const row = pickRow(rows(), pinned, threadProvider);
      return row ? `${row.name} ${row.remaining}%` : '';
    },
    render(body) {
      if (environmentId === null) return body.append(make('div', 'empty', 'No chat open'));
      const list = rows();
      if (!list.length) return body.append(make('div', 'empty', providers === null ? 'Loading…' : 'No limits reported'));
      const selected = pickRow(list, pinned, threadProvider);
      // Every provider is listed with its tightest window and when it resets. Clicking one only changes the summary
      // shown in the section header; the list itself looks the same.
      for (const provider of list) {
        const entry = make('button', `prov ${provider.level}`);
        entry.type = 'button';
        entry.title = provider.id === threadProvider ? `${provider.name} (this chat's model)` : provider.name;
        entry.onclick = () => { pinned = provider.id; repaint(); };
        const name = make('span', 'name', provider.name);
        if (provider.label) name.append(make('small', '', ` \u00b7 ${provider.label}`));
        const top = make('span', 'top');
        top.append(name, make('span', '', `${provider.remaining}%`));
        const bar = make('span', 'thin');
        const fill = make('b');
        fill.style.width = `${provider.remaining}%`;
        bar.append(fill);
        entry.append(top, bar, make('span', 'reset', provider.resetsInMs === null ? 'no reset time' : `resets in ${formatResetsIn(provider.resetsInMs)}`));
        body.append(entry);
      }
      if (selected.checkedAt) body.title = `Last checked ${new Date(selected.checkedAt).toLocaleTimeString()}`;
    },
  };
}
