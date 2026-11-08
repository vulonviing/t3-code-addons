import test from 'node:test';
import assert from 'node:assert/strict';
import { GAP, MARGIN, MIN_HEIGHT, geometry, parseOpen } from '../src/layout.mjs';

test('the card sits under the details card with the same left edge and width', () => {
  const placed = geometry({ left: 100.4, bottom: 300, width: 259.6 }, 900);
  assert.deepEqual(placed, { left: 100, top: 300 + GAP, width: 260, maxHeight: 900 - 300 - GAP - MARGIN });
});

test('the card shrinks to the room left and never below a usable height', () => {
  assert.equal(geometry({ left: 0, bottom: 860, width: 200 }, 900).maxHeight, MIN_HEIGHT);
});

test('saved open sections default to collapsed and ignore damaged or foreign values', () => {
  assert.deepEqual(parseOpen(null), {});
  assert.deepEqual(parseOpen('nope'), {});
  assert.deepEqual(parseOpen('{"a":true,"b":"yes","c":false}'), { a: true });
});
