import { notify } from './notice.mjs';
import { mountToggle } from './mount.mjs';

if (!document.getElementById('t3-adds-theme-toggle') && !document.getElementById('t3-adds-theme-toggle-notice')) {
  let loaded;
  try { loaded = await import('./host.mjs'); }
  catch { loaded = { host: null, attachError: 'a T3 module it depends on could not be loaded.' }; }
  if (loaded.host) mountToggle(loaded.host);
  else notify('Theme Toggle', loaded.attachError);
}
