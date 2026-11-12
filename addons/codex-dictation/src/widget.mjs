import { host } from './host-v017.mjs';
import { createConnection } from './connection.mjs';
import { createController } from './controller.mjs';

export function mountMicrophone({ adapter = host, connect = createConnection } = {}) {
  const ID = 't3-adds-codex-dictation';
  if (document.getElementById(ID)) return;
  const mount = document.createElement('div');
  mount.id = ID; mount.hidden = true;
  mount.style.cssText = 'position:fixed;z-index:2147482900;line-height:0';
  const root = mount.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>
    :host{font:12px/1.4 system-ui,sans-serif;color:var(--foreground,#ddd)}*{box-sizing:border-box}
    button{display:flex;align-items:center;justify-content:center;gap:7px;width:44px;height:32px;padding:0 10px;border:1px solid color-mix(in srgb,var(--foreground,#fff) 12%,transparent);border-radius:11px;background:color-mix(in srgb,var(--foreground,#fff) 3%,var(--background,#18181b));color:inherit;cursor:pointer;transition:background .15s,border-color .15s}
    button:hover{background:color-mix(in srgb,var(--foreground,#fff) 9%,var(--background,#18181b))}button:focus-visible{outline:2px solid #8b7cf8;outline-offset:2px}
    button[data-phase=connecting]{width:124px;color:#e9b45f;background:color-mix(in srgb,#e9b45f 9%,var(--background,#18181b));border-color:#e9b45f44}
    button[data-phase=recording]{width:112px;color:var(--foreground,#eee);background:color-mix(in srgb,#3cb99b 9%,var(--background,#18181b));border-color:#3cb99b66}
    button[data-phase=finishing]{width:112px;opacity:.7;cursor:wait}svg{width:18px;height:18px;flex-shrink:0;fill:none;stroke:currentColor;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
    button[data-compact]{width:32px;padding:0 5px}button[data-compact] .label{display:none!important}
    .label{display:none;font:500 11px/1 system-ui;white-space:nowrap}button:is([data-phase=connecting],[data-phase=recording],[data-phase=finishing]) .label{display:block}
    .spinner{display:none;width:15px;height:15px;flex-shrink:0;border:1.8px solid currentColor;border-right-color:transparent;border-radius:50%;animation:spin .8s linear infinite}
    button[data-phase=connecting] .spinner,button[data-phase=finishing] .spinner{display:block}button[data-phase=connecting] svg,button[data-phase=finishing] svg,button[data-phase=recording] svg{display:none}
    .wave{display:none;width:27px;height:20px;align-items:center;justify-content:center;gap:2px;color:#52c8a6;flex-shrink:0}
    button[data-phase=recording] .wave{display:flex}.wave i{display:block;width:3px;border-radius:2px;background:currentColor;height:calc(4px + var(--level,0) * var(--peak,1) * 15px);transition:height .07s linear}.wave i:nth-child(1),.wave i:nth-child(5){--peak:.45}.wave i:nth-child(2),.wave i:nth-child(4){--peak:.75}
    @keyframes spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){button{transition:none}.spinner{animation:none;border-style:dotted}.wave i{transition:none}}
    .note{position:absolute;bottom:calc(100% + 8px);left:0;min-width:200px;max-width:min(300px,80vw);padding:8px 10px;border:1px solid #8885;border-radius:9px;background:var(--background,#18181b);color:var(--foreground,#ddd);box-shadow:0 4px 18px #0003;line-height:1.4}
    [hidden]{display:none!important}.sr{position:absolute;width:1px;height:1px;overflow:hidden;clip-path:inset(50%)}
  </style><button type="button" data-phase="idle" aria-label="Start dictation" aria-pressed="false" title="Dictate into the prompt. Audio is sent to OpenAI through Codex."><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M6 10v2a6 6 0 0012 0v-2M12 18v3M9 21h6"/></svg><span class="spinner" aria-hidden="true"></span><span class="wave" aria-hidden="true"><i></i><i></i><i></i><i></i><i></i></span><span class="label" aria-hidden="true"></span></button><span class="sr" role="status" aria-live="polite"></span><div class="note" role="alert" hidden></div>`;
  const button = root.querySelector('button'), status = root.querySelector('[role=status]'), note = root.querySelector('.note');
  let lastLevel = 0, levelText = '0';
  const controller = createController({ host: adapter, connect, level(value) {
    lastLevel = Math.max(value, lastLevel * .65);
    const next = (Math.round(lastLevel * 40) / 40).toFixed(3);
    if (next !== levelText) { levelText = next; button.style.setProperty('--level', next); }
  }, changed({ phase, error }) {
    button.dataset.phase = phase;
    button.disabled = phase === 'finishing';
    button.setAttribute('aria-pressed', String(phase !== 'idle'));
    button.setAttribute('aria-label', phase === 'idle' ? 'Start dictation' : phase === 'finishing' ? 'Finishing dictation' : 'Stop dictation');
    button.title = error || (phase === 'idle' ? 'Dictate into the prompt. Audio is sent to OpenAI through Codex.' : phase === 'connecting' ? 'Connecting. Speech is buffered as soon as microphone access is available.' : phase === 'finishing' ? 'Microphone stopped. Finishing the buffered words…' : 'Listening. Click to stop; your words stay in the prompt.');
    root.querySelector('.label').textContent = phase === 'connecting' ? 'Connecting' : phase === 'recording' ? 'Listening' : phase === 'finishing' ? 'Finishing' : '';
    if (phase !== 'recording') { lastLevel = 0; levelText = '0'; button.style.setProperty('--level', '0'); }
    status.textContent = phase === 'connecting' ? 'Connecting dictation.' : phase === 'recording' ? 'Dictation is listening.' : phase === 'finishing' ? 'Finishing the last words.' : 'Dictation stopped.';
    note.textContent = error; note.hidden = !error;
    schedule();
  } });
  button.onclick = () => {
    if (controller.state().phase === 'idle') { note.hidden = true; void controller.start(); }
    else { void controller.stop(); adapter.focus(); }
  };

  let footer = null, anchor = null, form = null, right = null, queued = false;
  function place() {
    if (!footer?.isConnected || document.hidden) return;
    const f = footer.getBoundingClientRect();
    const a = anchor?.getBoundingClientRect();
    const r = right?.getBoundingClientRect();
    // The right wrapper is flex:1 and includes empty space. Measure its actual controls.
    const controls = right ? [...right.querySelectorAll('button, [role="button"], [aria-haspopup], input, select')]
      .map(e => e.getBoundingClientRect()).filter(r => r.width > 0 && r.height > 0 && r.right > f.left && r.left < f.right && r.bottom > f.top && r.top < f.bottom)
      .sort((a, b) => a.left - b.left) : [];
    const leftEdge = a?.right ?? [...footer.children].filter(e => e !== right)
      .reduce((edge, e) => Math.max(edge, e.getBoundingClientRect().right), f.left);
    let left = leftEdge + 6;
    const end = Math.min(controls[0]?.left ?? r?.right ?? f.right, innerWidth - 8) - 6;
    const desired = button.dataset.phase === 'connecting' ? 124 : button.dataset.phase === 'idle' ? 44 : 112;
    const compact = end - left < desired;
    button.toggleAttribute('data-compact', compact);
    const width = compact ? 32 : desired;
    // Align to a real toolbar control, not the footer's possibly taller wrapper.
    const row = a ?? controls[0] ?? f;
    let top = row.top + (row.height - 32) / 2;
    if (left + width > end) {
      // A fully occupied toolbar has no safe inline slot. Never float over the draft.
      left = f.right - width;
      const bounds = form.getBoundingClientRect();
      top = bounds.bottom + 6;
      if (top + 32 > innerHeight - 8) top = bounds.top - 38;
    }
    const visible = f.width > 0 && top >= 0 && top + 32 <= innerHeight;
    mount.hidden = !visible;
    const x = `${Math.max(8, Math.min(left, innerWidth - width - 8))}px`, y = `${top}px`;
    if (mount.style.left !== x) mount.style.left = x;
    if (mount.style.top !== y) mount.style.top = y;
  }
  const resize = new ResizeObserver(schedule);
  function attach() {
    if (document.hidden) return;
    const target = adapter.target();
    if (controller.target() && JSON.stringify(target) !== JSON.stringify(controller.target())) void controller.stop({ drain: false });
    const next = target && [...document.querySelectorAll('[data-chat-composer-form="true"] [data-chat-composer-footer="true"]')].find(e => e.getClientRects().length);
    const nextAnchor = ['#t3-adds-orchestrator', '#t3-adds-council-composer'].map(s => next?.querySelector(s)).find(e => e?.getClientRects().length) ?? null;
    const nextForm = next?.closest('[data-chat-composer-form="true"]') ?? null;
    const nextRight = next?.querySelector('[data-chat-composer-actions="right"]') ?? null;
    if (next !== footer || nextAnchor !== anchor || nextForm !== form || nextRight !== right) {
      resize.disconnect(); footer = next; anchor = nextAnchor; form = nextForm; right = nextRight;
      // The composer can grow while its footer keeps exactly the same dimensions.
      for (const element of [footer, anchor, form, right]) if (element) resize.observe(element);
    }
    mount.hidden = !footer;
    if (!footer && controller.target()) void controller.stop({ drain: false });
    if (footer) place();
  }
  function schedule() { if (!queued && !document.hidden) { queued = true; requestAnimationFrame(() => { queued = false; attach(); }); } }
  // Observe only the host root for discovery/layout changes; no idle timers or React DOM mutations.
  new MutationObserver(records => {
    if (document.hidden) return;
    if ((!footer?.isConnected && adapter.target()) || (footer && records.some(r => footer.contains(r.target)))) schedule();
  }).observe(document.getElementById('root') ?? document.body, { childList: true, subtree: true });
  window.navigation?.addEventListener('navigatesuccess', schedule);
  window.addEventListener('popstate', schedule);
  window.addEventListener('hashchange', schedule);
  window.addEventListener('resize', schedule);
  window.addEventListener('scroll', schedule, { passive: true, capture: true });
  window.visualViewport?.addEventListener('resize', schedule);
  window.visualViewport?.addEventListener('scroll', schedule);
  window.addEventListener('blur', () => void controller.stop({ drain: false }));
  document.addEventListener('visibilitychange', () => { if (document.hidden) void controller.stop({ drain: false }); else schedule(); });
  window.addEventListener('pagehide', () => void controller.stop({ drain: false }));
  document.body.append(mount); schedule();
}
