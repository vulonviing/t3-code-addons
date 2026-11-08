import { host } from './host-v017.mjs';
import { createRail } from './rail.mjs';
import { usageSection } from './usage-section.mjs';
import { planSection } from './plan-section.mjs';

const ID = 't3-adds-thread-details';
if (!document.getElementById(ID)) {
  const rail = createRail(ID);
  rail.add(usageSection(host, rail.update));
  rail.add(planSection(host, rail.update, rail.repaint));
}
