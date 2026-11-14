// Entry point. Loads the generated host adapter first; when this T3 release cannot be attached to, show one small
// dismissible note (once per load, no timers or observers) instead of loading the addon.
const NOTE_ID = 't3-adds-model-council-note';

function showUnsupported(reason) {
  if (document.getElementById(NOTE_ID)) return;
  const mount = document.createElement('div');
  mount.id = NOTE_ID;
  const root = mount.attachShadow({ mode: 'open' });
  root.innerHTML = `<style>
    .note{position:fixed;right:12px;bottom:12px;z-index:2147483000;max-width:min(320px,calc(100vw - 24px));padding:8px 30px 8px 10px;border:1px solid #8885;border-radius:9px;background:var(--background,#18181b);color:var(--foreground,#ddd);font:12px/1.4 system-ui,sans-serif;box-shadow:0 4px 18px #0003;overflow-wrap:anywhere}
    p{margin:0}button{position:absolute;top:4px;right:4px;width:20px;height:20px;padding:0;border:0;border-radius:6px;background:transparent;color:inherit;font:16px/1 system-ui;opacity:.7;cursor:pointer}button:hover{opacity:1}button:focus-visible{outline:2px solid #9b8cff}
  </style><div class="note" role="status"><p></p><button type="button" aria-label="Dismiss message" title="Dismiss">×</button></div>`;
  root.querySelector('p').textContent = `Model Council could not attach. ${reason}`;
  root.querySelector('button').onclick = () => mount.remove();
  document.body.append(mount);
}

let reason = '';
try {
  const { host } = await import('./host.mjs');
  reason = host.unsupported?.() ?? '';
} catch (error) {
  reason = `The T3 integration failed to load (${error.message}).`;
}
if (reason) showUnsupported(reason);
else await import('./app.mjs');
