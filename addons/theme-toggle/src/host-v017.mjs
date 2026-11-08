// These exports are pinned by the installer to the exact installed bundle hashes.
import { c as setAppearanceMode, n as snapshot, u as subscribe } from '../useTheme-DGh-F8xD.js';

export const host = {
  snapshot() { return snapshot(); },
  setAppearanceMode(mode) { return setAppearanceMode(mode); },
  subscribe(listener) { return subscribe(listener); },
};
