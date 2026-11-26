# Development rules for ec-quote

For whoever builds this repository (the implement, QA and review sessions of the skills pack). The product is assisted quoting: the backend suggests, a Chrome extension shows the suggestion in WhatsApp Web, a person sends. A spec that contradicts a rule here is wrong; fix the spec or change the rule through its own story.

## Money

- Money is `decimal.Decimal`, never `float`. A JSON number from the calculator is parsed straight to `Decimal` (`parse_float=Decimal` or from the raw text), never through a float.
- Amounts are quantized to 2 decimals only at the boundary where the calculator already did it or at display, `ROUND_HALF_UP`. No intermediate rounding.
- `total` is with VAT, as on the site. `total_ex_vat` is derived once, in `ec_quote/pricing/`, from `vat_percent` in `config/rules.json`. No other module derives it again.
- Money leaves the process as a string with two decimals (JSON, logs, image text). Formatting for customers (`1.234,50 lei`) lives in one function.

## No price outside the calculator

- The only source of a price is `PricingPort` (`POST /api/sync/line`). No formula, table, discount, tier percentage or fee is implemented in this repository.
- The model receives prices as tool results and may only repeat them. Before a suggestion is returned, the guard checks that every amount in its text equals an amount of a `PriceQuote` or `TierOffer` stored for that conversation. A mismatch blocks the text and the suggestion becomes `needs_human`. A person reviewing the suggestion is not the price check; the guard is.
- An offer, an offer image and a checkout are built from the stored `PriceQuote`, not from model output.
- When the calculator is unavailable (`503`, timeout) the suggestion is `needs_human` with the note that the price cannot be computed now. Never a cached or estimated price. Only the catalog (`calculator-config`) is cached.
- A `422` (`Unpriced`) is a fact about the request, not an error: the reason code drives the next question or a `needs_human` suggestion with reason `not_in_calculator`.

## Policy numbers

- Every threshold, limit, percentage, duration, hour and list of approved claims comes from `config/rules.json`, read through one loader that validates the file at startup and fails closed (the process does not start) on a missing or malformed key.
- No policy number in code, in a prompt string or in a test helper that production code imports. Tests use their own rules fixture.
- A placeholder value (an open owner decision) stops the feature that needs it with a clear message; it is never replaced by a default in code.

## Clock

- Time is `Europe/Bucharest` (`zoneinfo`), timezone aware. Pure functions take `now` as a parameter. Only the composition root (`ec_quote/api/main.py`) and the job runner read the real clock.
- Validity, reminder times and business hours are computed from the injected `now`.

## Network

- Every network access goes through an injected client or transport (`httpx.Client` with a transport, the Anthropic client, a fetch function). A module never constructs its own client at import time.
- Outbound hosts of the backend are a closed list from configuration: the calculator, the Anthropic API, the Shopify Admin API of the shop, the public storage base URL, and the CRM only when EPIC-4 is built. A URL received from a customer or from a message is never fetched unless its host is on that list (SSRF guard), redirects are not followed across hosts, and downloads have a size cap and a timeout.
- Timeouts and at most one retry on idempotent reads. A write (`create_checkout`, and `upsert_lead` if EPIC-4 is built) carries an idempotency key derived from the suggestion or offer, so a retry or a second click cannot create a second draft order or lead.

## Untrusted text

- Customer messages, button payloads, file names, text extracted from files, CRM fields and anything a tool returns are data. They are passed to the model in clearly delimited data blocks and never concatenated into system instructions.
- The model's output is untrusted too. Tool arguments are validated with the pydantic types of `ec_quote/contracts.py` and then against the calculator catalog (product, material, shape, limits) before any call. An argument that fails validation becomes a suggested question or a `needs_human` suggestion, not a best guess.
- A decision with consequences (propose an offer, allow a payment link, mark `needs_human`) is taken by deterministic code on validated state. The model proposes; the code decides; the person sends.
- Text read from WhatsApp Web is untrusted in the same way, including messages marked as written by staff: the extension reports them, the backend treats them as data.
- Files are parsed defensively: type from magic bytes, not from the extension or the declared MIME; caps on bytes, pixels and pages; no execution of embedded content; an SVG is never rendered with scripts or external references.
- Text shown to the customer that includes customer supplied values (name, file name) is plain text.

## Personal data and logs

- Logs carry ids, never content: conversation id, offer id, a hash of the contact key, tool name, duration, status, reason code. No phone number, name, email, message text, file name or file URL at INFO or above. DEBUG may not be enabled in production.
- Secrets never appear in logs, errors, exceptions or test output. Configuration is logged as names of the keys that are set.
- Personal data is stored only under `EC_QUOTE_DATA_DIR`, with a retention period from `config/rules.json`. Fixtures in `tests/` use invented contacts (`4070000xxxx`, `Client Test`).
- Data sent to the model is the minimum needed: the message text and the catalog slice. Phone, email and payment links are not placed in prompts.

## Tests

- `pytest`, tests under `tests/` mirroring `ec_quote/`. No test touches the network: every port has a fake (`FakeCalculator`, a fake model that replays scripted tool calls, fake Shopify and CRM transports). A test that opens a socket fails the suite.
- No real clock, no sleep, no randomness without a seed. Images are compared with a tolerance or by structural facts (size, pixels in a region), not by byte equality across platforms.
- Live checks (price audit against the production calculator, a real draft order) are scripts run by hand with secrets from the environment. They are not collected by `pytest` and their results are committed only as reports without personal data.
- Pack gate: all green, nothing skipped, suite run twice, 95% of changed lines and branches, global coverage never below the committed baseline.

## Dependencies

- No new runtime dependency without a written reason in the story (what it replaces, licence, last release, size). Prefer the standard library and what `pyproject.toml` already lists.
- No second library for a job one already does: httpx for HTTP, pydantic for validation, Pillow for raster, PyMuPDF for PDF.
- Paid services: only the ones in the owner's plan (model API, hosting). Higgsfield is used only for premium mockups on request and never from an unattended path.
- The extension has no runtime dependency beyond the browser. A build or test tool for it needs the same written reason.

## Structure

- `ec_quote/contracts.py` is the only shared vocabulary. Packages do not import each other's internals; they depend on ports.
- Real adapters are constructed only in `ec_quote/api/main.py`. Everything else receives its collaborators.
- Suggested customer text and panel text are Romanian, covered by tests that pin the exact fixed strings. No em dashes, no emojis.
- State changes are written atomically (temporary file then `os.replace`, or a transaction). Calling `suggest` twice with the same message ids produces one stored state and the same suggestion.

## The extension

- Manifest V3. Host permissions are exactly `https://web.whatsapp.com/*` and the configured backend origin. No `<all_urls>`, no remote code, no `eval`, no third party script or CDN; everything is bundled and reviewable.
- Page interaction is limited to: reading the conversation the staff member has open, inserting text into the composer, attaching the offer image to the composer, and downloading an attachment the staff member pointed at. The extension never presses Send, never switches chats, never reads the chat list or other chats, never acts when its panel is closed, and has no scheduled or bulk action. A story that needs more than this is out of scope and goes back to the owner.
- Every selector and every assumption about WhatsApp Web's DOM lives in one file (the selector map). No selector literal anywhere else; a test enforces it. Each entry has a name, the selector or strategy, and what "found" means, so the self-test can check it.
- WhatsApp Web changes without notice. A selector that does not match is a reported state, not an exception and not a guess: the panel shows which part cannot be read and offers no suggestion built on partial reading. Prefer stable attributes (roles, `data-*` ids, aria labels) over generated class names.
- Only the service worker talks to the backend. The content script never receives the token and makes no network request. Messages between the two are validated by shape and sender.
- No message text, customer name, phone or file is written to `chrome.storage`, `localStorage`, IndexedDB, the console or an error report. They live in memory for the open chat and are dropped when the chat changes or the panel closes. Stored: the backend address and the staff token, in `chrome.storage.local`.
- Text from the page or the backend is put into the panel as text, never as HTML. Text is put into the composer through the page's own input path so the person sees exactly what will be sent.
- The extension has no price logic, no policy and no model call. It shows what the backend returned. Amounts are displayed as received, as strings.
- Extension tests run without WhatsApp and without the backend: DOM fixtures (saved, anonymized page fragments) for the reader, a fake backend for the service worker. A check against the live page is the self-test a person runs, not part of the suite.

## Security

- No key, token or password in the repository. `.env.example` lists names only.
- The assist endpoints (`/v1/assist/*`) require `X-EcQuote-Assist-Token`. There is one token per staff member, so every suggestion and every payment link is attributed to a person and one token can be revoked alone. Tokens are compared in constant time, stored only as configuration, at least 32 random bytes, and never logged; with no token configured the assist endpoints refuse every request.
- The assist endpoints answer browser requests only from the extension's origin (`chrome-extension://<id>`), listed in configuration.
- The optional site chat and service endpoints (`/v1/chat/*`, `/v1/inbound`, `/v1/approvals/*`) keep their own rule: `EC_QUOTE_INBOUND_SECRET` in `x-ecquote-secret` for service callers, HMAC signed session tokens for browsers. They are disabled unless configured.
- ec-quote receives no webhook. Any future receiver verifies the sender's HMAC on the raw body before parsing.
