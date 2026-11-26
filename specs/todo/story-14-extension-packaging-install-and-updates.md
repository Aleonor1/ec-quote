---
id: story-14
title: "Extension: packaging, installing unpacked or from a private Chrome Web Store listing, updates"
effort: MEDIUM
epic: EPIC-1
depends_on: [story-12, story-13]
shared_files: [extension/manifest.json, extension/package.json, ec_quote/api/app.py, RUNBOOK.md]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-14: Extension: packaging, installing unpacked or from a private Chrome Web Store listing, updates

**Repository:** ec-quote (`extension/` and backend) · **Epic:** [EPIC-1](epic-1-assisted-quoting-in-the-extension.md) · **Depends on:** story-12, story-13

## Summary

Two people need the extension on their computers, and they need the next version quickly when WhatsApp Web changes its page. This story makes the extension buildable into one reproducible package, installable in two ways (loaded unpacked from a folder, for development and for the first days; and from a private, unlisted Chrome Web Store listing, which updates by itself), and makes the backend and the extension tell each other their versions so an outdated extension says "update me" instead of failing oddly. It also writes the Romanian install and update steps for the staff.

## User Story

As a staff member, I want to install the assistant in a few clicks and get fixes without doing anything, and to be told clearly when my version is too old.

## Scope

**In:** `extension/scripts/build.mjs` (or an equivalent single command: copy sources, stamp the version, produce `dist/` and a zip); `extension/manifest.json` (version, a fixed `key` so the extension id is stable across unpacked and packed installs, icons); `extension/icons/`; `extension/package.json` (scripts); `extension/test/build.test.js`, `manifest.test.js`; backend: `ec_quote/api/app.py` and `schemas.py` (`GET /v1/assist/ping` returns the backend version and the minimum extension version; requests carry the extension version in a header), `ec_quote/config.py` (the minimum extension version and the allowed extension origin), `tests/api/test_assist_ping.py`; `docs/extensie-instalare.md` (new, Romanian, for staff); `docs/extensie-publicare.md` (new, Romanian, for the owner: the store listing steps and texts); `RUNBOOK.md` (what to do when WhatsApp changes).

**Out:** the submission to the Chrome Web Store itself and the developer account (owner); a public listing; other browsers; automatic repair of selectors.

## Acceptance Criteria

1. One command builds `extension/dist/` and `extension/dist/ec-quote-extension-<version>.zip` from a clean checkout; two builds of the same commit produce byte identical zips (fixed timestamps, sorted entries).
2. The package contains only what the manifest needs: no tests, fixtures, source maps with absolute paths, `node_modules`, `.env` or backup files; a test lists the zip and compares with an allow list of paths.
3. The manifest version comes from one place (`extension/package.json`), follows `major.minor.patch`, and the build fails if the version was not raised since the last tagged build when sources changed.
4. The extension id is the same when loaded unpacked from `dist/` and when installed from the packed build, because the manifest carries a fixed public `key`; the private key file is not in the repository (the build reads its path from the environment and the hygiene scan passes).
5. The backend accepts browser requests only from the configured extension origin `chrome-extension://<that id>`; the id is documented in `docs/extensie-publicare.md` and set on the host as a setting.
6. Every request from the extension carries its version; `GET /v1/assist/ping` returns `{backend_version, min_extension_version, staff}`; when the extension is older than the minimum, the panel shows "Actualizați extensia" with the install link and stops requesting suggestions; an assist route called by an older version answers 426 with the minimum.
7. Loaded unpacked, the extension works end to end against a local backend on the fixture page (the UI journey of the epic), with no error in the service worker console on install and on browser restart.
8. `docs/extensie-instalare.md` gives numbered steps in Romanian, with what the person should see at each step, for: installing unpacked from a zip, installing from the private store link, entering the backend address and token, running the self-test, turning the assistant off, updating, and removing it.
9. `docs/extensie-publicare.md` gives the owner: creating the developer account, uploading the zip as an unlisted or private item restricted to named Google accounts, the listing texts in Romanian and English (single purpose statement, permission justifications for the WhatsApp Web host permission and storage, the data use disclosures matching `docs/privacy.md`), and how to publish an update.
10. `RUNBOOK.md` has a section "WhatsApp s-a schimbat": the staff run the self-test and send its text; a developer captures a new fixture, fixes the selector map, raises the version, builds, publishes; until then the staff answer without suggestions. It states the expected delay of a store review and that the unpacked zip is the fast path.
11. Icons exist at 16, 32, 48 and 128 px and the toolbar icon shows a distinct state for "off", "ready" and "cannot read".
12. The extension's test and build commands are in `CLAUDE.md` and both run in the pack's gates without a browser profile.

## Technical Notes

- A store listing restricted to specific accounts updates automatically and avoids Chrome's warnings about developer mode extensions; store review can take days, so the unpacked route must stay documented.
- The single purpose and permission justifications must be accurate: the extension reads the open WhatsApp Web conversation to suggest a reply and inserts text at the user's request; it does not send messages.
- WhatsApp's terms do not provide for third party tools on WhatsApp Web. The owner accepted this risk on the basis that a person sends every message and nothing is automated; the listing and the code must stay inside that line.

## Hand-over

Owner: a Chrome Web Store developer account (one time fee), the Google accounts of the staff who may install it, the first upload and each publish; safekeeping of the extension's private key.
