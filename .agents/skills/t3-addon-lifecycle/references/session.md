# External session record

Create one active session per application. Use an advisory lock while updating the session; write through a temporary file, flush it, and atomically replace the record. Keep completed sessions by session ID. Resolve paths at runtime; all paths and local identities belong only in external state.

Required fields:

- `schemaVersion`: initially 1.
- `id`: unique session identifier; `startedAt` and `updatedAt`: UTC timestamps.
- `phase`: `planned`, `withdrawing`, `awaiting-official-update`, `updating`, `assessing`, `awaiting-restart`, `awaiting-user`, or `complete`.
- `app`: resolved target path; `hostBefore` and `hostAfter`: version, commit, bundle identity and observed signature identity.
- `runningVersionVerified`: boolean; disk installation alone does not set it.
- `addons`: ID, previously installed version/source hashes, receipt reference, withdrawal transaction reference, assessment status, evidence, checks/results, and reinstallation receipt reference.
- `steps`: intended action, status (`planned`, `succeeded`, `failed`), relevant transaction ID, timestamp and concise result. Write `planned` before performing each application mutation.
- `nextAction`: explicit resumption step and any input needed from the user.

Keep evidence concise and factual: official artifact identity, relevant code locations, behavior comparison and test command/results. Do not copy private conversations, authentication state, or provider logs. Bundle inventories and exact changes belong in installer transaction records; reference them instead of duplicating them into Git.

This session is an AI workflow record, not a replacement for the installer's write-ahead transaction journal. Reconcile both with the current app before continuing. Archive a session as complete only after every selected addon has a reported disposition and the intended running host has been verified.
