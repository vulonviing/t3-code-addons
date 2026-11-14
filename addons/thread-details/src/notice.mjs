// A small dismissible note for when the addon could not attach. Shown once per load; no timers, no polling.
export function notify(title, message) {
  const id = 't3-adds-thread-details-notice';
  if (document.getElementById(id)) return;
  const mount = document.createElement('div');
  mount.id = id;
  mount.style.cssText = 'position:fixed;z-index:2147482900;right:16px;bottom:16px;line-height:0';
  const root = mount.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>
    :host{font:12px/1.4 system-ui,sans-serif;color:var(--foreground,#ddd)}*{box-sizing:border-box}
    .note{position:relative;max-width:min(320px,80vw);padding:8px 28px 8px 10px;border:1px solid #8885;border-radius:9px;background:var(--background,#18181b);box-shadow:0 4px 18px #0003;line-height:1.4}
    p{margin:0;overflow-wrap:anywhere}
    button{position:absolute;top:4px;right:4px;width:20px;height:20px;padding:0;border:0;border-radius:6px;background:transparent;font:16px/1 system-ui;color:inherit;opacity:.7;cursor:pointer}
    button:hover{opacity:1;background:color-mix(in srgb,var(--foreground,#fff) 12%,transparent)}
    button:focus-visible{outline:2px solid #8b7cf8}
  </style><div class="note" role="status"><p></p><button type="button" aria-label="Dismiss message" title="Dismiss">×</button></div>`;
  root.querySelector('p').textContent = `${title} could not attach to this version of T3: ${message}`;
  root.querySelector('button').onclick = () => mount.remove();
  document.body.append(mount);
}
