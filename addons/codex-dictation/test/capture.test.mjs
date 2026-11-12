import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

test('Capture worklet preserves the beginning and flushes the final partial batch in order', () => {
  let Processor; const messages = [];
  vm.runInNewContext(readFileSync(new URL('../src/capture-worklet.mjs', import.meta.url), 'utf8'), {
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: data => messages.push(data) }; } },
    registerProcessor(_name, implementation) { Processor = implementation; },
  });
  const capture = new Processor();
  const first = new Float32Array(2000).fill(.25), last = new Float32Array(200).fill(.5);
  capture.process([[first]]); capture.process([[last]]);
  assert.equal(messages.length, 1); assert.equal(messages[0].samples.length, 2048);
  assert.equal(messages[0].samples[0], .25); assert.equal(messages[0].samples[2000], .5);
  capture.port.onmessage({ data: 'flush' });
  assert.equal(messages[1].samples.length, 152); assert.equal(messages[1].samples[0], .5);
  assert.equal(messages[2].flushed, true);
});
