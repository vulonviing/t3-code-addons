---
name: t3-addon-lifecycle
description: Update T3 Code with its T3 Adds addons. Unplug every addon, update T3, plug them back in, report which attached. Use for T3 updates and for installing or removing addons in this library.
---

# T3 Addon Lifecycle

Think of an engine test: unplug the wires (withdraw all addons), update the engine (T3 Code), plug the wires back in, check they fit. If they fit, done. Compatibility means "does the addon attach?" There are no version gates to maintain and no reassessment ceremony.

## Update T3 (the normal case)

```sh
python3 .agents/skills/t3-addon-lifecycle/scripts/update_all.py [--candidate "/path/to/T3 Code (Beta).app or .zip"]
```

One run does everything and prints one table (attached or failed, with a short reason):

1. Lists installed addons from their receipts and records the wanted set outside the repo.
2. Withdraws each one with its own installer: overlays `remove`, Model Council `restore` last.
3. Installs the official update when `--candidate` is given, using the existing verified mechanics (signature and identity checks, recoverable previous app). If you updated through T3's own updater, omit it; stale receipts are archived automatically.
4. Applies every wanted addon with its own `apply` (Model Council first), then runs each `check`.
5. Sets up persistent signing if missing, once, with no prompt (reuses one identity for all addons).
6. Retries any failed apply or check once (recover, withdraw, apply again); on a hard failure it prints a short reason and the exact next command, and leaves the other addons attached. The table comes from real `check` runs after everything is plugged in.
7. Restarts T3 once through a detached job (`--no-restart` to skip).
8. When everything attached and the working tree is dirty, runs `scripts/publish.py` (`--no-publish` to skip). A scan or push problem is reported and never fails the update.

A failed addon is reported and left withdrawn; the others continue and the run finishes. Re-run the same command after an interruption or to retry failures (the wanted set is kept in `<state root>/lifecycle/wanted.json`). `--drop ID` stops wanting an addon. Exit code 1 means at least one addon is not attached.

When an addon fails to attach, tell the user in one line. Fix it at the addon level only if asked; never edit a version string just to make it pass.

## When the user says they updated T3

1. Run `update_all.py` (add `--candidate` only if they gave you a release file). One command, no prompts.
2. If any addon is not attached, fix it now without asking: adapt discovery in that addon, run its tests, rerun `update_all.py`. Repeat until every addon is attached.
3. Publish: `update_all.py` does it when all attached; otherwise run `python3 .agents/skills/t3-addon-lifecycle/scripts/publish.py --footer "<attribution line from your instructions, if any>"`. It privacy-scans, runs addon tests, commits in logical groups on `update-<date>`, and pushes to the existing remote (never force, never creates a repository). Stop and tell the user only if the scan, tests, or push block it.
4. Report in a few lines: the table, what you fixed, what was published.

Nothing is final until the table shows every addon attached and each addon's own `check` passes.

## Rules that stay

- The previous official app is kept recoverable before any replacement; do not downgrade T3 automatically, since the new version may have migrated user data.
- Removal undoes only that addon's own changes and refuses if they were altered.
- Resolve the state root with `T3_ADDS_STATE_DIR` or the platform application-support directory. Backups, receipts, staging, and logs stay outside the repository; no personal data or paths in the repo.
- CLI updates (Codex, Claude Code, Open Code) never need anything from the addons. Do not run this tool for them.
- Do not terminate the host running this agent; the restart is a detached job.

## Single addon commands

Each addon is independent. From its folder, `python3 scripts/install.py <check|setup-signing|apply|update|remove|recover|forget>`; Model Council uses `restore` instead of `remove`. Details: [references/overlay-addons.md](references/overlay-addons.md) and [references/model-council.md](references/model-council.md). `recover` finishes an interrupted swap; `update_all.py` calls it automatically when a step fails.

Tests (fakes and temp git repos only): `python3 -B .agents/skills/t3-addon-lifecycle/scripts/test_update_all.py` and `test_publish.py` in the same folder.
