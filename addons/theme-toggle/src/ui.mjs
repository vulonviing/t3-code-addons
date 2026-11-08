import { host } from './host-v017.mjs';
import { view, choose } from './toggle.mjs';

const ID = 't3-adds-theme-toggle';
if (!document.getElementById(ID)) {
  const mount = document.createElement('div');
  mount.id = ID;
  const root = mount.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  // Offsets clear T3's own header buttons; override the custom properties on :root to adjust.
  style.textContent = `
    :host{position:fixed;top:var(--t3-adds-theme-toggle-top,9px);right:var(--t3-adds-theme-toggle-right,108px);z-index:40;
      font:12px system-ui,sans-serif;color:var(--foreground,#888);-webkit-app-region:no-drag}
    .seg,button{-webkit-app-region:no-drag}
    *{box-sizing:border-box}
    .seg{display:flex;gap:2px;padding:2px;border:1px solid var(--border,#8884);border-radius:99px;
      background:var(--background,transparent)}
    button{display:grid;place-items:center;width:24px;height:20px;padding:0;border:0;border-radius:99px;
      background:transparent;color:inherit;opacity:.45;cursor:pointer;transition:opacity .15s,background .15s}
    button:hover{opacity:.8}
    button[aria-pressed=true]{opacity:1;background:var(--secondary,#8883)}
    button:focus-visible{outline:2px solid var(--ring,#9b8cff);outline-offset:1px}
    svg{width:13px;height:13px;stroke:currentColor;fill:none;stroke-width:1.6;stroke-linecap:round;stroke-linejoin:round}
    @media(max-width:560px){:host{display:none}}
  `;
  const sun = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const moon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  const group = document.createElement('div');
  group.className = 'seg';
  group.setAttribute('role', 'group');
  group.setAttribute('aria-label', 'Theme');
  const buttons = {};
  for (const [mode, icon] of [['light', sun], ['dark', moon]]) {
    const button = document.createElement('button');
    button.type = 'button';
    button.innerHTML = icon;
    button.title = `${mode === 'light' ? 'Light' : 'Dark'} theme`;
    button.setAttribute('aria-label', button.title);
    button.addEventListener('click', () => {
      try { choose(host, mode); } catch (error) { console.error('[t3-adds:theme-toggle]', error); }
    });
    buttons[mode] = button;
    group.append(button);
  }
  // The header is a window-drag region in the desktop app; place the switch against T3's own header
  // buttons so it lines up with them at any window size. The CSS offsets above are the fallback.
  const ANCHORS = ['Toggle thread details panel', 'Toggle terminal drawer', 'Toggle right panel'];
  const place = () => {
    const rects = ANCHORS.map((label) => document.querySelector(`button[aria-label^="${label}"]`))
      .filter(Boolean).map((node) => node.getBoundingClientRect()).filter((rect) => rect.width > 0 && rect.top < 120);
    if (!rects.length) { mount.style.removeProperty('top'); mount.style.removeProperty('right'); return; }
    const left = Math.min(...rects.map((rect) => rect.left));
    const middle = rects.reduce((sum, rect) => sum + rect.top + rect.height / 2, 0) / rects.length;
    mount.style.top = `${Math.round(middle - group.getBoundingClientRect().height / 2)}px`;
    mount.style.right = `${Math.round(document.documentElement.clientWidth - left + 10)}px`;
  };
  const render = () => {
    const { resolved, following } = view(host.snapshot());
    for (const [mode, button] of Object.entries(buttons)) {
      button.setAttribute('aria-pressed', String(mode === resolved));
    }
    group.title = following ? 'Following the system theme' : '';
  };
  host.subscribe(render);
  root.append(style, group);
  document.body.append(mount);
  render();
  place();
  // Re-place only when the layout can have changed (resize, a click that opens or closes a panel, a finished
  // transition) plus a slow safety check, and never while the page is in the background.
  let pending = 0;
  const schedule = () => {
    if (document.hidden || pending) return;
    pending = setTimeout(() => { pending = 0; place(); }, 150);
  };
  window.addEventListener('resize', schedule);
  document.addEventListener('click', schedule, true);
  document.addEventListener('transitionend', schedule, true);
  document.addEventListener('visibilitychange', schedule);
  setInterval(schedule, 3000);
}
