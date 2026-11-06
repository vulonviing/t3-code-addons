# T3 Code Addons

Independent modular addons for T3 Code. Keep custom features separate from upstream T3 development, with explicit compatibility checks and reversible installation.

Unofficial, version-specific extensions; not affiliated with T3 Tools.

## Addons

- **[Model Council](addons/model-council/README.md)** — Independent opinions from 2–5 models, peer review, per-model thinking effort, and one final answer in the current chat.

## Library layout

```text
t3-code-addons/
  AGENTS.md
  README.md
  addons/
    model-council/
      README.md
      addon.json
      src/
      scripts/
      test/
```

Each addon has its own folder, English interface and README, manifest, source code, tests, and installation tools. Start with that addon's README. No addon should need another addon's files to install or run.

Compatibility is checked per addon. Updating T3 does not automatically make an addon compatible with the new release. Keep local application backups and receipts in the external application-support directory until you have removed or migrated the addon.

## AI-assisted update lifecycle

The repository skill [t3-addon-lifecycle](.agents/skills/t3-addon-lifecycle/SKILL.md) coordinates installation records, withdrawal before official updates, and reassessment afterward. It is discoverable as a project skill in Codex. Ask the agent to use it when updating T3 or managing addons.

The agent checks whether official T3 now covers each addon's behavior and whether still-needed addons work with the exact new release. Verified compatible addons are reinstalled; adaptations and uncertain cases are reported before proceeding. Official T3 remains usable while an addon needs work. This is an AI workflow with verified installation tools, not a promise that every release can be adapted automatically.

Every application replacement keeps recoverable bundles and records intended/completed file changes outside this repository. Model Council's standalone installer includes a transaction journal and `recover` command for interrupted swaps. A workflow session also records pending restart or user-performed update steps, so another turn can resume from observed state.

Keep reference checkouts, test environments, logs, screenshots, credentials, application backups, and installation receipts outside this project. The source library must contain no personal identities, personal absolute paths, private chat data, or secrets. See each addon’s README for its external state location.
