import { make } from './dom.mjs';
import { geometry, parseOpen } from './layout.mjs';

const STORAGE = 't3-adds:thread-details:open';
const CARD = '[data-thread-details-card]';
const REFRESH_MS = 1000;
const CLOCK_MS = 30000;

// A second card attached under T3's thread-details card. T3's card and its own sizing logic are never touched: we only
// read its position. Cost model: nothing runs while T3's card is closed; while it is open data repaints at most once per
// second, and the only timer is a 30 s clock refresh.
export function createRail(id) {
  const open = parseOpen((() => { try { return localStorage.getItem(STORAGE); } catch { return null; } })());
  const save = () => { try { localStorage.setItem(STORAGE, JSON.stringify(open)); } catch { /* per-viewer convenience only */ } };
  const sections = [];
  let host = null, shown = false, dirty = true, paintTimer = 0, checkTimer = 0, clock = 0, watched = null;

  const style = document.createElement('style');
  style.textContent = `
    #${id}{position:fixed;z-index:50;box-sizing:border-box;overflow:auto;scrollbar-width:thin;border-radius:1rem;-webkit-app-region:no-drag;
      color:var(--foreground);font:inherit}
    #${id}[hidden]{display:none}
    #${id} button{font:inherit;color:inherit;background:none;border:0;cursor:pointer;text-align:left}
    #${id} .sec+.sec{border-top:1px solid color-mix(in srgb,var(--foreground) 8%,transparent)}
    #${id} .head{display:flex;align-items:center;gap:.5rem;width:100%;padding:.55rem .75rem;border-radius:.5rem;min-height:2.25rem}
    #${id} .head:hover{background:color-mix(in srgb,var(--foreground) 6%,transparent)}
    #${id} .label{flex:1;font-size:.875rem;font-weight:500;color:color-mix(in srgb,var(--foreground) 85%,transparent)}
    #${id} .sum{font-size:.75rem;color:color-mix(in srgb,var(--foreground) 55%,transparent);font-variant-numeric:tabular-nums;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:55%}
    #${id} .chev{flex:none;width:1rem;height:1rem;opacity:.6;transition:transform .18s ease}
    #${id} .sec.open .chev{transform:rotate(180deg)}
    #${id} .fold{display:grid;grid-template-rows:0fr;transition:grid-template-rows .2s ease}
    #${id} .sec.open .fold{grid-template-rows:1fr}
    #${id} .fold>div{overflow:hidden;min-height:0}
    #${id} .body{padding:.1rem .75rem .7rem;font-size:.75rem;line-height:1.4;color:color-mix(in srgb,var(--foreground) 60%,transparent);font-variant-numeric:tabular-nums}
    #${id} .top{display:flex;justify-content:space-between;align-items:baseline}
    #${id} .bar2,#${id} .thin{display:flex;gap:1px;height:3px;margin:.5rem 0 .4rem;border-radius:2px;overflow:hidden;background:color-mix(in srgb,var(--foreground) 12%,transparent)}
    #${id} .bar2 b,#${id} .thin b{display:block;height:100%;background:var(--foreground)}
    #${id} .line{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #${id} .row+.row{margin-top:.65rem}
    #${id} .name{color:color-mix(in srgb,var(--foreground) 85%,transparent);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
    #${id} .name small{font:inherit;opacity:.6}
    #${id} .thin{display:block;height:2px;margin:.3rem 0 .1rem}
    #${id} .thin b{border-radius:2px;opacity:.55}
    #${id} .low b{background:var(--warning,#d97706);opacity:.9}
    #${id} .critical b{background:var(--destructive,#dc2626);opacity:.95}
    #${id} .reset{opacity:.75}
    #${id} .empty{opacity:.75}
    #${id} .model{margin-top:.6rem;cursor:default}
    #${id} .model .thin{display:block;margin:.3rem 0 0}
    #${id} .tok{color:var(--foreground);font-variant-numeric:tabular-nums}
    #${id} .prov{display:block;width:100%;padding:.4rem .55rem;border-radius:.5rem}
    #${id} .prov+.prov{margin-top:.15rem}
    #${id} .prov:hover{background:color-mix(in srgb,var(--foreground) 6%,transparent)}
    #${id} .prov .thin{display:block;margin:.35rem 0 0}
    #${id} .prov .reset{display:block;margin-top:.3rem}
    #${id} .prov .top{display:flex;justify-content:space-between;gap:.5rem}
  `;

  const chevron = () => {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '2');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    svg.setAttribute('class', 'chev');
    const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'm6 9 6 6 6-6');
    svg.append(path);
    return svg;
  };

  const paint = () => {
    paintTimer = 0;
    if (!shown || !dirty || !host) return;
    dirty = false;
    host.replaceChildren(...sections.map((section) => {
      const isOpen = open[section.id] === true;
      const wrap = make('div', `sec${isOpen ? ' open' : ''}`);
      const head = make('button', 'head');
      head.type = 'button';
      head.setAttribute('aria-expanded', String(isOpen));
      head.append(make('span', 'label', section.title), make('span', 'sum', section.summary()), chevron());
      head.onclick = () => { if (open[section.id]) delete open[section.id]; else open[section.id] = true; save(); dirty = true; paint(); place(); };
      const fold = make('div', 'fold');
      const clip = make('div');
      const body = make('div', 'body');
      if (isOpen) section.render(body);
      clip.append(body);
      fold.append(clip);
      wrap.append(head, fold);
      return wrap;
    }));
    place();
  };

  // Data changes call this; repaints are throttled and skipped entirely while T3's card is closed.
  const invalidate = () => {
    dirty = true;
    if (shown && !paintTimer && !document.hidden) paintTimer = setTimeout(paint, REFRESH_MS);
  };

  const resizeWatcher = new ResizeObserver(() => place());
  function place() {
    const card = document.querySelector(CARD);
    if (!card || !card.getClientRects().length) return;
    const placed = geometry(card.getBoundingClientRect(), window.innerHeight);
    host.style.left = `${placed.left}px`;
    host.style.top = `${placed.top}px`;
    host.style.width = `${placed.width}px`;
    host.style.maxHeight = `${placed.maxHeight}px`;
  }

  const check = () => {
    checkTimer = 0;
    const card = document.querySelector(CARD);
    const visible = Boolean(card && card.getClientRects().length) && !document.hidden;
    if (card !== watched) {
      if (watched) resizeWatcher.unobserve(watched);
      watched = card;
      if (card) resizeWatcher.observe(card);
    }
    if (visible === shown) { if (visible) place(); return; }
    shown = visible;
    host.hidden = !visible;
    clearInterval(clock);
    clock = 0;
    if (visible) { dirty = true; paint(); clock = setInterval(invalidate, CLOCK_MS); }
  };
  // Opening and closing T3's card happens through clicks, shortcuts, Esc, and route changes; re-check after each, once
  // right away and once after its animation. There is no polling.
  const schedule = () => {
    if (checkTimer) return;
    checkTimer = setTimeout(() => { check(); setTimeout(check, 350); }, 60);
  };

  host = make('div', 'dropdown-glass');
  host.id = id;
  host.hidden = true;
  document.head.append(style);
  document.body.append(host);
  for (const type of ['click', 'keydown', 'pointerup']) document.addEventListener(type, schedule, true);
  window.addEventListener('resize', schedule);
  document.addEventListener('visibilitychange', schedule);
  const follow = () => { for (const section of sections) section.tick?.(); schedule(); };
  // Route changes are events, not polling; the interval is only a fallback for runtimes without the Navigation API.
  if (window.navigation) window.navigation.addEventListener('currententrychange', follow);
  else {
    window.addEventListener('hashchange', follow);
    window.addEventListener('popstate', follow);
    setInterval(() => { if (!document.hidden) follow(); }, 2000);
  }

  return {
    add(section) { sections.push(section); section.tick?.(); dirty = true; schedule(); },
    update: invalidate,
    // For clicks inside a section: repaint now instead of waiting for the throttle.
    repaint() { dirty = true; paint(); },
  };
}
