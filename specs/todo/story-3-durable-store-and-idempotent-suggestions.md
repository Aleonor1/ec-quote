---
id: story-3
title: "Durable conversation store and idempotent suggestions"
effort: MEDIUM
epic: EPIC-0
depends_on: [story-1]
shared_files: [ec_quote/agent/store.py, ec_quote/api/store.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-3: Durable conversation store and idempotent suggestions

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-1

## Summary

The extension calls `suggest` every time the open chat changes, from two browsers (two staff members can have the same chat open), and sends the whole visible conversation each time. The backend must therefore be idempotent on WhatsApp message ids, remember what was already understood and priced for a contact across days and restarts, and keep each suggestion and offer as a record that the payment link, the metrics and the weekly audit can read later. The scaffold has `ConversationStore` with a SQLite and an in memory implementation (`ec_quote/agent/store.py`) and a second store module in `ec_quote/api/store.py`. This story makes the SQLite store the proven source of truth.

## User Story

As a staff member, I want the suggestion for a customer to stay the same when I reopen the chat, and to continue from what was agreed yesterday instead of asking again.

## Scope

**In:** `ec_quote/agent/store.py` (schema versioning, message ledger keyed by WhatsApp message id, suggestions and offers ledger, per contact lock, atomic writes, WAL mode); `ec_quote/api/store.py` (merged into it or reduced to what the API alone needs, with the reason in the pull request); `tests/agent/test_store_sqlite.py`, `tests/agent/test_store_contract.py` (one contract suite on both implementations); `tests/e2e/test_restart.py`.

**Out:** retention and deletion (story-13 sets the rule, a later job enforces it); metric queries (story-25); any second datastore.

## Acceptance Criteria

1. The contract test suite passes unchanged on `InMemoryStore` and on `SqliteStore` (temporary directory).
2. Restart: state, messages, suggestions and offers written by one `SqliteStore` instance are read identically by a new instance on the same file; `Decimal` values round trip exactly (`"1234.50"`), datetimes keep their timezone.
3. Messages are stored once per (contact, message id): sending the same visible conversation again adds nothing; sending it with two new messages adds exactly two; a message whose id is known but whose text differs is kept as first seen and counted as a mismatch.
4. A suggestion is keyed by the contact and the id of the last message it was computed for; `suggest` with no new message returns the stored suggestion without calling the model or the calculator.
5. Two concurrent `suggest` calls for the same contact with the same messages (two staff browsers) run one after the other under a per contact lock and return the same `suggestion_id`; the model is called once. Two different contacts run in parallel.
6. A conversation that arrives with older messages missing (the page shows only the last screen) is merged with what is stored; nothing stored is deleted because it is no longer visible.
7. An offer record holds: id, contact, the suggestion it came from, the staff member who asked for the payment link, the full `PriceQuote` and tiers as returned by the calculator, `valid_until`, status (`suggested`, `link_created`, `expired`, `paid`), `draft_order_id` when present, timestamps. It is read back by id, by suggestion id and by `draft_order_id`.
8. A crash between the calculator call and the write (simulated by raising inside the transaction) leaves no partial suggestion, so the next call recomputes.
9. Opening a database of schema version N-1 migrates it to N without data loss; opening version N again changes nothing; a version newer than the code refuses to start with a clear error.
10. The database file and its directory are created with owner only permissions (`0600`, `0700`).

## Technical Notes

- Standard library `sqlite3`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`.
- The contact key is the customer's WhatsApp number in digits, as the extension reads it; when the page shows only a saved name, the key is what story-11 defines. Logs use a hash of the key (`docs/dev-rules.md`).
- The stored message text is what the retention rule covers; nothing else in the system keeps conversation content.

## Dependencies

story-1. Runs in parallel with story-2; the shared seam is the `ConversationStore` protocol.
