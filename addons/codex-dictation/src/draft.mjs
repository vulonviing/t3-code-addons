// Own only the draft version we last wrote. User edits and sends always take priority.
export function createDraftWriter(host, target) {
  const original = host.prompt(target);
  const prefix = original + (original && !/\s$/.test(original) ? '\n' : '');
  let expected = original;
  return {
    apply(transcript) {
      if (host.prompt(target) !== expected) throw new Error('Dictation stopped to preserve your edited or sent prompt.');
      const next = transcript ? prefix + transcript : original;
      if (next !== expected) { host.write(target, next); expected = next; }
    },
  };
}
