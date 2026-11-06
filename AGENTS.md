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

Use the repository skill `.agents/skills/t3-addon-lifecycle/SKILL.md` for addon installation, withdrawal, and official T3 update coordination. AI evaluates feature necessity and compatibility; verified standalone installers perform application changes. This workflow does not add a runtime dependency to addons.

Every application mutation must have a durable external record before replacement: host and addon/source identity, recoverable originals, before/after file hashes, permission modes and symlink targets, added/changed/removed logical archive entries, and verification results. Record completion afterward. Legacy adoption must disclose missing historical evidence. Unfinished operations must be reconciled before another operation starts.

Before an official update, withdraw recorded addon changes and verify the official application. After updating, reassess each addon: superseded, compatible, adaptation required, or uncertain. Reinstall only verified compatible addons; report adaptations or uncertainty to the user before proceeding unless that development is already authorized. Do not silently lose addon-specific behavior, overwrite unexpected changes, or downgrade a host that may have migrated user data.

1. Identify the installed T3 version or commit and applied addons. Preserve existing work.
2. Inspect the target official release and verify each addon's integration points.
3. Apply compatible addons reproducibly. Repeating an operation must not duplicate code, records, or model turns.
4. Never silently skip an incompatible patch or guess a new insertion point. Report and fix compatibility at the addon level.
5. Run appropriate checks and any necessary build before recording compatibility with a new release.

Updates are not guaranteed to be automatic. The goal is to keep adaptation limited to small integration points while preserving feature code.

## Installation and verification

- Distinguish official T3 files, addon source, generated output, and machine-local state.
- Installation tools must check the target version and required files, and reject unsupported states with a clear error.
- Preserve a recoverable original application before replacing it. Verify the prepared application's integrity before installation.
- Removal must undo only the addon's changes and must not overwrite unrelated work or an intervening official update.
- Run checks relevant to the change. State what was tested and what remains unverified.
- Do not claim external loading support unless it has been verified. Explain when an addon requires a modified application build.
- Preserve applicable upstream license and copyright notices when copying or distributing T3-derived material.

## Language and privacy

- Write all project instructions, interfaces, comments, documentation, fixtures, and user-facing messages in English. Unicode test data may use explicit escape sequences.
- Never store personal names, account or device identities, personal absolute paths, API keys, passwords, cookies, tokens, private keys, credentials, or private conversation data in this project.
- Store machine-local backups, installation receipts, staged applications, test environments, logs, screenshots, authentication state, and reference checkouts outside the project.
- Construct local paths at runtime with platform or home-directory APIs. Source files and documentation may use generic application paths and placeholders, never a real user's home path.
- Model Council uses an external OS application-support directory by default. Keep restore and update support functional when moving local state.
- Keep dependencies, bytecode, local environment files, databases, logs, and credentials out of version control. Ignoring a private file is not a substitute for keeping private state outside this project.
- Before preparing the project for Git or sharing, inspect all remaining files, including hidden files, for personal data and secrets. Report findings without exposing secret values.

## Scope

This document defines the project's direction. It does not itself authorize downloading T3, modifying an installed application, starting model runs, or creating a Git repository. Follow the user's current request and existing session authorization.
