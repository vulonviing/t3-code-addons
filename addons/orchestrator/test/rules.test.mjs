import test from 'node:test';
import assert from 'node:assert/strict';
import { MARKER, activationText, updateText, reminderText, endText } from '../src/rules.mjs';

const model = { instanceId: 'codex', slug: 'gpt-x', label: 'Codex / GPT X' };

test('every message starts with the marker', () => {
  for (const text of [activationText(null), activationText(model), updateText(null), updateText(model), reminderText(null), endText()]) {
    assert.ok(text.startsWith(MARKER));
  }
});

test('activation without a default carries the coordinator rules but no model sentence', () => {
  const text = activationText(null);
  for (const word of ['never', 'edit files', 'delegate', 'context', 'plan', 'check']) assert.ok(text.includes(word), word);
  assert.ok(!text.includes('default model'));
});

test('activation with a default names the provider instance, model, delegate_task and the override rule', () => {
  const text = activationText(model);
  for (const word of ['providerInstanceId', 'codex', 'gpt-x', 'delegate_task', 'explicitly asks']) assert.ok(text.includes(word), word);
});

test('update says when there is no default, end says ended, reminder is short', () => {
  assert.match(updateText(null), /no default model/);
  assert.match(updateText(model), /gpt-x/);
  assert.match(endText(), /ended/);
  assert.ok(reminderText(model).length < activationText(model).length);
});
