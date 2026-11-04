# Model Council

A T3 Adds addon that gathers independent opinions from 2–5 models, runs one round of peer review, and presents one final answer through the model selected in your current T3 chat.

This folder contains the source, manifest, tests, and installation tools. It works independently of the rest of the addon library and does not require a T3 source checkout.

## Requirements

- macOS with **T3 Code Beta 0.1.6**, source commit **`2359643cffa6`**.
- Python 3 and the macOS `ditto` and `codesign` commands for installation.
- Node.js 20+ and npm for optional automated tests.
- At least two usable model selections in T3. Provider subscriptions and usage limits still apply.

This is a local application modification, not an official T3 plugin API. The installer checks the exact build and host-file hashes. It refuses unsupported builds; a newer T3 release requires a compatibility review first.

## Install

From the T3 Adds library root:

```sh
cd addons/model-council
python3 scripts/install.py check
python3 scripts/install.py apply
```

If you copied the addon elsewhere, open that folder directly instead of using the `cd` command above. Everything else works the same way.

The default target is `/Applications/T3 Code (Beta).app`. For another installation, pass `--app` to each command:

```sh
python3 scripts/install.py check --app "/path/to/T3 Code (Beta).app"
python3 scripts/install.py apply --app "/path/to/T3 Code (Beta).app"
```

`apply` builds and verifies a separate application copy, saves the complete original app in the external local-state directory, and installs the prepared copy. It does not modify the conversation database or quit the running app. **Quit and reopen T3 Code afterward.**

To prepare a copy before installing, run `python3 scripts/install.py stage`, then `python3 scripts/install.py apply`.

### Local signing

The modified app uses an ad-hoc local signature. Apple-issued distributor identity and keychain-group entitlements cannot be preserved with that signature, so T3's distributor-bound Touch ID/passkey integration may be affected. Provider credentials are not rewritten. The complete original signed app is retained for restoration.

## Use

1. Open an existing chat and click **Model Council** next to the attachment button inside the composer.
2. Enter a question. Select models from the provider lists and click **Add**.
3. Choose each member's **Thinking effort**, where supported. **Default** leaves that setting to T3/the provider.
4. Click **Start council**.
5. Inspect independent opinions and peer reviews in the council card, or open each member's native T3 chat.

Each member uses two turns: an independent opinion, then a review of all initial opinions. Member effort settings are preserved across both rounds. The model currently selected in the main chat produces the final answer using its existing model and effort settings.

The council preserves unresolved disagreements. Failed members are reported and are never silently replaced. At least two independent opinions and one completed peer review are required for a final answer.

Use **Stop** to stop members and, when applicable, the council's final-answer turn. If the main chat is busy, the council enters **Ready**; click **Send final answer to chat** when the other work finishes.

## Update the addon

After changing or replacing source files in this folder:

```sh
python3 scripts/install.py update
```

This rebuilds from the recorded original app, retains the original backup, saves the previous addon installation, and updates the receipt. Restart T3 afterward.

Keep the external local-state directory: it contains the original app and receipt needed for updates and restoration. Moving or copying the addon source folder does not move private machine state or break its backup references on the same machine.

If T3 itself has updated, the installer refuses to overwrite it. Review the new release and update the adapter and compatibility manifest before applying the addon again.

## Remove and restore

```sh
python3 scripts/install.py restore
```

Restart T3 afterward. Restoration puts back the original signed app and refuses to overwrite an application that changed after injection. It does not delete council records or member conversations.

## Folder contents

```text
model-council/
  README.md              Installation and usage
  addon.json             Name, version, and supported T3 build
  compatibility.json     Host-file SHA-256 hashes
  integration.patch      Client entry-point change
  src/                   UI, protocol, controller, effort, storage, host adapter
  scripts/               Installer, ASAR utility, installer tests
  test/                  Automated tests
  package.json           Optional test dependencies and command shortcuts
  package-lock.json      Reproducible test dependency versions
  T3-Code-LICENSE         Upstream MIT notice
```

For sharing, copy the source and documentation while excluding installed `node_modules/` and generated files. No files from a sibling addon or the library root are required. Private runtime state must stay outside the source folder.

## Local state and privacy

Application backups, the installation receipt, and staged applications are stored outside the project. On macOS the default location is:

```text
$HOME/Library/Application Support/T3 Adds/model-council/
  backups/
  .cache/staged/
```

The home directory is resolved at runtime; no personal path is embedded in the addon. Set `T3_ADDS_STATE_DIR` to an external parent directory to use another location; the installer appends `model-council/`. Use the same setting for install, update, and restore commands.

Do not commit or share local receipts, application backups, test-server profiles, logs, browser authentication state, credentials, or private chat exports. Isolated integration tests must also use a data directory outside this project. Python bytecode generation is disabled by the installer and its test runner to avoid writing compiled files containing local source paths.

## Context and limitations

The starting conversation selection is frozen once and shared by all members. Its default budget is 16,000 UTF-8 bytes, prioritizing the original request and recent exchanges. Members receive a source-thread reference for retrieving omitted history. Attachments and private reasoning are not copied. Contributions above 24,000 bytes are shortened explicitly; the full output remains in the native member chat.

The frontend coordinates later rounds. Closing its window may leave an already-started native turn running; reopening T3 resumes remaining steps. Stable command IDs prevent resending accepted turns. Web Locks coordinate execution across windows. Council records live in the browser profile's IndexedDB and do not sync across devices.

Members run in the same project, branch, and workspace, in plan mode with advice-only instructions. These instructions are not an operating-system sandbox; T3's permissions remain authoritative. An opinion request does not authorize implementation work.

The UI applies to the local desktop app and the web frontend it serves. It does not modify the official mobile app or the independently hosted `app.t3.codes` frontend. Native member conversations remain regular T3 conversations.

## Test

From this folder:

```sh
npm ci
npm test
```

Tests cover context selection, common inputs, round order, effort forwarding, partial failure, cancellation, timeouts, resume idempotency, busy parent chats, durable storage, and ASAR rewriting. They do not call paid model APIs. The installer also verifies the prepared app's signature and ASAR integrity.

Previous live checks verified the native T3 UI/RPC path and final context delivery to Codex. The cross-provider live check was limited by the Claude account's usage cap; not every provider/model combination has been tested.
