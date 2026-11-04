import test from 'node:test';
import assert from 'node:assert/strict';
import { IDBFactory } from 'fake-indexeddb';
import { createStorage } from '../src/storage.mjs';
import { fixture } from './fixtures.mjs';

test('jobs and selected model settings survive reopening storage', async () => {
  const idb = new IDBFactory(), storage = createStorage(idb), job = fixture();
  await storage.save(job);
  const reopened = createStorage(idb);
  assert.deepEqual(await reopened.get(job.id), job);
  assert.equal((await reopened.all()).length, 1);
});

test('cross-window cancellation cannot be overwritten by a stale worker', async () => {
  const idb = new IDBFactory(), worker = createStorage(idb), otherWindow = createStorage(idb), job = fixture();
  await worker.save(job);
  const cancelled = structuredClone(job); cancelled.cancelRequested = true; cancelled.stage = 'cancelled';
  await otherWindow.save(cancelled);
  job.stage = 'reviews'; await worker.save(job);
  const result = await worker.get(job.id);
  assert.equal(result.cancelRequested, true); assert.equal(result.stage, 'cancelled');
  assert.equal(job.cancelRequested, true);
});
