import { makeJob } from '../src/protocol.mjs';

export function fixture() {
  let id = 0;
  return makeJob({
    uuid: () => `id-${++id}`, ref: { environmentId: 'env', threadId: 'parent' },
    parent: { projectId: 'project', branch: 'main', worktreePath: null, runtimeMode: 'full-access', modelSelection: { instanceId: 'codex', model: 'final' } },
    question: 'Evaluate the architecture.', context: { text: 'Frozen context', selected: 2, omitted: 1 },
    members: ['claude', 'gemini', 'codex'].map((name) => ({ label: name, selection: { instanceId: name, model: name } })),
  });
}
