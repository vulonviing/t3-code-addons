// The companion card sits directly under T3's own thread-details card, matching its width, and never leaves the window.
export const GAP = 8;
export const MARGIN = 12;
export const MIN_HEIGHT = 80;

export function geometry(card, windowHeight) {
  return {
    left: Math.round(card.left),
    top: Math.round(card.bottom + GAP),
    width: Math.round(card.width),
    maxHeight: Math.max(MIN_HEIGHT, Math.round(windowHeight - card.bottom - GAP - MARGIN)),
  };
}

export function parseOpen(text) {
  let saved = {};
  try { saved = JSON.parse(text || '{}') || {}; } catch { /* damaged storage: everything collapsed */ }
  const open = {};
  for (const [id, value] of Object.entries(saved)) if (value === true) open[id] = true;
  return open;
}
