import { createTranscript } from './transcript.mjs';
import { createDraftWriter } from './draft.mjs';

export function createController({ host, connect, changed = () => {}, level = () => {}, finishMs = 1200 }) {
  let session = null, phase = 'idle', error = '';
  const notify = () => changed({ phase, error });
  function stop({ drain = true, message = '' } = {}) {
    const s = session;
    if (!s) return Promise.resolve();
    if (!drain) s.accepting = false;
    if (message) error = message;
    if (s.stopping) { notify(); return s.stopping; }
    s.connection.mute();
    phase = 'finishing'; notify();
    s.stopping = (async () => {
      if (drain) { await s.connection.drain?.(); await new Promise(resolve => setTimeout(resolve, finishMs)); }
      s.accepting = false;
      await s.connection.stop();
    })().catch(e => { error = e.message; }).finally(() => {
      if (session === s) { session = null; phase = 'idle'; notify(); }
    });
    return s.stopping;
  }
  async function start() {
    if (session) return;
    const target = host.target();
    if (!target) return;
    const unsupported = host.unsupported?.();
    if (unsupported) { error = unsupported; notify(); return; }
    error = '';
    const transcript = createTranscript(), writer = createDraftWriter(host, target);
    const s = { target, accepting: true };
    s.connection = connect({
      onLevel(value) { if (session === s && phase === 'recording') level(value); },
      onEvent(event) {
        if (session !== s || !s.accepting) return;
        if (event.type === 'error') { void stop({ drain: false, message: 'The voice service reported an error. Please try again.' }); return; }
        const text = transcript.accept(event);
        if (text === null) return;
        try { writer.apply(text); }
        catch (e) { void stop({ drain: false, message: e.message }); }
      },
      onError(e) { if (session === s) void stop({ drain: false, message: e.message }); },
    });
    session = s; phase = 'connecting'; notify();
    try {
      await s.connection.start();
      if (session !== s || s.stopping) return;
      phase = 'recording'; notify();
    } catch (e) {
      if (session === s) await stop({ drain: false, message: e.name === 'NotAllowedError' ? 'Microphone access was denied. Allow it in system settings and try again.' : e.message });
    }
  }
  return { start, stop, state: () => ({ phase, error }), target: () => session?.target ?? null };
}
