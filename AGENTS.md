# T3 Code Addons — Purpose and working principles

## Motivation

This project stores modular features and customizations for T3 Code. Upstream T3 continues to evolve; our additions should be reusable on newer official releases without rewriting them from scratch.

T3 Adds is an independent customization layer, not a permanently divergent copy of T3. Keep addon code, small integration changes, compatibility information, and reproducible installation instructions together.

## Addon structure

- Put each independent addon in `addons/<addon-id>/`.
- Every addon must be independently installable, updatable, and removable.
- Include an English `README.md`, `addon.json`, source files, relevant tests, and any required installation tools in the addon folder.
- Addons must not depend on files from a sibling addon or the library root.
- Keep feature logic in the addon and minimize changes to T3 itself.
- Prefer verified extension points. Do not assume a plugin API or capability exists without checking it.
- Record necessary host changes as an integration patch or a reproducible installation step. Never make untracked manual changes to an installed application.
- Avoid unnecessary dependencies and speculative frameworks. Build shared infrastructure only when real addons require it.

A typical addon may contain:

- `addon.json`: ID, name, version, dependencies, and verified T3 version or commit.
- `src/`: Feature code and a version-specific host adapter when needed.
- `integration.patch`: Small host integration changes, when applicable.
- `scripts/`: Standalone install, update, restore, and verification tools.
- `test/`: Meaningful behavior and integration tests.
- `README.md`: Purpose, setup, use, removal, compatibility, validation, and limitations.

Do not create empty files merely to match this layout.

## Upstream updates

Update T3 with `python3 .agents/skills/t3-addon-lifecycle/scripts/update_all.py` (see `.agents/skills/t3-addon-lifecycle/SKILL.md`). It unplugs every addon, updates T3, plugs the addons back in, runs each `check`, prints which attached, and restarts T3 once. Compatibility means "does the addon attach?": no version pins, no reassessment ceremony. A failed addon is retried once, then reported with the exact next command and left withdrawn; the others stay attached. When everything attached, the result is privacy-scanned, committed on `update-<date>`, and pushed (`scripts/publish.py`). Nothing is final until every addon's own `check` passes. Do not change a version string just to make an addon pass. CLI updates (Codex, Claude Code, Open Code) never involve addons.

## Installation and verification

- Distinguish official T3 files, addon source, generated output, and machine-local state.
- Keep a recoverable copy of the original app before replacing it, and verify the prepared app before installing. Never downgrade T3 automatically.
- Removal undoes only the addon's own changes and must not overwrite unrelated work or an official update.
- Repeating an operation must not duplicate code, records, or model turns.
- Run checks relevant to the change and say what was and was not tested.
- Do not claim external loading support unless verified; addons need a modified app build.
- Preserve upstream license and copyright notices when copying T3-derived material.

## Language and privacy

- Write all project instructions, interfaces, comments, documentation, fixtures, and user-facing messages in English. Unicode test data may use explicit escape sequences.
- Never store personal names, account or device identities, personal absolute paths, API keys, passwords, cookies, tokens, private keys, credentials, or private conversation data in this project.
- Store machine-local backups, installation receipts, staged applications, test environments, logs, screenshots, authentication state, and reference checkouts outside the project.
- Construct local paths at runtime with platform or home-directory APIs. Source files and documentation may use generic application paths and placeholders, never a real user's home path.
- Model Council uses an external OS application-support directory by default. Keep restore and update support functional when moving local state.
- Keep dependencies, bytecode, local environment files, databases, logs, and credentials out of version control. Ignoring a private file is not a substitute for keeping private state outside this project.
- Before preparing the project for Git or sharing, inspect all remaining files, including hidden files, for personal data and secrets. Report findings without exposing secret values.

## Overlay addons (Theme Toggle, Thread Details, Orchestrator, Codex Dictation)

Small interface addons that add files and one `<script>` entry to the installed app. Use each addon's own `scripts/install.py` (`check`, `apply`, `update`, `remove`, `recover`, `forget`); they are independent of each other and of Model Council. Details: `.agents/skills/t3-addon-lifecycle/references/overlay-addons.md`.

- Never insert elements into DOM that T3's React components own, and never patch T3's functions. Attach beside T3's elements and read their position.
- Keep idle cost near zero: no polling, no work while the addon's UI is closed or the window is in the background, use browser events instead of timers.
- Develop against a mock page, not the installed app. Install into the real app only after it looks right, and say what was not exercised in a real window.

## Scope

This document defines the project's direction. It does not itself authorize downloading T3, modifying an installed application, starting model runs, or creating a Git repository. Follow the user's current request and existing session authorization.
