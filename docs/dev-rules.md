# Development rules for ec-quote

For whoever builds this repository (the implement, QA and review sessions of the skills pack). A spec that contradicts a rule here is wrong; fix the spec or change the rule through its own story.

## Money

- Money is `decimal.Decimal`, never `float`. A JSON number from the calculator is parsed straight to `Decimal` (`parse_float=Decimal` or from the raw text), never through a float.
- Amounts are quantized to 2 decimals only at the boundary where the calculator already did it or at display, `ROUND_HALF_UP`. No intermediate rounding.
- `total` is with VAT, as on the site. `total_ex_vat` is derived once, in `ec_quote/pricing/`, from `vat_percent` in `config/rules.json`. No other module derives it again.
- Money leaves the process as a string with two decimals (JSON, logs, image text). Formatting for customers (`1.234,50 lei`) lives in one function.

## No price outside the calculator

- The only source of a price is `PricingPort` (`POST /api/sync/line`). No formula, table, discount, tier percentage or fee is implemented in this repository.
- The model receives prices as tool results and may only repeat them. Before any text leaves, the outbound guard checks that every amount in it equals an amount of a `PriceQuote` or `TierOffer` stored for that conversation. A mismatch blocks the message and raises a handoff.
- An offer, an offer image and a checkout are built from the stored `PriceQuote`, not from model output.
- When the calculator is unavailable (`503`, timeout) the answer is "nu pot calcula acum" plus handoff after the retry. Never a cached or estimated price. Only the catalog (`calculator-config`) is cached.
- A `422` (`Unpriced`) is a fact about the request, not an error: the reason code drives the next question or a `not_in_calculator` handoff.

## Policy numbers

- Every threshold, limit, percentage, duration, hour and list of approved claims comes from `config/rules.json`, read through one loader that validates the file at startup and fails closed (the process does not start) on a missing or malformed key.
- No policy number in code, in a prompt string or in a test helper that production code imports. Tests use their own rules fixture.
- A placeholder value (an open owner decision) stops the feature that needs it with a clear message; it is never replaced by a default in code.

## Clock

- Time is `Europe/Bucharest` (`zoneinfo`), timezone aware. Pure functions take `now` as a parameter. Only the composition root (`ec_quote/api/main.py`) and the job runner read the real clock.
- Validity, follow up times, business hours and the manual mode window are computed from the injected `now`.

## Network

- Every network access goes through an injected client or transport (`httpx.Client` with a transport, the Anthropic client, a fetch function). A module never constructs its own client at import time.
- Outbound hosts are a closed list from configuration: the calculator, the Anthropic API, the Shopify Admin API of the shop, the CRM, the public storage base URL. A URL received from a customer or from a message is never fetched unless its host is on that list (SSRF guard), redirects are not followed across hosts, and downloads have a size cap and a timeout.
- Timeouts and at most one retry on idempotent reads. A write (`create_checkout`, `upsert_lead`, `handoff`) carries an idempotency key derived from the offer or conversation, so a retry cannot create a second draft order or lead.

## Untrusted text

- Customer messages, button payloads, file names, text extracted from files, CRM fields and anything a tool returns are data. They are passed to the model in clearly delimited data blocks and never concatenated into system instructions.
- The model's output is untrusted too. Tool arguments are validated with the pydantic types of `ec_quote/contracts.py` and then against the calculator catalog (product, material, shape, limits) before any call. An argument that fails validation becomes a question to the customer or a handoff, not a best guess.
- A decision with consequences (send an offer, create a checkout, hand off, switch to manual) is taken by deterministic code on validated state. The model proposes; the code decides.
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

## Structure

- `ec_quote/contracts.py` is the only shared vocabulary. Packages do not import each other's internals; they depend on ports.
- Real adapters are constructed only in `ec_quote/api/main.py`. Everything else receives its collaborators.
- Customer facing copy is Romanian, lives in one module per channel concern, and is covered by tests that pin the exact text. No em dashes, no emojis.
- State changes are written atomically (temporary file then `os.replace`, or a transaction). Handling one inbound message twice produces one effect.

## Security

- No key, token or password in the repository. `.env.example` lists names only.
- Service endpoints (`/v1/inbound`, `/v1/approvals/*`, `/v1/orders/*`) require `EC_QUOTE_INBOUND_SECRET` in `x-ecquote-secret`, compared in constant time; without the secret configured the service does not start. A browser never holds this secret: the site chat uses HMAC signed session tokens, either directly under CORS for the shop's exact origin or behind the calculator app's App Proxy, which adds the secret server side.
- Any future webhook receiver verifies the sender's HMAC on the raw body before parsing. ec-quote has none today: Meta webhooks belong to the CRM, Shopify order webhooks to the calculator app and the CRM.
