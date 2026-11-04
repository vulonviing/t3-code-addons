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

Keep reference checkouts, test environments, logs, screenshots, credentials, application backups, and installation receipts outside this project. The source library must contain no personal identities, personal absolute paths, private chat data, or secrets. See each addon’s README for its external state location.
