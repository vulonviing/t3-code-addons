# Overlay addons: Theme Toggle, Thread Details

Resolve `addons/<id>` relative to the current library; a standalone copy uses its own directory. Each installer is self-contained and identical in behavior; the addon's `addon.json` supplies its identity.

Commands from the addon directory:

```sh
python3 scripts/install.py check      # verified state: compatible and absent, or installed and intact
python3 scripts/install.py apply
python3 scripts/install.py update     # after the addon's own source changed
python3 scripts/install.py remove     # withdraw this addon only
python3 scripts/install.py recover
python3 scripts/install.py forget     # archive a stale receipt once an official update removed the addon
```

An overlay layers onto whatever app is installed. It adds only `assets/<id>/` files and one marked `<script>` line in the client `index.html`, checks that nothing else in the application archive changed, re-signs with the certificate already pinned in the installed app (or its own `setup-signing` identity on an unmodified official app), and swaps the app atomically with a transaction journal. `remove` deletes only that addon's recorded entries, refuses when they were changed, and never restores a whole-application backup. Any order of apply and remove is safe and was rehearsed on a scratch copy with Model Council present.

State per addon: `<state root>/<id>/installation.json`, `transactions/`, and `backups/<operation>/` holding the previous app. A `transactions/pending.json` blocks that addon's next mutation until `recover`. One lock (`app-mutation.lock` in the state root) serializes all overlay installers.

## Interaction with Model Council and official updates

- Model Council's `update` and `restore` refuse while an overlay is installed, because the installed archive no longer matches its receipt. Withdraw every overlay first, run the Model Council operation, then reinstall the overlays.
- Phase 1 of the lifecycle: withdraw overlays with `remove` (record each), then Model Council, then update T3.
- Phase 2: an overlay is `compatible` only if its `check` passes against the new host and `verify_host.mjs` passes against the new official client assets (`scripts/extract_client.py`). Its pinned host modules (`compatibility.json`) are hashed chunk names, so a rebuilt T3 normally means `adaptation-required`: update the adapter's import names and the hashes, then re-verify.
- If an official update replaced the app while a receipt remains, `check` fails the entry check; confirm the addon is absent, then run `forget`.
