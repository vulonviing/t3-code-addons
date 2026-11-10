# Orchestrator addon design

## Intent

Keep the agent the user talks to out of the dirty work. When Orchestrator is on, that agent never writes code or changes anything. It sends subagents to gather real context, plans from what they return, splits the work, sends other subagents to do each part, and sends independent subagents to check the results. Its own context stays small, so it keeps remembering the whole picture and stays sharp.

## Goals

- A composer button next to Model Council: **Orchestrator**. Off by default, green when on. State is per chat.
- Turning it on makes the chat's current agent a coordinator for the rest of that chat. Turning it off ends that.
- Right-click opens a menu that chooses the default model for subagents. The main agent always stays on the chat's selected model.
- The user can override per task in plain words ("use model X for this one"); the coordinator follows that over the default.
- Subagents are T3's existing subagents, not a new mechanism (see Verified facts).

## Non-goals

- No hard tool lockout. The rules are instructions, not a sandbox. The README says so.
- No change to T3 server or client code, no composer interception, no patched functions.
- No new subagent runtime and no custom thread creation. The coordinator uses the tools it already has.

## Anti-goals

- A coordinator that edits files, runs implementation commands, or pastes large subagent output into its own context.
- A button that looks active while the chat is not in coordinator mode.
- Silent loss of the setting after a reload.

## Verified facts (T3 0.1.7, commit 322f6544dfad)

- T3's server injects orchestration instructions into every session that has the T3 MCP tools: Claude via the appended system prompt, Codex via developer instructions, other harnesses as a prompt prefix.
- Subagents come from two paths. The provider-native one (Claude `Agent`, Codex `spawn_agent`) serves the same provider. The T3 MCP `delegate_task` tool serves another provider or model through `target: {providerInstanceId, model}`. Both appear in the UI as subagents; delegated ones open a child thread.
- There is no per-thread or per-turn instruction channel from the client. Claude's `append-system-prompt-file` is provider-wide.
- The client command `message.dispatch` accepts `dispatchMode` of `start_immediately` or `queue_after_active`, and Model Council already uses it to post into the user's chat.

## Design

**Activation by message.** The addon posts one `message.dispatch` turn into the chat with the coordinator rules, using the chat's current model selection (so the main agent stays on the selected model). If the chat is busy it uses `queue_after_active`. The message begins with a visible marker so the user can recognise it. Deactivation posts a short "coordinator mode ended" turn the same way.

**Rules text** (English, versioned in the addon): never edit files, run implementation commands, commit, or install; delegate everything; start with parallel context-gathering subagents that return short reports with evidence; plan from those reports; split the plan into independent parts; send each part to a subagent; send separate checking subagents for each result; request summaries only and keep own context small; report decisions, results, and open risks to the user; follow an explicit per-task model request over the default.

**Default subagent model.** The right-click menu lists the enabled provider instances and their non-legacy models from the host. The choice is stored globally and written into the rules as: use `delegate_task` with `target {providerInstanceId, model}` for this model, or the native tool's model argument when the provider matches. Changing it while on posts a one-line update turn. Empty means "no default": the coordinator picks, as T3 normally would.

**Button.** Attached beside the composer's existing controls without inserting into T3-owned React containers, the same way Model Council does. Click toggles. A busy-queued activation shows "Starting…" until the run is accepted.

**State.** Per-chat on/off and the global default model are in `localStorage`, wrapped in try/catch, keyed by environment and thread. The button's on state is derived from stored state plus whether the activation message exists in the thread projection, so it cannot claim "on" for a chat that never received the rules.

**Reminder.** Context dilution is the main weakness of message-based rules. The menu offers **Remind now**, which re-posts a short reminder. Automatic per-message reminders need composer interception, which AGENTS.md forbids; they are out of scope unless a verified, non-patching send hook is found.

**Overlay packaging.** `addons/orchestrator/` follows the overlay layout (`addon.json`, `compatibility.json`, `src/`, `scripts/`, `test/`, `README.md`) with its own copy of the overlay installer. It adds `assets/orchestrator/` and one marked `<script>` entry, is independent of every other addon, and installs, updates, and removes by itself.

## Constraints

- English everywhere; no personal paths or identities.
- Zero idle cost: no polling, mutation observer only on the composer footer, event-driven redraws.
- Host imports pinned by sha256 in `compatibility.json`; the adapter reuses only the exports already verified for the other overlays plus `message.dispatch`.

## Left to the builder

Exact menu styling, the rules wording within the listed points, and how to detect the activation message in the projection (marker text versus message id).

## Not exercised until installed

Real-window behavior, and whether a given model follows the rules over a long chat, cannot be proven by tests. The README must say what was and was not run.

## v0.2: frugal delegation

Observed: one task opened about 15 subagents, several on the largest model, and used about 30% of a usage limit. Causes were the rules (parallel scouts, one subagent per part, a separate checker per result), subagents inheriting the chat model when the native tool got no model, and every subagent starting cold.

Changes, all in the rules text plus one menu section:

- Agent budget: small 1, medium 2-3, large at most 5, never more than 3 at once; ask before going over.
- Reuse: one subagent per role (scout, builder per area, ops for all git/test/build, reviewer) kept alive with follow-up messages; the native tool is preferred because it can be continued.
- Replies: `DONE` / `NEEDS_INPUT` / `BLOCKED` plus at most 5 lines; briefs carry goal, file paths, and done condition only.
- Review in proportion to risk; the reviewer reads only the diff; at most 2 fix-and-review rounds.
- The coordinator may run tiny read-only checks itself and shows its plan before medium and large work.
- No largest-tier model unless asked; the model is named on every call (an omitted model inherits the chat's); no default means a mid-tier model; Claude defaults pass the native alias (`sonnet`, `haiku`).
- Effort: **By task** (default), **Low**, or **Medium** from the right-click menu, stored globally like the default model.
- `scripts/measure_session.py` reports spawns by model and tokens for before/after comparison.

Still instructions, not a sandbox. Not exercised: a real window and long-chat adherence.
