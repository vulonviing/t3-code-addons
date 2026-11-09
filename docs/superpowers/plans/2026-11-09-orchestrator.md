# Orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A T3 overlay addon whose composer button turns the chat's agent into a coordinator that only delegates to subagents, with a right-click menu for the default subagent model.

**Architecture:** Client-only overlay (one `<script>` entry plus `assets/orchestrator/` files) like Theme Toggle. Pure modules (`rules`, `state`, `controller`) take an injected `host`; `host-v017.mjs` is the only file importing T3 bundles; `ui.mjs` mounts the button and menu. Rules are delivered as a `message.dispatch` turn into the chat.

**Tech Stack:** Plain ES modules, `node --test`, Python 3 installer copied from Theme Toggle.

**Spec:** `docs/superpowers/specs/2026-11-09-orchestrator-design.md`

## Global Constraints

- Addon lives in `addons/orchestrator/`, id `orchestrator`, name `Orchestrator`, version `0.1.0`; independent of every sibling addon and the library root.
- Target T3 `0.1.7`, commit `322f6544dfad`.
- English only; no personal names, absolute paths, or identities anywhere.
- No polling and no timers for idle work; event-driven redraws only.
- Never insert into T3-owned React containers' children; attach the mount as a sibling in the composer footer exactly as Model Council does (`insertBefore` the `[data-chat-composer-actions="right"]` node). Never patch T3 functions.
- Persisted state uses `localStorage` inside try/catch; the page must work when it throws.
- Host imports pinned by sha256 in `compatibility.json`.
- Commits are made only if the user asks for them.

## Review Focus

- localStorage unavailable or throwing: button still renders and toggles for the session.
- Chat busy at activation: rules are queued (`queue_after_active`), button shows "Starting…", then "On" once the run exists.
- Chat has no selected model or provider list is empty: menu shows "No default" and rules omit the default-model sentence.
- Default model removed or disabled later: menu shows it as unavailable and rules fall back to "no default".
- Double click / repeated activation: stable `commandId` and `messageId` per activation, so T3 does not run it twice.
- Script loaded twice (as Theme Toggle's verify does): only one mount.

---

### Task 1: Scaffold the addon and installer

**Files:**
- Create: `addons/orchestrator/{addon.json,compatibility.json,package.json,README.md}`
- Create (copied from `addons/theme-toggle/scripts/`): `asar.py extract_client.py install.py lifecycle.py signing.py test_asar.py test_installer.py`
- Create: `addons/orchestrator/src/host-v017.mjs` (placeholder exporting `host = {}`), `addons/orchestrator/src/ui.mjs` (placeholder, empty module)

**Interfaces:**
- Produces: `addon.json` with `"id":"orchestrator","entry":"src/ui.mjs","adapter":"src/host-v017.mjs"`; the installer globs `src/*.mjs` into `assets/orchestrator/`.

- [ ] **Step 1:** Copy the scripts folder from Theme Toggle excluding `__pycache__` and `verify_host.mjs`. Write `addon.json` (fields as in Theme Toggle's, new id/name/description "Turns the chat's agent into a coordinator that delegates all work to subagents."), `package.json` (`@t3-adds/orchestrator`, same scripts), and an empty `compatibility.json` `{}`.
- [ ] **Step 2:** Run `python3 -I scripts/test_installer.py` and `python3 -I scripts/test_asar.py` in `addons/orchestrator`. Expected: both pass (they are addon-agnostic; if either references `theme-toggle`, change it to read the id from `addon.json`).
- [ ] **Step 3:** Run `python3 -I scripts/install.py check`. Expected: reports compatible and absent (or the same status Theme Toggle's check reports on a not-yet-installed addon). The only placeholder pins are fixed in Task 5.

### Task 2: Rules text

**Files:**
- Create: `addons/orchestrator/src/rules.mjs`
- Test: `addons/orchestrator/test/rules.test.mjs`

**Interfaces:**
- Produces:
  - `MARKER = '[T3 Adds · Orchestrator]'`
  - `defaultModelSentence(model) -> string` where `model` is `{ instanceId, slug, label } | null`
  - `activationText(model) -> string`, `updateText(model) -> string`, `reminderText(model) -> string`, `endText() -> string`; every one starts with `MARKER`.

- [ ] **Step 1: Write failing tests** asserting: every export starts with `MARKER`; `activationText(null)` contains "never" and each of: "edit files", "delegate", "context", "plan", "check", and does not contain "default model"; `activationText({instanceId:'codex',slug:'gpt-x',label:'Codex / GPT X'})` contains `providerInstanceId`, `codex`, `gpt-x`, `delegate_task`, and "explicitly asks"; `updateText(null)` says there is no default model now; `endText()` contains "ended"; `reminderText` is shorter than `activationText`.
- [ ] **Step 2:** Run `node --test test/rules.test.mjs`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the module. Content follows the spec's "Rules text" list verbatim in meaning: never edit files, run implementation commands, commit or install; delegate everything; start with parallel context-gathering subagents returning short evidence-based reports; plan from them; split into independent parts; one subagent per part; separate checking subagents per result; ask for summaries only; report decisions, results, risks; an explicit per-task model request from the user overrides the default. Native tools (Claude `Agent`, Codex `spawn_agent`) when the child uses the same provider; `delegate_task` with `target {providerInstanceId, model}` otherwise.
- [ ] **Step 4:** Run the test. Expected: PASS.

### Task 3: Persisted state

**Files:**
- Create: `addons/orchestrator/src/state.mjs`
- Test: `addons/orchestrator/test/state.test.mjs`

**Interfaces:**
- Produces: `createState(storage) -> { get(ref), setEnabled(ref, value, messageId?), activation(ref), defaultModel(), setDefaultModel(model|null) }` where `ref = { environmentId, threadId }`, `activation(ref) -> { enabled: boolean, messageId: string|null }`, `defaultModel` returns `{ instanceId, slug, label } | null`. `storage` is a `Storage`-like object (`getItem`, `setItem`, `removeItem`) and may throw.

- [ ] **Step 1: Write failing tests:** round trip of per-chat enabled and messageId; two chats are independent; default model round trip and clearing; with a storage whose methods throw, the same calls work in memory for the session and never throw; corrupt JSON in storage reads as "off / no default".
- [ ] **Step 2:** Run `node --test test/state.test.mjs`. Expected: FAIL.
- [ ] **Step 3:** Implement with an in-memory map as the source of truth and storage as best-effort write-through under keys `t3-adds:orchestrator:chat:<env>:<thread>` and `t3-adds:orchestrator:model`.
- [ ] **Step 4:** Run the test. Expected: PASS.

### Task 4: Controller

**Files:**
- Create: `addons/orchestrator/src/controller.mjs`
- Test: `addons/orchestrator/test/controller.test.mjs`

**Interfaces:**
- Consumes: `rules.mjs` exports; `createState` from Task 3.
- Host contract: `host.parent(ref) -> { status, modelSelection } | null`, `host.projection(ref) -> { runs: [{ userMessageId }] } | null`, `host.providers(ref) -> [{ instanceId, driver, displayName, models: [{ slug, name, isLegacy }] }]`, `host.canOperate(ref) -> boolean`, `host.command(ref, command) -> Promise`.
- Produces: `createController({ host, state, newId }) -> { status(ref), toggle(ref), remind(ref), setDefaultModel(ref, model|null), resolveDefault(ref) }`.
  - `status(ref)` returns `'off' | 'starting' | 'on'`: `off` if not enabled; `on` if a run with `userMessageId === activation.messageId` exists; otherwise `starting`.
  - `resolveDefault(ref)` returns the stored default only if its provider instance and non-legacy model are still offered by `host.providers(ref)`, else `null`.

- [ ] **Step 1: Write failing tests** with a fake host recording commands: `toggle` from off sends exactly one `message.dispatch` with `threadId`, a fresh `messageId`, `text` starting with `MARKER`, `attachments: []`, `modelSelection` equal to the parent's, `dispatchMode.type === 'start_immediately'` when the parent status is idle and `'queue_after_active'` when it is `running`; the `commandId` is `orchestrator:<messageId>`; `toggle` from on sends the `endText` turn and `status` becomes `off`; `status` goes `starting` then `on` when the projection gains the matching run; `remind` and `setDefaultModel` while on each send one turn (`reminderText`, `updateText`) and send nothing while off (state only); `toggle` throws a clear error when `canOperate` is false and changes no state; a failing `host.command` leaves state off and rethrows; unavailable stored default resolves to `null`.
- [ ] **Step 2:** Run `node --test test/controller.test.mjs`. Expected: FAIL.
- [ ] **Step 3:** Implement. Order inside `toggle` on: build rules from `resolveDefault`, dispatch, then persist `setEnabled(ref, true, messageId)` only after dispatch resolves.
- [ ] **Step 4:** Run the test. Expected: PASS.

### Task 5: Host adapter and pins

**Files:**
- Modify: `addons/orchestrator/src/host-v017.mjs`, `addons/orchestrator/compatibility.json`
- Create: `addons/orchestrator/scripts/verify_host.mjs` (adapted from Theme Toggle's)

**Interfaces:**
- Produces: `host` implementing the Task 4 host contract, reusing the exact bundle imports and bodies from `addons/model-council/src/host-v017.mjs` for `parent`, `projection`, `canOperate`, `providers`, and `command` (without the auto-settle branch). The adapter copies them rather than importing across addons.

- [ ] **Step 1:** Write `host-v017.mjs` with the imports of utils, queries, projectGrouping, themePalette, session (same names as Model Council's adapter).
- [ ] **Step 2:** Fill `compatibility.json` with those five files' sha256 values, copied from Model Council's `compatibility.json`.
- [ ] **Step 3:** Adapt `verify_host.mjs`: load the extracted official client assets in an isolated Chromium context, import `/assets/orchestrator/host-v017.mjs`, assert the host reads fixture thread data and forwards a `message.dispatch` with the expected shape. Do not call any model. Keep it external to the repo's installed state as Theme Toggle's does.
- [ ] **Step 4:** Run `python3 -I scripts/install.py check`. Expected: pins match the installed app and the status is compatible.

### Task 6: UI — button and right-click menu

**Files:**
- Modify: `addons/orchestrator/src/ui.mjs`
- Create: `addons/orchestrator/src/menu.mjs`
- Test: `addons/orchestrator/test/menu.test.mjs`

**Interfaces:**
- Consumes: `createController`, `createState`, `host`, `routeRef` logic equivalent to Model Council's (parse the current route to `{ environmentId, threadId }`; the helper is local to this addon).
- Produces: `menu.mjs` exports `modelOptions(providers) -> [{ instanceId, slug, label }]` (non-legacy models only, label `"<provider displayName or driver> / <model name>"`).

- [ ] **Step 1: Write failing tests** for `modelOptions`: legacy models are excluded; labels as specified; empty provider list gives `[]`.
- [ ] **Step 2:** Run `node --test test/menu.test.mjs`. Expected: FAIL; then implement `menu.mjs`; expected PASS.
- [ ] **Step 3:** Implement `ui.mjs`: guard against double load with `#t3-adds-orchestrator`; shadow-root button "Orchestrator" with `aria-pressed`, green background when `on`, "Starting…" label while `starting`; hidden when no current chat; mount placed in the visible composer footer before `[data-chat-composer-actions="right"]` and after `#t3-adds-council-composer` when present; re-attach on route change (Navigation API) and when the footer node changes (one MutationObserver on the composer form only); redraw on `host.observe`-style projection updates only while attached. Click toggles via the controller and shows errors in the button's `title` and a small inline message.
- [ ] **Step 4:** Right-click (`contextmenu`) opens a menu in the same shadow root: "Subagent model" with a `No default` item plus `modelOptions` items (current choice marked), and "Remind now" (disabled when off). Menu closes on outside click, Escape, and blur; it is keyboard-reachable (`Shift+F10`/context-menu key and arrow keys).
- [ ] **Step 5:** Narrow-width rule like Model Council: below 600px the button shows an icon only.

### Task 7: README, full verification, handoff

**Files:**
- Modify: `addons/orchestrator/README.md`

- [ ] **Step 1:** Write the README: purpose, requirements, install/update/remove commands (same as Theme Toggle's), use (toggle, right-click menu, per-task override in plain words, Remind now), how it works (rules delivered as a chat message; T3's own subagent tools), limitations (soft rules, not a sandbox; long chats can dilute the rules; no per-message reminder; state is per browser profile; the activation message is visible in the chat), compatibility, validation done and not done.
- [ ] **Step 2:** Run `npm test` in `addons/orchestrator`. Expected: all node and Python tests pass.
- [ ] **Step 3:** Run `python3 -I scripts/install.py check`. Expected: compatible.
- [ ] **Step 4:** Search the addon for personal data: `grep -rIn "/Users/\|@gmail" addons/orchestrator docs` returns nothing.
- [ ] **Step 5:** Stop. Installing into the real app (`apply`) needs the user's go-ahead (AGENTS.md); report what was tested and what was not exercised in a real window.
- [ ] **Step 6:** Commit the addon, spec, and plan together only if the user asks for a commit.
