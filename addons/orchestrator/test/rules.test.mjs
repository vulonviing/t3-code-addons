import test from 'node:test';
import assert from 'node:assert/strict';
import { MARKER, activationText, updateText, reminderText, endText, nativeAlias } from '../src/rules.mjs';

const model = { instanceId: 'codex', slug: 'gpt-x', label: 'Codex / GPT X' };
const claude = { instanceId: 'claude', slug: 'claude-sonnet-5-5', label: 'Claude / Sonnet 5.5' };

test('every message starts with the marker', () => {
  for (const text of [activationText(null), activationText(model), updateText(null), updateText(model), reminderText(null), endText()]) {
    assert.ok(text.startsWith(MARKER));
  }
});

test('activation without a default carries the coordinator rules but no model sentence', () => {
  const text = activationText(null);
  for (const word of ['never', 'edit files', 'delegate', 'context', 'plan', 'check']) assert.ok(text.includes(word), word);
  assert.ok(!text.includes('default model'));
  assert.match(text, /model "sonnet"/);
  assert.ok(!text.includes('choose as you normally would'));
});

test('activation with a default names the provider instance, model, delegate_task and the override rule', () => {
  const text = activationText(model);
  for (const word of ['providerInstanceId', 'codex', 'gpt-x', 'delegate_task', 'explicitly asks']) assert.ok(text.includes(word), word);
});

test('activation carries the budget, reuse, reply, review, approval and Opus rules', () => {
  const text = activationText(null);
  for (const word of ['DONE', 'NEEDS_INPUT', 'BLOCKED', 'at most 5', 'Never more than 3', 'ops', 'Opus', 'diff', '2 fix-and-review', 'plan', 'follow-up']) assert.ok(text.includes(word), word);
});

test('a Claude default names the native alias and a Codex default does not', () => {
  assert.match(activationText(claude), /model "sonnet"/);
  assert.match(activationText(claude), /delegate_task/);
  const codex = activationText(model);
  assert.ok(!codex.includes('model "sonnet"'));
  assert.ok(codex.includes('delegate_task') && codex.includes('gpt-x'));
});

test('effort sentence follows the chosen level', () => {
  assert.match(activationText(null, 'task'), /low for search, git, and fully specified edits/);
  assert.match(activationText(null, 'low'), /use low for every subagent/);
  assert.match(activationText(null, 'medium'), /use medium for every subagent/);
  assert.match(updateText(model, 'low'), /low/);
  assert.match(reminderText(model, 'medium'), /medium/);
});

test('nativeAlias maps Claude slugs to native aliases and ignores other providers', () => {
  assert.equal(nativeAlias('claude-sonnet-5-5'), 'sonnet');
  assert.equal(nativeAlias('Claude-HAIKU-5-5'), 'haiku');
  assert.equal(nativeAlias('claude-opus-5-5'), 'opus');
  assert.equal(nativeAlias('gpt-x'), null);
});

test('update says when there is no default, end says ended, reminder is short', () => {
  assert.match(updateText(null), /No default subagent model/);
  assert.match(updateText(model), /gpt-x/);
  assert.match(endText(), /ended/);
  assert.ok(reminderText(model).length < activationText(model).length);
});
