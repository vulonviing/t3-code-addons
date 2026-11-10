# Orchestrator

A T3 Adds addon that turns the agent you talk to into a team lead. With Orchestrator on, that agent never writes code or changes anything. It sends subagents to gather real context, plans from their reports, splits the work, sends other subagents to do each part, and sends independent subagents to check the results. Its own context stays small, so it keeps the whole picture instead of forgetting it.

This folder contains the source, manifest, tests, and installation tools. It works independently of every other addon and does not require a T3 source checkout.

![Orchestrator flow: you talk only to the coordinator, which sends subagents to gather context, plans and splits the work, has one reused builder subagent handle each area, has a reviewer check the diff, and then reports decisions, results, and open risks to you.](assets/orchestrator-flow.svg)

The coordinator is built to be frugal. It sizes the work first (small: 1 subagent, medium: 2-3, large: at most 5, never more than 3 at once), reuses one subagent per role with follow-up messages instead of respawning (scout, builder per area, an ops agent for all git, test, and build commands, reviewer), asks each for a `DONE` / `NEEDS_INPUT` / `BLOCKED` reply of at most 5 lines, and reviews in proportion to risk: none for trivial changes, one review of the whole diff for normal work, a separate review for risky parts, at most 2 fix-and-review rounds. It shows its plan before building medium and large work and ends with one line per subagent (role, model, rounds, result).

Subagents use the default subagent model from the right-click menu, a model you request for a single task, or a mid-tier model (for Claude, Sonnet; Haiku for search and git) when **No default** is set. They never use the largest tier (Opus) unless you ask. The coordinator itself stays on the chat's selected model.

## Requirements

- macOS with **T3 Code Beta 0.1.7**, source commit **`322f6544dfad`**.
- Python 3 and the macOS `ditto`, `codesign`, and `security` commands for installation.
- Node.js 20+ for the tests.

This is a local application modification, not an official T3 plugin API. The installer checks the exact build and the hashes of the host files it imports, and refuses unsupported builds.

## Install

```sh
cd addons/orchestrator
python3 scripts/install.py check
python3 scripts/install.py apply
```

If the installed application is already signed by a T3 Adds local certificate (for example after installing Model Council), `apply` re-signs with that same certificate. On an unmodified official app, run `python3 scripts/install.py setup-signing` once first, as described in the Model Council README. Quit and reopen T3 Code afterward.

## Use

- The **Orchestrator** button sits in the composer next to **Model Council**. It is off by default in every chat.
- Click it to turn it on. It shows **Starting…** until T3 accepts the rules, then turns green. If the chat is busy, the rules are queued behind the current work. Click again to end coordinator mode.
- Right-click (or press the context-menu key) for options:
  - **Default subagent model**: the model subagents use unless told otherwise. **No default** means a mid-tier model.
  - **Subagent effort**: **By task** (recommended) uses low for search, git, and fully specified edits and medium for code with logic and review. **Low** or **Medium** applies that level to every subagent.
  - **Remind now**: re-sends a short reminder of the rules.
- The chat's own agent always stays on the model selected in the chat.
- To use a specific model for one task, say so in plain words ("use model X for this one"). The coordinator is told to follow an explicit request over the default.

## How it works

Turning it on posts one message into the chat, starting with `[T3 Adds · Orchestrator]`, that states the coordinator rules. Turning it off, changing the default model or effort, or choosing Remind posts a short message the same way. Subagents are T3's existing subagents: the provider's native tool (Claude `Agent`, Codex `spawn_agent`) for the same provider, and T3's `delegate_task` for another provider or model. Nothing in T3 is patched.

The on/off state per chat, the default model, and the effort are kept in the browser profile's local storage. If storage is blocked, they last for the session.

## Limitations

- The rules are instructions, not a sandbox. T3's permissions remain authoritative, and an agent that ignores the rules can still change files. The button turning green means the rules were delivered, not that they are enforced.
- In very long chats the rules can fade. Use **Remind now**. Automatic per-message reminders would need hooking T3's composer, which this addon does not do.
- The rule messages are visible in the chat and use the chat's normal turn, so they use a little model usage.
- The agent budget (3 at once, 5 per task), reuse, reply format, and the Opus ban are instructions too, so a model can overstep them. Effort is passed on only where the subagent tool supports it.
- Models you pick must be enabled in T3. A saved default that is no longer available is ignored.

## Update and remove

```sh
python3 scripts/install.py update    # after changing source files in this folder
python3 scripts/install.py remove    # withdraw this addon only
python3 scripts/install.py recover   # reconcile an interrupted operation
python3 scripts/install.py forget    # archive a stale receipt after an official T3 update
```

Removal deletes only what this addon added. Model Council's `update` and `restore` refuse while an overlay is installed; withdraw overlays first.

## Test

```sh
npm test
```

Covers the rules text (budget, reuse, reply format, review, effort, native model aliases), persisted state (including blocked storage), the controller (queueing when busy, permission and failure handling, unavailable defaults), model options and routing, and the installer against a synthetic app. `scripts/verify_host.mjs` imports the real official bundles in an isolated Chromium and checks the adapter; see Theme Toggle's README for running it from an external test copy.

`scripts/measure_session.py <session.jsonl>` counts a Claude Code session's subagent spawns by model, follow-up messages, and tokens (it reads only; nothing is written), so you can compare token use before and after.

Not exercised: a real T3 window, a real model following the rules, and the button/menu layout in the live composer.
