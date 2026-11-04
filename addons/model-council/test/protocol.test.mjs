import test from 'node:test';
import assert from 'node:assert/strict';
import { selectContext, makeJob, opinionPrompt, reviewPrompt, synthesisPrompt, synthesisMessage, contribution, routeRef, MAX_CONTRIBUTION_BYTES } from '../src/protocol.mjs';

import { fixture } from './fixtures.mjs';

test('selection preserves whole records, chronology, first request and recent exchanges within budget', () => {
  const items = Array.from({ length: 40 }, (_, i) => ({ item: { id: `i-${i}`, type: i % 2 ? 'assistant_message' : 'user_message', text: `${i} ${'\u00fc'.repeat(100)}` } }));
  const selected = selectContext({ threadId: 'source', items }, 2000);
  assert.ok(selected.omitted > 0);
  assert.ok(selected.itemIds.includes('i-0'));
  assert.ok(selected.itemIds.includes('i-38'));
  assert.ok(selected.itemIds.includes('i-39'));
  assert.ok(Buffer.byteLength(selected.text) <= 2000);
  assert.deepEqual(selected.itemIds, [...selected.itemIds].sort((a, b) => +a.slice(2) - +b.slice(2)));
  assert.match(selected.text, /t3_thread_read/);
});

test('oversized record is omitted intact rather than silently shortened', () => {
  const selected = selectContext({ threadId: 'source', items: [{ item: { id: 'huge', type: 'user_message', text: 'x'.repeat(100_000) } }] });
  assert.equal(selected.selected, 0); assert.equal(selected.omitted, 1);
});

test('participant output is bounded in UTF-8 bytes with an explicit recovery marker', () => {
  const answer = contribution('🌏'.repeat(20_000), 'Gemini');
  assert.equal(answer.truncated, true);
  assert.ok(Buffer.byteLength(answer.text) <= MAX_CONTRIBUTION_BYTES);
  assert.match(answer.text, /complete answer/);
});

test('opinion is independent; review sees the same complete opinion packet; synthesis preserves disagreement', () => {
  const job = fixture();
  job.members.forEach((m) => { m.opinion = { text: `Opinion ${m.label}` }; m.review = { text: `Review ${m.label}` }; });
  assert.doesNotMatch(opinionPrompt(job), /Opinion claude/);
  for (const member of job.members) {
    assert.ok(reviewPrompt(job).includes(member.opinion.text));
    assert.ok(synthesisPrompt(job).includes(member.review.text));
  }
  assert.match(synthesisPrompt(job), /preserve unresolved disagreements/);
  assert.match(opinionPrompt(job), /do not edit files/);
});

test('model identity uses provider instance and model; route handles Electron hash and web paths', () => {
  const job = fixture(); assert.equal(job.members.length, 3);
  assert.deepEqual(routeRef({ hash: '#/env/thread?tab=x', pathname: '/' }), { environmentId: 'env', threadId: 'thread' });
  assert.deepEqual(routeRef({ hash: '', pathname: '/env/thread' }), { environmentId: 'env', threadId: 'thread' });
  assert.equal(routeRef({ hash: '#/settings/providers', pathname: '/' }), null);
});

test('final message carries council evidence as referenced native context, keeping the chat readable', () => {
  const job = fixture();
  job.members.forEach((m) => { m.opinion = contribution('Opinion'.repeat(10_000), m.label); m.review = contribution('Review'.repeat(10_000), m.label); });
  const message = synthesisMessage(job);
  assert.equal(message.context.records.length, 7);
  assert.ok(message.text.length < 2500);
  for (const record of message.context.records) {
    assert.match(record.contextId, /^[a-z0-9_-]{1,128}$/i);
    assert.ok(JSON.stringify(record.payload).length <= 64_000);
    assert.ok(message.text.includes(`t3-context://v1/model-council/${record.contextId}`));
  }
});
