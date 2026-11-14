# Overlay addons: Theme Toggle, Thread Details, Orchestrator, Codex Dictation

Run from `addons/<id>`. Each installer is self-contained.

```sh
python3 scripts/install.py check          # attached and intact, or absent
python3 scripts/install.py setup-signing  # once; update_all.py does this automatically
python3 scripts/install.py apply
python3 scripts/install.py update         # after the addon's own source changed
python3 scripts/install.py remove         # withdraw this addon only
python3 scripts/install.py recover        # finish an interrupted swap
python3 scripts/install.py forget         # archive a stale receipt after an official update replaced the app
```

An overlay adds only its `assets/<id>/` files and one marked `<script>` line, re-signs with the certificate already pinned in the app, and swaps the app atomically with a journal. `remove` deletes only its recorded entries and never restores a whole-app backup. Addons apply and remove in any order. State: `<state root>/<id>/installation.json`, `transactions/`, `backups/`. One lock serializes all installers.

Model Council `update` and `restore` refuse while overlays are installed, so withdraw overlays first. `update_all.py` handles that ordering.

If an overlay no longer attaches to a rebuilt T3, `apply` or `check` fails with a reason. That failure is the whole compatibility signal; extract the new client with `scripts/extract_client.py` and fix the adapter only when the user wants that addon repaired.
