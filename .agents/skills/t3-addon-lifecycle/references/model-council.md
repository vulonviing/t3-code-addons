# Model Council

Whole-bundle addon: it saves the signed original app and restores it to withdraw. Run from `addons/model-council`.

```sh
python3 scripts/install.py check | setup-signing | stage | apply | update | restore | recover
python3 scripts/install.py install-official --candidate "/external/staging/T3 Code (Beta).app"
```

- `restore` withdraws it (put the original back). Withdraw overlays before it; apply it before overlays.
- `install-official` installs an official release while Model Council is withdrawn. It checks the signature and bundle ID, and compares the candidate's distributor team with the live app's team (if distributor-signed) or else with recorded teams (earlier install-official transactions, verified original backups). It always refuses downgrades; the same version is allowed only over a locally signed (overlay-signed) app, while a distributor-signed app needs a strictly newer version. It keeps the replaced app, and does not restart T3. `update_all.py --candidate` calls it (a .zip is extracted to external staging first).
- A `transactions/pending.json` blocks new changes until `recover`.
- State: `<state root>/model-council/` with `backups/model-council-install.json`, recovery bundles, and `transactions/`.
- If T3 was updated outside this flow, `restore` refuses; `update_all.py` archives the stale receipt (external, not deleted) and reapplies.

Tests: `npm test` and `python3 addons/model-council/scripts/test_lifecycle.py`. No paid model runs.
