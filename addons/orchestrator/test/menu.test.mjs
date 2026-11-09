import test from 'node:test';
import assert from 'node:assert/strict';
import { modelOptions, routeRef } from '../src/menu.mjs';

test('modelOptions skips legacy models and labels by provider', () => {
  const providers = [
    { instanceId: 'c', driver: 'codex', displayName: 'Codex', models: [{ slug: 'a', name: 'A', isLegacy: false }, { slug: 'old', name: 'Old', isLegacy: true }] },
    { instanceId: 'k', driver: 'claude', models: [{ slug: 'b', name: 'B' }] },
  ];
  assert.deepEqual(modelOptions(providers), [
    { instanceId: 'c', slug: 'a', label: 'Codex / A' }, { instanceId: 'k', slug: 'b', label: 'claude / B' },
  ]);
  assert.deepEqual(modelOptions([]), []);
});

test('routeRef reads chat routes from path or hash and ignores other pages', () => {
  assert.deepEqual(routeRef({ pathname: '/env1/th1' }), { environmentId: 'env1', threadId: 'th1' });
  assert.deepEqual(routeRef({ hash: '#/env1/th1', pathname: '/' }), { environmentId: 'env1', threadId: 'th1' });
  assert.equal(routeRef({ pathname: '/settings/general' }), null);
  assert.equal(routeRef({ pathname: '/' }), null);
});
