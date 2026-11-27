# UI Map — ec-quote Chrome Extension & Demo Surface

Generated during `/onboard-project` on 2026-11-27.

## Surfaces

1. **WhatsApp Web Docked Panel (`extension/panel/panel.js`, injected on `https://web.whatsapp.com/*`)**
   - Shadow root `#ecq-assist-root` docked on the right (`368px` expanded, `40px` collapsed rail).
   - Views: unconfigured, no open chat (`no-chat.html`), unsupported/group chat (`chat-group.html`), manual idle (`Cere sugestie`), loading, error (`503`, `429`, `401`), suggestion (`reply`, `question` with option chips, `offer` with VAT/ex-VAT table + offer image + payment link confirmation, `needs_human` with internal staff note, `none`).
   - Attachment box: `Trimite fișierul la verificare` for loaded blobs (`chat-individual.html`) and drag-and-drop / file picker fallback for unloaded documents (`chat-lid.html`).
   - Footer self-test toggle: `Compatibilitate WhatsApp Web: ok | de verificat | deschideți o conversație`.

2. **Extension Options Page (`chrome-extension://<id>/options/options.html`)**
   - Fields: `Adresa serverului` (`#baseUrl`, HTTPS or loopback HTTP), `Token personal` (`#token`, write-only password input), `Asistent activ` (`#enabled`), `Sugestii` (`auto` / `manual`).
   - Actions: `Salvează`, `Testează conexiunea` (`GET /v1/assist/ping`).

3. **Optional Demo Chat Widget (`http://127.0.0.1:8080/demo/`, when `EC_QUOTE_DEMO=1`)**
   - Static demo page in `ec_quote/api/static/index.html` exercising `/v1/chat/*`.

## Verified Automated Browser Journeys (`extension/tests/browser/`)

- `reader.test.mjs` (5 tests): individual chat, group chat, `@lid` contact with document, no-chat state, broken-selector self-test.
- `panel.e2e.test.mjs` (17 tests): offer render, composer paste & draft overwrite confirmation (asserting zero auto-sends), XSS/HTML-as-text guard, payment-link confirmation, incoming refresh & dirty-draft protection, Romanian error mapping, group-chat silence, blob image upload, manual PDF upload, non-overlapping responsive layout & collapse persistence, full keyboard Tab/focus ring navigation, manual mode & enable toggle, empty/unconfigured states, live DOM breakage self-test, dark/light theme sync, options page token secrecy & URL validation, `TRUSTED_CONTEXTS` token isolation.
