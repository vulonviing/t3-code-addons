// These exports are pinned by the installer to the exact installed bundle hashes.
import { al as registry } from '../utils-BL51zcsk.js';
import { rt as details } from '../projectGrouping-aRBPi9Ux.js';
import { ut as server } from '../themePalette-owjsZZI0.js';

export const host = {
  observeThread(ref, listener) {
    return registry.subscribe(details.threadAtom(ref), (value) => listener(value?.projection ?? null), { immediate: true });
  },
  observeProviders(environmentId, listener) {
    return registry.subscribe(server.configValueAtom(environmentId), (config) => listener(config?.providers ?? []), { immediate: true });
  },
};
