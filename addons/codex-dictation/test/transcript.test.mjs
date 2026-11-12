import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createTranscript } from '../src/transcript.mjs';

test('Frameless input fragments preserve spacing and replace replayed items without duplication', () => {
  const t = createTranscript();
  const input = (id, text) => t.accept({ type: 'input_transcript.added', item: { id, type: 'input_transcript', text } });
  assert.equal(input('a', 'Hello'), 'Hello');
  assert.equal(input('b', ' world'), 'Hello world');
  assert.equal(input('b', ' world'), 'Hello world');
  assert.equal(input('c', '.'), 'Hello world.');
  assert.equal(input('d', ' T\u00fcrk\u00e7e'), 'Hello world. T\u00fcrk\u00e7e');
});

test('Assistant responses, turn deltas, delegations, and malformed frames are excluded', () => {
  const t = createTranscript();
  for (const event of [
    { type: 'turn.delta', delta: 'I will do that.' },
    { type: 'output_transcript.added', item: { id: 'a', type: 'output_transcript', text: 'Assistant speech' } },
    { type: 'delegation.created', item: { content: [{ text: 'Execute this' }] } },
    { type: 'input_transcript.added', item: { type: 'input_transcript', text: 'Missing ID' } },
  ]) assert.equal(t.accept(event), null);
});

test('Completed standard transcripts replace partial text and survive replay', () => {
  const t = createTranscript();
  assert.equal(t.accept({ type: 'conversation.item.input_audio_transcription.delta', item_id: 'a', delta: 'Hell' }), 'Hell');
  assert.equal(t.accept({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'a', transcript: 'Hello.' }), 'Hello.');
  assert.equal(t.accept({ type: 'conversation.item.input_audio_transcription.completed', item_id: 'a', transcript: 'Hello.' }), 'Hello.');
});
