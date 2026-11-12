// Verified public draft-store actions; the imported host module is hash-pinned.
import { A as drafts } from '../utils-BL51zcsk.js';

export function routeTarget(location) {
  const path = location.hash?.startsWith('#/') ? location.hash.slice(1) : location.pathname;
  let parts;
  try { parts = path.split('?')[0].split('/').filter(Boolean).map(decodeURIComponent); }
  catch { return null; }
  if (parts.length !== 2) return null;
  if (parts[0] === 'draft') return parts[1];
  return ['settings', 'onboarding'].includes(parts[0]) ? null : { environmentId: parts[0], threadId: parts[1] };
}

export const host = {
  target: () => routeTarget(window.location),
  prompt(target) { return drafts.getState().getComposerDraft(target)?.prompt ?? ''; },
  write(target, text) {
    const current = this.target();
    if (JSON.stringify(current) !== JSON.stringify(target)) throw new Error('Return to the chat where you started dictation before inserting.');
    drafts.getState().setPrompt(target, text);
  },
  focus() {
    const input = [...document.querySelectorAll('[data-chat-composer-form="true"] textarea, [data-chat-composer-form="true"] [role="textbox"], [data-chat-composer-form="true"] [contenteditable="true"]')].find(e => e.getClientRects().length);
    input?.focus({ preventScroll: true });
    if (input?.setSelectionRange) input.setSelectionRange(input.value.length, input.value.length);
  },
};
