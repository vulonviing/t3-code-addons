import test from 'node:test';
import assert from 'node:assert/strict';
import { view, choose } from '../src/toggle.mjs';

test('view reports the resolved theme and whether the system is being followed', () => {
  assert.deepEqual(view({ resolvedTheme: 'dark', appearanceMode: 'system', followSystem: true }), { resolved: 'dark', following: true });
  assert.deepEqual(view({ resolvedTheme: 'light', appearanceMode: 'light', followSystem: false }), { resolved: 'light', following: false });
  assert.equal(view({ resolvedTheme: 'unknown' }).resolved, 'light');
});

test('choose pins an explicit mode through the host', () => {
  const calls = [];
  choose({ setAppearanceMode: (mode) => (calls.push(mode), true) }, 'dark');
  assert.deepEqual(calls, ['dark']);
});

test('choose rejects unsupported modes and failed saves', () => {
  assert.throws(() => choose({ setAppearanceMode: () => true }, 'system'), /Unsupported/);
  assert.throws(() => choose({ setAppearanceMode: () => false }, 'light'), /could not save/);
});
