import { host } from './host-v017.mjs';
import { createState } from './state.mjs';
import { createController } from './controller.mjs';
import { modelOptions, routeRef, draftRef } from './menu.mjs';

const ID = 't3-adds-orchestrator';
if (!document.getElementById(ID)) {
  const state = createState((() => { try { return window.localStorage; } catch { return { getItem() { throw new Error('storage'); }, setItem() {}, removeItem() {} }; } })());
  const controller = createController({ host, state });
  const mount = document.createElement('span');
  mount.id = ID;
  mount.style.cssText = 'display:inline-flex;flex-shrink:0;align-items:center;position:relative';
  const root = mount.attachShadow({ mode: 'open' });
  const style = document.createElement('style');
  style.textContent = `
    :host{font:13px/1.5 system-ui,sans-serif;color:var(--foreground,#eee)}*{box-sizing:border-box}
    button{font:inherit;color:inherit;cursor:pointer;border:1px solid transparent;border-radius:9px;background:transparent;padding:6px 8px;white-space:nowrap;font-size:12px;display:inline-flex;gap:6px;align-items:center;transition:background .15s,border-color .15s}
    button:hover:not(:disabled){background:color-mix(in srgb,var(--foreground,#fff) 7%,transparent)}button:disabled{opacity:.45;cursor:default}
    button:focus-visible{outline:2px solid #9b8cff;outline-offset:2px}
    #launch[data-status=on]{color:#fff;background:#1f9d57;border-color:#2bbd6b}#launch[data-status=on]:hover{background:#25b066}
    #launch[data-status=starting]{border-color:#1f9d5780;color:#4ade80}
    .menu{position:fixed;z-index:2147483000;min-width:240px;max-width:min(360px,calc(100vw - 16px));max-height:70vh;overflow:auto;padding:6px;border:1px solid #8884;border-radius:12px;background:var(--background,#18181b);box-shadow:0 12px 40px #0006}
    .menu[hidden]{display:none}.menu h3{margin:6px 8px;font-size:11px;font-weight:600;letter-spacing:.4px;color:color-mix(in srgb,var(--foreground,#eee) 60%,transparent)}
    .menu button{display:flex;width:100%;justify-content:flex-start;text-align:left;white-space:normal;padding:7px 10px;font-size:13px;border-radius:8px}
    .menu button[aria-checked=true]::before{content:'✓';color:#4ade80}.menu button[aria-checked=false]::before{content:'';display:inline-block;width:.8em}
    .menu hr{border:0;border-top:1px solid #8883;margin:6px 0}
    .note{position:absolute;bottom:calc(100% + 6px);left:0;max-width:280px;padding:6px 10px;border-radius:8px;background:#7f1d1d;color:#fff;font-size:12px;white-space:normal}.note[hidden]{display:none}
    @media(max-width:600px){#launch .text{display:none}}`;
  const launch = document.createElement('button');
  launch.id = 'launch'; launch.type = 'button'; launch.setAttribute('aria-haspopup', 'menu');
  const label = document.createElement('span'); label.className = 'text';
  launch.append(Object.assign(document.createElement('span'), { textContent: '◇', ariaHidden: 'true' }), label);
  const note = Object.assign(document.createElement('div'), { className: 'note', hidden: true, role: 'alert' });
  const menu = Object.assign(document.createElement('div'), { className: 'menu', hidden: true, role: 'menu' });
  root.append(style, launch, note, menu);

  let current = null;
  const showError = (error) => { note.textContent = error.message; note.hidden = false; setTimeout(() => { note.hidden = true; }, 6000); };
  // Re-attach afterwards: promoting a draft changes the route before the chat data may be present.
  const run = (work) => work().catch(showError).finally(() => { render(); schedule(); });

  function render() {
    const ref = current;
    mount.style.display = ref ? 'inline-flex' : 'none';
    if (!ref) return;
    const status = controller.status(ref);
    launch.dataset.status = status;
    launch.setAttribute('aria-pressed', String(status !== 'off'));
    label.textContent = status === 'starting' ? 'Starting…' : 'Orchestrator';
    launch.title = status === 'off' ? 'Orchestrator is off. Click to let this chat’s agent coordinate subagents only. Right-click for options.'
      : 'Orchestrator is on. Click to end coordinator mode. Right-click for options.';
  }

  function closeMenu() { menu.hidden = true; }
  function openMenu(x, y) {
    const ref = current; if (!ref) return;
    const options = modelOptions(host.providers(ref));
    const active = controller.resolveDefault(ref);
    menu.replaceChildren();
    const heading = (text) => menu.append(Object.assign(document.createElement('h3'), { textContent: text }));
    const item = (text, checked, onClick, disabled = false) => {
      const b = Object.assign(document.createElement('button'), { type: 'button', textContent: text, disabled });
      b.setAttribute('role', checked === null ? 'menuitem' : 'menuitemradio');
      if (checked !== null) b.setAttribute('aria-checked', String(checked));
      b.onclick = () => { closeMenu(); run(onClick); };
      menu.append(b);
    };
    heading('Default subagent model');
    item('No default (mid-tier model)', !active, () => controller.setDefaultModel(ref, null));
    for (const option of options) item(option.label, active?.instanceId === option.instanceId && active.slug === option.slug, () => controller.setDefaultModel(ref, option));
    menu.append(document.createElement('hr'));
    heading('Subagent effort');
    for (const [value, label] of [['task', 'By task (recommended)'], ['low', 'Low'], ['medium', 'Medium']]) item(label, controller.effort() === value, () => controller.setEffort(ref, value));
    menu.append(document.createElement('hr'));
    item('Remind now', null, () => controller.remind(ref), controller.status(ref) === 'off');
    menu.hidden = false;
    menu.style.left = `${Math.max(8, Math.min(x, innerWidth - menu.offsetWidth - 8))}px`;
    menu.style.top = `${Math.max(8, Math.min(y, innerHeight - menu.offsetHeight - 8))}px`;
    menu.querySelector('button:not(:disabled)')?.focus();
  }
  let clicking = false;
  launch.addEventListener('click', () => {
    if (clicking || !current) return;
    clicking = true;
    run(() => controller.toggle(current)).finally(() => { clicking = false; });
  });
  launch.addEventListener('contextmenu', (event) => { event.preventDefault(); const r = launch.getBoundingClientRect(); openMenu(r.left, r.top - 8 - (menu.offsetHeight || 0)); });
  launch.addEventListener('keydown', (event) => { if (event.key === 'ContextMenu' || (event.shiftKey && event.key === 'F10')) { event.preventDefault(); const r = launch.getBoundingClientRect(); openMenu(r.left, r.top - 8); } });
  menu.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') { closeMenu(); launch.focus(); return; }
    const items = [...menu.querySelectorAll('button:not(:disabled)')], at = items.indexOf(root.activeElement);
    if (event.key === 'ArrowDown') { event.preventDefault(); items[(at + 1) % items.length]?.focus(); }
    if (event.key === 'ArrowUp') { event.preventDefault(); items[(at - 1 + items.length) % items.length]?.focus(); }
  });
  document.addEventListener('pointerdown', (event) => { if (!event.composedPath().includes(mount)) closeMenu(); });
  window.addEventListener('blur', closeMenu);

  const locate = () => {
    const chat = routeRef(window.location);
    if (chat) return chat;
    const draft = draftRef(window.location);
    const session = draft && host.draft.session(draft.draftId);
    return session ? { environmentId: session.environmentId, threadId: session.threadId, projectId: session.projectId, draftId: draft.draftId } : null;
  };
  const keyOf = (ref) => ref && `${ref.environmentId}/${ref.threadId}/${ref.draftId ?? ''}`;
  let unobserve = null, observedKey = null;
  function attach() {
    const ref = locate();
    const key = keyOf(ref);
    current = ref && (ref.draftId || host.parent(ref)) ? ref : null;
    if (key !== observedKey) {
      unobserve?.(); unobserve = null; observedKey = key; closeMenu();
      // Redraw only when this chat's data changes.
      // A draft has no chat data to observe yet.
      if (current && !current.draftId) unobserve = host.observe(current, render);
    }
    const footer = [...document.querySelectorAll('[data-chat-composer-form="true"] [data-chat-composer-footer="true"]')].find((n) => n.getClientRects().length > 0);
    if (current && footer) {
      const council = footer.querySelector('#t3-adds-council-composer');
      const before = council ? council.nextSibling : footer.querySelector('[data-chat-composer-actions="right"]');
      if (mount.parentElement !== footer || (council && mount.previousSibling !== council)) footer.insertBefore(mount, before);
    } else mount.remove();
    render();
  }
  let queued = false;
  const settled = () => {
    const ref = locate();
    return mount.isConnected && ref && observedKey === keyOf(ref) && mount.parentElement.getClientRects().length > 0;
  };
  const schedule = () => { if (queued) return; queued = true; requestAnimationFrame(() => { queued = false; attach(); }); };
  window.addEventListener('popstate', schedule);
  window.addEventListener('hashchange', schedule);
  window.navigation?.addEventListener('navigatesuccess', schedule);
  new MutationObserver((records) => (settled() ? null : schedule())).observe(document.getElementById('root') ?? document.body, { childList: true, subtree: true });
  schedule();
}
