import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createConnection } from '../src/connection.mjs';
const captureFactory = () => ({ async prepare() {}, attach: stream => stream, release() {}, mute() {}, async drain() {}, close() {} });

test('Closing while microphone permission is pending stops a late media stream', async () => {
  let release, stopped = 0;
  const stream = { getTracks: () => [{ stop: () => stopped++ }] };
  const c = createConnection({ captureFactory, mediaDevices: { getUserMedia: () => new Promise(r => release = r) }, Peer: class {}, onEvent() {}, onError() {} });
  const opening = c.start(); await Promise.resolve(); await c.stop(); release(stream); await opening;
  assert.equal(stopped, 1);
});

test('Negotiation errors close the microphone and the peer', async () => {
  let stopped = 0, closed = 0;
  const track = { stop: () => stopped++ };
  class Peer {
    addTrack() {} createDataChannel() { return {}; }
    async createOffer() { return {}; }
    async setLocalDescription() { this.localDescription = { sdp: 'v=0' }; }
    close() { closed++; }
  }
  const c = createConnection({ captureFactory, mediaDevices: { async getUserMedia() { return { getTracks: () => [track], getAudioTracks: () => [track] }; } },
    Peer, call: async () => { throw new Error('Unavailable'); }, onEvent() {}, onError() {} });
  await assert.rejects(c.start(), /Unavailable/);
  assert.equal(stopped, 1); assert.equal(closed, 1);
});

test('Early audio is not released until the data channel and voice service are both ready', async () => {
  let negotiating, answer, channel, releases = 0;
  const negotiation = new Promise(r => { negotiating = r; });
  const track = { stop() {} }, stream = { getTracks: () => [track], getAudioTracks: () => [track] };
  class Peer {
    addTrack() {} createDataChannel() { channel = { readyState: 'open' }; return channel; }
    async createOffer() { return {}; } async setLocalDescription() { this.localDescription = { sdp: 'v=0' }; }
    async setRemoteDescription() {} close() {}
  }
  const c = createConnection({ captureFactory: () => ({ ...captureFactory(), release() { releases++; } }),
    mediaDevices: { async getUserMedia() { return stream; } }, Peer, onEvent() {}, onError() {},
    call(path) { if (path === '/stop') return Promise.resolve({}); negotiating(); return new Promise(r => { answer = r; }); },
  });
  const opening = c.start(); await negotiation; assert.equal(releases, 0);
  answer({ id: 'test', sdp: 'answer' }); await Promise.resolve(); await Promise.resolve();
  assert.equal(releases, 0);
  channel.onmessage({ data: JSON.stringify({ type: 'session.started' }) }); await opening;
  assert.equal(releases, 1); await c.stop();
});
