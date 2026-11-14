import { createCapture } from './capture.mjs';
const BASE = 'http://127.0.0.1:48173';
export async function request(path, body, signal) {
  let response;
  try {
    response = await fetch(BASE + path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-T3-Dictation': '1' }, body: JSON.stringify(body), signal, keepalive: path === '/stop' });
  } catch (error) {
    if (error.name === 'AbortError') throw error;
    throw new Error('The dictation helper is unavailable. Run scripts/service.py check or install.');
  }
  const value = await response.json();
  if (!response.ok) throw new Error(value.error ?? 'Dictation could not start.');
  return value;
}

export function createConnection({ onEvent, onError, onLevel, mediaDevices = navigator.mediaDevices, Peer = RTCPeerConnection, call = request, captureFactory = createCapture }) {
  let leaseTimer;
  let pc, stream, session, capture, opening, muted = false, aborted = false, serviceReady = false, readyResolve;
  const ready = new Promise(resolve => { readyResolve = resolve; });
  const abort = new AbortController();
  function closeMedia() { stream?.getTracks().forEach((t) => t.stop()); capture?.close(); pc?.close(); readyResolve(); }
  async function stop() {
    aborted = true;
    clearTimeout(leaseTimer);
    closeMedia();
    // The start response owns cleanup if the request is still in flight.
    if (session) { const id = session; session = null; await call('/stop', { id }).catch(() => {}); }
  }
  async function renewLease() {
    if (aborted || !session) return;
    try {
      await call('/keepalive', { id: session });
      if (!aborted) leaseTimer = setTimeout(renewLease, 30000);
    } catch {
      if (!aborted) { await stop(); onError(new Error('The dictation helper connection was lost. Your transcript is preserved.')); }
    }
  }
  return {
    start() {
      opening = this.open(); return opening;
    },
    async open() {
      try {
        capture = captureFactory({ onLevel });
        await capture.prepare();
        if (aborted || muted) { await stop(); return; }
        stream = await mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true }, video: false });
        if (aborted || muted) { await stop(); return; }
        pc = new Peer({ iceServers: [] });
        const outgoing = capture.attach(stream);
        for (const track of outgoing.getAudioTracks()) pc.addTrack(track, outgoing);
        const channel = pc.createDataChannel('oai-events');
        channel.onmessage = ({ data }) => { try {
          const event = JSON.parse(data);
          if (event.type === 'session.started') { serviceReady = true; readyResolve(); }
          onEvent(event);
        } catch { /* Ignore non-JSON protocol frames. */ } };
        pc.onconnectionstatechange = () => {
          if (!aborted && ['failed', 'disconnected'].includes(pc.connectionState)) { void stop(); onError(new Error('The voice connection closed. Your transcript is preserved.')); }
        };
        // Remote assistant audio is intentionally never played.
        await pc.setLocalDescription(await pc.createOffer());
        const result = await call('/start', { sdp: pc.localDescription.sdp }, abort.signal);
        session = result.id;
        if (!aborted) leaseTimer = setTimeout(renewLease, 30000);
        if (aborted) { await stop(); return; }
        await pc.setRemoteDescription({ type: 'answer', sdp: result.sdp });
        await new Promise((resolve, reject) => {
          if (channel.readyState === 'open') return resolve();
          const timer = setTimeout(() => reject(new Error('The voice connection timed out.')), 15000);
          channel.addEventListener('open', () => { clearTimeout(timer); resolve(); }, { once: true });
          channel.addEventListener('close', () => { clearTimeout(timer); reject(new Error('The voice connection closed.')); }, { once: true });
        });
        if (!serviceReady && !aborted) await new Promise((resolve, reject) => {
          const timer = setTimeout(() => reject(new Error('The voice service did not become ready.')), 15000);
          ready.then(() => { clearTimeout(timer); resolve(); });
        });
        if (!aborted) capture.release();
      } catch (error) { await stop(); if (!aborted || error.name !== 'AbortError') throw error; }
    },
    // Keep the connection alive briefly after muting, so the last words can arrive.
    mute() { muted = true; stream?.getTracks().forEach((t) => t.stop()); capture?.mute(); },
    async drain() { await opening?.catch(() => {}); if (!aborted) await capture?.drain(); },
    stop,
  };
}
