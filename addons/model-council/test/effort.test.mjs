import test from 'node:test';
import assert from 'node:assert/strict';
import { reasoningControls, setReasoningChoice, selectedReasoningLabel } from '../src/effort.mjs';

const model = { capabilities: { optionDescriptors: [
  { id: 'effort', label: 'Reasoning', type: 'select', currentValue: 'medium', options: [{ id: 'low', label: 'Low' }, { id: 'medium', label: 'Medium', isDefault: true }, { id: 'high', label: 'High' }, { id: 'ultrathink', label: 'Ultrathink' }], promptInjectedValues: ['ultrathink'] },
  { id: 'serviceTier', label: 'Speed', type: 'select', options: [{ id: 'fast', label: 'Fast' }] },
] } };

test('effort choices come from native capabilities and omit prompt-only levels', () => {
  const controls = reasoningControls(model);
  assert.equal(controls.length, 1); assert.equal(controls[0].defaultLabel, 'Medium');
  assert.deepEqual(controls[0].choices.map((c) => c.id), ['low', 'medium', 'high']);
  assert.deepEqual(reasoningControls({ capabilities: null }), []);
});

test('changing and resetting effort preserves unrelated options', () => {
  const control = reasoningControls(model)[0];
  const selection = { instanceId: 'codex', model: 'sol', options: [{ id: 'serviceTier', value: 'fast' }] };
  const updated = setReasoningChoice(selection, control, 'high');
  assert.equal(selectedReasoningLabel(model, updated), 'High');
  assert.deepEqual(updated.options, [{ id: 'serviceTier', value: 'fast' }, { id: 'effort', value: 'high' }]);
  assert.deepEqual(setReasoningChoice(updated, control, ''), selection);
  assert.throws(() => setReasoningChoice(selection, control, 'unsupported'));
});

test('boolean thinking is sent as a boolean rather than a string', () => {
  const control = reasoningControls({ capabilities: { optionDescriptors: [{ id: 'thinking', label: 'Thinking', type: 'boolean' }] } })[0];
  const updated = setReasoningChoice({ instanceId: 'cursor', model: 'x' }, control, 'false');
  assert.deepEqual(updated.options, [{ id: 'thinking', value: false }]);
  assert.equal(setReasoningChoice(updated, control, '').options, undefined);
});
