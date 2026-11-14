import { notify } from './notice.mjs';
import { createRail } from './rail.mjs';
import { usageSection } from './usage-section.mjs';
import { planSection } from './plan-section.mjs';

const ID = 't3-adds-thread-details';
if (!document.getElementById(ID) && !document.getElementById(ID + '-notice')) {
  let loaded;
  try { loaded = await import('./host.mjs'); }
  catch { loaded = { host: null, attachError: 'a T3 module it depends on could not be loaded.' }; }
  if (loaded.host) {
    const rail = createRail(ID);
    rail.add(usageSection(loaded.host, rail.update));
    rail.add(planSection(loaded.host, rail.update, rail.repaint));
  } else notify('Thread Details', loaded.attachError);
}
