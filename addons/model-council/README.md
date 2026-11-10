# Model Council

A T3 Adds addon that gathers independent opinions from 2–5 models, runs configurable peer-review rounds with individual early completion, and presents one final answer through the model selected in your current T3 chat.

This folder contains the source, manifest, tests, and installation tools. It works independently of the rest of the addon library and does not require a T3 source checkout.

![Model Council flow: independent opinions feed shared peer-review rounds, which repeat until members finish or the round limit is reached; the selected model then answers in the original chat.](assets/model-council-flow.svg)

Three members are shown; a council supports 2–5. Finishing a review does not imply agreement. The final answer preserves unresolved disagreements.

## Requirements

- macOS with **T3 Code Beta 0.1.7**, source commit **`322f6544dfad`**.
- Python 3 and the macOS `ditto` and `codesign` commands for installation.
- Node.js 20+ and npm for optional automated tests.
- At least two usable model selections in T3. Provider subscriptions and usage limits still apply.

This is a local application modification, not an official T3 plugin API. The installer checks the exact build and host-file hashes. It refuses unsupported builds; a newer T3 release requires a compatibility review first.

## Install

From the T3 Adds library root:

```sh
cd addons/model-council
python3 scripts/install.py check
python3 scripts/install.py setup-signing
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

Run `python3 scripts/install.py setup-signing` once on each Mac before staging or installing. This creates a unique self-signed code-signing certificate with the generic name **T3 Adds Local Code Signing**, imports its private key into your default user Keychain, and requests user-domain trust restricted to code signing. macOS may ask for local authentication; enter it only in the system dialog. No Apple Developer membership, provider subscription, online account, or network request is required. This is a local signing identity, not an Apple Developer ID or notarization.

The installer signs nested code inside out and pins each component's designated requirement to its bundle identifier and this certificate. Rebuilds keep that identity instead of binding permissions to an ad-hoc build hash. Missing, untrusted, or changed signing keys stop installation; there is no automatic ad-hoc fallback or key rotation. Keep the certificate and private key in Keychain, and keep the external signing configuration. Repeating setup reuses the recorded identity. The certificate lasts ten years; replacing it, moving to another Mac, returning to the official build, or changing the host's bundle identifiers can require fresh permission grants.

For an existing ad-hoc installation, run `setup-signing`, then `python3 scripts/install.py update`. Quit and reopen T3 afterward. macOS may require a one-time regrant of Accessibility, Screen Recording, or Automation because this migration changes the signing identity. Use System Settings to reauthorize only T3 if necessary; do not reset all applications' privacy permissions. Verify the affected features after two quit/reopen cycles and after a subsequent addon update. Signing checks establish identity stability; they cannot automatically grant or prove retention of TCC permissions.

Apple-issued distributor identity and keychain-group entitlements cannot be preserved with a local certificate, so T3's distributor-bound Touch ID/passkey integration may still be affected. Provider credentials are not rewritten. The complete original signed app is retained for restoration. See Apple's [code identity and privacy explanation](https://developer.apple.com/documentation/technotes/tn3127-inside-code-signing-requirements/) and [self-signed identity guidance](https://developer.apple.com/library/archive/technotes/tn2206/).

#### Sharing and privacy

Publish the installer and these instructions, never your generated identity or a locally signed application bundle. Each user generates their own key; do not distribute a shared private key. The public source contains no user certificate fingerprint, personal certificate subject, home-directory path, account identifier, or subscription credential. The generated certificate uses only the generic name above. It does not encode an Apple ID or device name. A certificate fingerprint could link signed builds if you share those builds; keep them local.

`signing/identity.json`, `signing/setup.json`, and the public certificate live under the external addon state directory, not in this repository. These local JSON records contain the certificate fingerprint and Keychain path. Temporary encrypted key/import files and their generated passwords are created in a private external directory and removed after setup; the persistent private key remains in Keychain. Do not commit receipts, signed bundles, certificates, Keychain exports, local signing files, or generated logs. Publishing this source does not itself provide access to subscriptions, credentials, or local folders.

If setup stops at a system authorization prompt, complete or cancel that prompt before retrying. An interrupted import is recorded in `signing/setup.json`; inspect the matching Keychain identity before changing that record. Never delete the setup journal to generate another key blindly. A missing private key cannot be recovered from the public certificate. Restoring the official app remains available independently of the signing configuration; restoration does not delete the Keychain identity or change global trust settings.

## Use

1. Open an existing chat, or a new-chat screen, and click **Model Council** next to the attachment button inside the composer.
2. Enter a question. Expand **Add models**, select models from the provider lists, and click **Add**. Selected models appear as separate cards under **Council members**.
3. Choose each member's thinking or reasoning level in its card, where supported. **Default** leaves that setting to T3/the provider.
4. Set **Maximum rounds** to a whole number of at least 2 (default: 2). The independent opinion counts as round 1; the final answer is separate.
5. Click **Start council**. On a new-chat screen the question is prefilled from the composer text, and Start first turns the draft into a real chat (a model must be chosen in the composer); the final answer then becomes that chat's first message, and there is no earlier history to share. The new-chat flow was tested only in a mock page; see Context and limitations.
6. Inspect independent opinions and peer reviews in the council card, or open each member's native T3 chat.

Each member gives an independent opinion, then reviews the initial opinions and the latest earlier position of every member. All participating models receive the same frozen packet for a round. Member effort settings are preserved across rounds. The limit is a maximum, not a required number of turns: for example, a limit of 5 can finish at round 3. The model currently selected in the main chat produces the final answer using its existing model and effort settings.

Each reviewer is instructed to stop participating when more discussion would not materially improve its recommendation, using an exact final control line: `{"councilStatus":"done"}`. A `continue` line or a missing/malformed signal keeps that member eligible until the limit. A finished member receives no more turns, while its last position remains visible to other members. Once all remaining members finish, or the maximum is reached, synthesis starts. Finishing does not imply agreement.

The council preserves unresolved disagreements. Failed members are reported and are never silently replaced. At least two independent opinions and one completed peer review are required for a final answer.

Use **Stop** to stop members and, when applicable, the council's final-answer turn. If the main chat is busy, the council enters **Ready**; click **Send final answer to chat** when the other work finishes.

After the final answer completes, the addon automatically settles the member chats through T3's native `thread.auto-settle` command. It also attempts cleanup after cancellation or failure. It preserves the chat history and does not settle the original chat. Active, reused, pinned, explicitly kept-active, or concurrently changed member chats are skipped and the council card reports the reason. Pending cleanup resumes after reopening; older completed councils are left unchanged.

## Update the addon

After changing or replacing source files in this folder:

```sh
python3 scripts/install.py update
```

This rebuilds from the recorded original app, retains the original backup, saves the previous addon installation, and updates the receipt. Restart T3 afterward.

Keep the external local-state directory: it contains the original app and receipt needed for updates and restoration. Moving or copying the addon source folder does not move private machine state or break its backup references on the same machine.

The installer records full original/installed bundle inventories (file hashes, modes, symlinks), logical ASAR changes, host identity, and addon source hashes. It writes transaction intent before replacing the application and keeps both recovery copies. Staged apps are tied to the original and source hashes. Legacy receipts are adopted only after reconstructing the current installation from its signed original; this verifies current state rather than claiming a complete historical audit. ACLs and extended attributes are not inventoried; application copies use macOS `ditto` and signatures are verified separately.

An unfinished operation blocks new installation operations. Reconcile it with:

```sh
python3 scripts/install.py recover
```

Recovery only accepts recorded bundle contents and refuses unexpected application changes. It does not modify chats or council records. All installer commands share an exclusive lock.

If T3 itself has updated, the installer refuses to overwrite it. Review the new release and update the adapter and compatibility manifest before applying the addon again.

## Remove and restore

```sh
python3 scripts/install.py restore
```

Restart T3 afterward. Restoration puts back the original signed app and refuses to overwrite an application that changed after injection. It does not delete council records or member conversations.

Restoration retains the signed original backup and the withdrawn application. Its transaction archives the installation receipt. After withdrawal, an extracted newer official app may be installed with `python3 scripts/install.py install-official --candidate "/external/staging/T3 Code (Beta).app"`. The candidate must have a valid signature, matching distributor team and bundle ID, and a newer stable numeric version. This records the host replacement, keeps the previous application, and leaves the addon withdrawn. Restart T3 and reassess compatibility before reinstalling; this command does not update the addon's compatibility metadata.

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
  signing/
```

The home directory is resolved at runtime; no personal path is embedded in the addon. Set `T3_ADDS_STATE_DIR` to an external parent directory to use another location; the installer appends `model-council/`. Use the same setting for install, update, and restore commands.

Do not commit or share local receipts, application backups, test-server profiles, logs, browser authentication state, credentials, or private chat exports. Isolated integration tests must also use a data directory outside this project. Python bytecode generation is disabled by the installer and its test runner to avoid writing compiled files containing local source paths.

## Context and limitations

The draft flow was exercised only in a mock page with a fake host, not in a real T3 window. Unverified: the redirect after the draft is finalized, the server's reaction to the thread creation (including an assumed deduplication of a repeated command ID on retry), whether the model picker stores the chosen model in the composer draft (otherwise "Pick a model first." appears), and the mobile composer footer. If starting fails after the chat was created, an error says so and you press Start again in the new chat.

New-chat support relies on T3's internal draft store (`getDraftSession`, `getComposerDraft`, `markDraftThreadPromoting`, `finalizePromotedDraftThread`), a contract pinned by the sha256 of the exact host file, not a public API. The promoted chat is not prepared as a new worktree.

The starting conversation selection is frozen once and shared by all members. Its default budget is 16,000 UTF-8 bytes, prioritizing the original request and recent exchanges. Members receive a source-thread reference for retrieving omitted history. Attachments and private reasoning are not copied. Contributions above 24,000 bytes are shortened explicitly; the full output remains in the native member chat.

All round responses remain in the local council record and member chats. Final-answer context contains the original opinions, latest reviews, and completion metadata to keep its size bounded regardless of the round limit; earlier reviews can be retrieved from member chats. There is no fixed upper limit beyond a safe integer, so large values can consume substantial model usage if members keep discussing.

The frontend coordinates later rounds. Closing its window may leave an already-started native turn running; reopening T3 resumes remaining steps. Stable per-round command IDs prevent resending accepted turns. In-progress records from the previous two-round format retain their limit and accepted message IDs. Web Locks coordinate execution across windows. Council records live in the browser profile's IndexedDB and do not sync across devices.

Members run in the same project, branch, and workspace, in T3's default interaction mode (not plan mode) with the source conversation's runtime mode, so they can use the terminal, web search, and browser automation to investigate. Their instructions make them read-only investigators: they must cite evidence and must not edit files, commit, install, submit forms, or otherwise change state. These instructions are not an operating-system sandbox; T3's permissions remain authoritative, and a member that ignores them can change the workspace. With an approval-requiring runtime mode, commands may wait for approval in a member thread nobody is watching until the response times out; start the council from a conversation whose runtime mode allows the research you want. Browser automation through AppleScript acts in the user's own Chrome profile and needs macOS Automation permission. An opinion request does not authorize implementation work.

The UI applies to the local desktop app and the web frontend it serves. It does not modify the official mobile app or the independently hosted `app.t3.codes` frontend. Native member conversations remain regular T3 conversations.

## Test

From this folder:

```sh
npm ci
npm test
```

Tests cover context selection, common inputs, custom round limits, individual early completion, frozen round packets, legacy records, settlement safeguards and cleanup recovery, round order, effort forwarding, partial failure, cancellation, timeouts, resume idempotency, busy parent chats, durable storage, ASAR rewriting, signing identity reuse, nested signing order, and rejection of missing signing identities. They do not call paid model APIs or modify Keychain. The installer also verifies the prepared app's signature, certificate requirements, and ASAR integrity.

Local macOS validation additionally signed two different compiled Mach-O builds under one identifier and verified that both satisfy the same certificate-pinned designated requirement despite different file hashes. This validates identity stability, not interactive permission retention. Accessibility, Screen Recording, and Automation still require manual verification after migration and relaunch.

The configurable-round and automatic-settlement upgrade is covered by simulated controller tests and inspection of the pinned host command schema and handler; it has not been exercised with paid model runs.

Previous live checks verified the native T3 UI/RPC path and final context delivery to Codex. The cross-provider live check was limited by the Claude account's usage cap; not every provider/model combination has been tested.

## T3 0.1.7 adaptation

Addon 0.4.0 targets official T3 0.1.7 / `322f6544dfad`. The host adapter uses the verified atom registry, thread detail/shell, provider configuration, scope, orchestration, and transcript exports from this exact application build. New-chat support was verified only against the real client's exports and in a mock page, not in a real window. The native multi-model sender starts separate background threads; it does not replace Council's peer-review rounds and final synthesis.

Reasoning controls also honor T3 0.1.7's explicit `role: "reasoning"` descriptor, including provider-specific option IDs, while preserving existing choices and excluding prompt-only levels.

Settlement snapshots remain ISO strings in durable council records. The adapter decodes them to native Effect DateTime values before invoking `thread.auto-settle`; passing persisted strings directly does not meet the native command schema. The controller also accepts native DateTime timestamps when creating the persisted snapshot. Existing ownership, pin, explicit active-state, and concurrent-change safeguards remain in place.

`test/controller.test.mjs` covers settlement with native timestamp shapes. The optional `scripts/verify_host.mjs` imports the real official bundles in an isolated Chromium context, checks adapter reads and command forwarding with fixture-backed atoms, and opens the Council dialog. It fulfills requests from extracted local assets without a server, live profile, credentials, or model calls. Install `playwright-core` only in an external test copy; pass the extracted official client assets directory as its argument. Set `T3_ADDS_TEST_BROWSER` to an existing Chromium executable, or use a Playwright-managed browser. Keep that test copy and its dependencies outside this repository.

These checks verify the bundled adapter and date conversion, not a paid end-to-end council or a live server settlement. After installation, restart T3 to load the new UI.
