---
name: t3-addon-lifecycle
description: Manage T3 Adds installation records, withdraw addons before official T3 updates, and reassess whether addons are still needed and compatible before reinstalling them. Use for addon installation, removal, and T3 update coordination in this library.
---

# T3 Addon Lifecycle

AI owns feature comparison and compatibility analysis. Verified installers own application changes. Read the repository AGENTS.md and each affected addon's manifest, README, installer, and receipt before acting. Addons remain independently installable; this skill coordinates them without becoming a runtime dependency.

## Authorization and state

Use the current request and existing session authorization. A request to perform the lifecycle permits its routine steps; do not ask again at every transition. A request for advice does not authorize application changes. Never start paid model runs for validation without authorization.

Resolve machine-local state using the platform application-support directory or the documented T3_ADDS_STATE_DIR override. Keep backups, receipts, extracted releases, reference checkouts, test environments, and update-session records outside the repository. Never embed a personal path or conversation in source or evidence committed to Git.

Before the first change, atomically write `lifecycle/active.json` under that external state root, using the session format in [references/session.md](references/session.md). Persist intended actions before executing them, then record observed outcomes. Resume an existing session instead of assuming a clean start. If its application or receipts changed unexpectedly, inspect and stop before replacement. Do not silently discard an unfinished session.

## Installation contract

Every install, addon update, withdrawal, and host replacement must record its exact host identity, addon/source identity where applicable, before/after file inventories, added/changed/removed logical archive entries, recoverable original, verification results, and outcome. Hash file contents and record modes and symlink targets. Record intent durably before replacing application files. Do not represent a retrospective adoption as a complete historical record.

Use each addon's standalone installer. Inspect its actual commands; do not invent a common plugin API. For Model Council, see [references/model-council.md](references/model-council.md). If an installer cannot meet this contract, improve and test it before installation. Do not bypass a failed hash, version, signature, or compatibility check.

## Phase 1: withdraw and update official T3

1. Inventory the target application and all applied addons, including external receipts and integration markers. A missing or contradictory receipt is an inspection problem, not permission to overwrite. Record source versions so the intended addon set survives withdrawal.
2. Preserve active work. Distinguish a running old process from the app installed on disk. Do not terminate this agent's host just to finish automation. A verified bundle can be prepared or replaced on disk, but clearly hand off restart and verify the running version afterward.
3. Check whether addons overlap. Independent whole-bundle backups must not be restored sequentially onto a multiply modified app. If the installed combination has no verified composition/reversal plan, report that limitation and stop withdrawal; prepare and test such a plan first.
4. Withdraw recorded changes with verified recovery copies. Validate the restored official signature and identity. Preserve addon data and chat history. Record `withdrawn` only after observing success.
5. Update through the official updater or a verified official release. A cached ZIP is a candidate, not proof of authenticity. Validate the extracted app's signature, distributor identity against the signed original, bundle identity, and newer version. Keep the previous app recoverable. Record failures without reapplying addons to an unknown intermediate state.
6. If the user performs the update, leave the session at `awaiting-official-update` and give the exact next action. On resumption, inspect the installed app and verify its new identity. Never infer update success from a download or button click. Track disk installation and running-version confirmation separately.

## Phase 2: reassess addons

For each previously installed addon, inspect official release notes and the relevant new host implementation. Prefer a local official reference checkout/release artifact; otherwise consult primary upstream sources. Feature names alone do not establish parity. Compare the actual user behavior, limitations, settings, and persistence needs.

Record one outcome with evidence:

- `superseded`: Official T3 covers the required behavior sufficiently. Leave the addon withdrawn and tell the user what replaces it. Preserve its data; do not silently migrate or delete it. Ask only if meaningful behavior would be lost and the preference is unclear.
- `compatible`: Still needed; existing source passes integration and behavior checks against this exact host. Run relevant tests and prepare/verify a staged application, then reinstall under the user's lifecycle authorization. Record a fresh receipt and the new official baseline.
- `adaptation-required`: Still needed, but source or adapter changes are necessary. Explain the required changes and return to the user before developing the adaptation, unless already explicitly authorized. Leave official T3 usable.
- `uncertain`: Available evidence cannot establish necessity or compatibility. Explain the gap and return to the user; do not install speculatively.

A version guard rejecting a new build alone establishes that installation is unsupported, not that the feature is obsolete or that its code needs changing. Inspect the integration first. Never fix compatibility merely by changing a version string or trusting an AI assertion. Add a verified compatibility record only after appropriate checks pass. If the installer must change to support a new build, that is an adaptation to report.

Do not downgrade T3 automatically when an addon fails: the new host may have migrated user data. Recover a failed application swap using its journal; leave a verified official new release available when addon installation cannot finish.

## Completion

Archive completed sessions and keep original/previous bundle recovery copies outside the project. Report installed and running T3 versions separately when they differ, addons reinstalled/withdrawn, reasons and evidence for blocked adaptations, checks actually run, and any user restart/update action still required. Do not mark the workflow complete while a restart, update, or addon decision is pending.
