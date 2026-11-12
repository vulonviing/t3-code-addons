import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createController } from '../src/controller.mjs';

function fixture(initial = '') {
  let target = 'chat1', prompt = initial, callbacks, muted = 0, closed = 0, starts = 0;
  const host = { target: () => target, prompt: () => prompt, write: (_target, text) => { prompt = text; } };
  const controller = createController({ host, finishMs: 0, connect(options) { callbacks = options; return {
    async start() { starts++; }, mute() { muted++; }, async stop() { closed++; },
  }; } });
  return { controller, get prompt() { return prompt; }, set prompt(v) { prompt = v; },
    set target(v) { target = v; }, get muted() { return muted; }, get closed() { return closed; }, get starts() { return starts; },
    emit(id, text) { callbacks.onEvent({ type: 'input_transcript.added', item: { id, type: 'input_transcript', text } }); },
    assistant() { callbacks.onEvent({ type: 'output_transcript.added', item: { id: 'assistant', type: 'output_transcript', text: 'Ignored' } }); },
  };
}

test('Speech appears live in the existing prompt and stop mutes synchronously without sending', async () => {
  const f = fixture('Existing prompt'); await f.controller.start();
  f.emit('a', 'Hello'); assert.equal(f.prompt, 'Existing prompt\nHello');
  f.emit('b', ' world'); assert.equal(f.prompt, 'Existing prompt\nHello world');
  f.emit('b', ' world'); f.assistant(); assert.equal(f.prompt, 'Existing prompt\nHello world');
  const stopping = f.controller.stop(); assert.equal(f.muted, 1);
  f.emit('c', '.'); await stopping; assert.equal(f.prompt, 'Existing prompt\nHello world.');
  f.emit('d', ' Late'); assert.equal(f.prompt, 'Existing prompt\nHello world.');
  assert.equal(f.closed, 1); assert.equal(f.controller.state().phase, 'idle');
});

test('Manual edits stop dictation and are never overwritten', async () => {
  const f = fixture(); await f.controller.start(); f.emit('a', 'Hello');
  f.prompt = 'Edited by the user'; f.emit('b', ' world'); await f.controller.stop();
  assert.equal(f.prompt, 'Edited by the user'); assert.match(f.controller.state().error, /edited or sent/);
});

test('Sending/clearing the draft while recording never recreates the sent prompt', async () => {
  const f = fixture(); await f.controller.start(); f.emit('a', 'Send this');
  f.prompt = ''; f.emit('b', ' late'); await f.controller.stop();
  assert.equal(f.prompt, '');
});

test('Navigation never writes a late transcript to another chat', async () => {
  const f = fixture(); await f.controller.start(); f.emit('a', 'Hello');
  f.target = 'chat2'; f.prompt = 'Other chat'; f.emit('b', ' world'); await f.controller.stop();
  assert.equal(f.prompt, 'Other chat');
});

test('Repeated start shares one recording, and a new recording appends to the completed draft', async () => {
  const f = fixture(); await f.controller.start(); await f.controller.start();
  assert.equal(f.starts, 1); f.emit('a', 'First'); await f.controller.stop();
  await f.controller.start(); f.emit('a', 'Second'); await f.controller.stop();
  assert.equal(f.prompt, 'First\nSecond');
});

test('A background stop discards late events immediately', async () => {
  const f = fixture(); await f.controller.start(); f.emit('a', 'First');
  const stopping = f.controller.stop({ drain: false }); f.emit('b', ' late'); await stopping;
  assert.equal(f.prompt, 'First');
});

test('Stopping mutes immediately but drains buffered speech before closing the connection', async () => {
  let drained, muted = false, closed = false;
  const controller = createController({ host: { target: () => 'chat', prompt: () => '', write() {} }, finishMs: 0,
    connect: () => ({ async start() {}, mute() { muted = true; }, drain() { return new Promise(resolve => { drained = resolve; }); }, async stop() { closed = true; } }),
  });
  await controller.start(); const stopping = controller.stop();
  assert.equal(muted, true); assert.equal(closed, false); assert.equal(controller.state().phase, 'finishing');
  drained(); await stopping; assert.equal(closed, true); assert.equal(controller.state().phase, 'idle');
});
