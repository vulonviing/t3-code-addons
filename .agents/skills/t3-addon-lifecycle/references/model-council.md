# Model Council adapter

Resolve `addons/model-council` relative to the current library. A standalone copy uses its own directory. No sibling or root code is required by its installer.

Commands from the addon directory:

```sh
python3 scripts/install.py check
python3 scripts/install.py restore
python3 scripts/install.py recover
python3 scripts/install.py apply
python3 scripts/install.py update
```

`update` updates the addon on its supported host; it does not update T3. `check` validates an existing recorded installation even if the working source has since changed. Legacy receipts require a reproducible reconstruction from the signed original and matching current source; if that fails, inspect instead of force-adopting.

The state directory is the documented external T3 Adds state root plus `model-council`. It contains `backups/model-council-install.json`, recovery bundles, and `transactions/`. A `transactions/pending.json` blocks new mutations until `recover` reconciles exact inventories. Recovery does not rerun model turns or touch conversation data.

To install a newer extracted official release after withdrawal:

```sh
python3 scripts/install.py install-official --candidate "/external/staging/T3 Code (Beta).app"
```

This checks strict bundle signatures, matching nonempty distributor team, bundle ID, and an increasing stable numeric version. It records and retains the replaced app. The candidate is consumed by an atomic rename; extract it outside the repo on the application volume. This command does not assert addon compatibility and does not restart T3.

For addon installation, the receipt records host version/commit, addon manifest/source hashes, full original/installed file inventories, and logical ASAR changes. Staged addon apps have a preparation record and are rejected if source, original, or staged contents changed. A legacy adoption is explicitly marked as retrospective. Inventories cover file bytes, permission modes and symlinks; they do not cover ACLs or extended attributes. macOS `ditto` preserves the application copy and strict code signing is checked independently.

Tests from the library root:

```sh
npm test
python3 addons/model-council/scripts/test_lifecycle.py
```

No paid provider runs are needed. Evaluate feature parity and the host adapter independently of these installer tests. Current compatibility is whatever the addon manifest and verified compatibility files actually say; never assume the next T3 version is supported.
