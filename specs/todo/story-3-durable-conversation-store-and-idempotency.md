---
id: story-3
title: "Durable conversation store and idempotent inbound"
effort: MEDIUM
epic: EPIC-0
depends_on: [story-1]
shared_files: [ec_quote/agent/store.py, ec_quote/api/store.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-3: Durable conversation store and idempotent inbound

**Repository:** ec-quote · **Epic:** [EPIC-0](epic-0-foundation.md) · **Depends on:** story-1

## Summary

A conversation lasts hours or days and its messages can be delivered twice (the CRM retries; Meta redelivers for up to 7 days). The scaffold has `ConversationStore` with a SQLite and an in memory implementation in `ec_quote/agent/store.py`, and a second store module in `ec_quote/api/store.py`. This story makes the SQLite store the proven source of truth: state survives a restart, one inbound message has one effect, two messages of the same contact are handled in order, an offer is a stored record with its exact quote, and schema changes are applied by an idempotent migration.

## User Story

As a customer, I want the assistant to remember what we agreed even if I answer the next day, and never to send me the same offer twice.

## Scope

**In:** `ec_quote/agent/store.py` (schema versioning, offers ledger, per contact lock, atomic writes, WAL mode); `ec_quote/api/store.py` (merged into it or reduced to what the API alone needs, with the reason in the pull request); `tests/agent/test_store_sqlite.py`, `tests/agent/test_store_contract.py` (the same contract suite on both implementations); `tests/e2e/test_restart.py`.

**Out:** retention and deletion (EPIC-4); metrics queries (story-17); any second datastore.

## Acceptance Criteria

1. The contract test suite passes unchanged on `InMemoryStore` and on `SqliteStore` (temporary directory).
2. Restart: state, message log, approvals and offers written by one `SqliteStore` instance are read identically by a new instance on the same file; `Decimal` values round trip exactly (`"1234.50"` stays `Decimal("1234.50")`), datetimes keep their timezone.
3. `claim_inbound(channel, key, message_id)` returns `True` once and `False` for every later call with the same triple, across instances and after a restart.
4. Delivering the same inbound message twice through the engine produces the actions once; the second delivery returns an empty action list and writes nothing.
5. Two threads handling different messages of the same contact run one after the other (a per contact lock); the stored state reflects both, in order of `received_at`; two contacts run in parallel.
6. An offer record holds: id, contact, the full `PriceQuote` and tiers as returned by the calculator, `valid_until`, status (`pending_approval`, `sent`, `rejected`, `expired`, `paid`), `draft_order_id` when present, timestamps. An offer is read back by id and by `draft_order_id`.
7. A crash between the calculator call and the write (simulated by raising inside the transaction) leaves no partial offer and the message unclaimed, so a redelivery is processed.
8. Opening a database of schema version N-1 migrates it to N without data loss; opening version N again changes nothing; a version newer than the code refuses to start with a clear error.
9. The database file and its directory are created with owner only permissions (`0600`, `0700`).

## Technical Notes

- Standard library `sqlite3`, `PRAGMA journal_mode=WAL`, `PRAGMA foreign_keys=ON`, one connection per thread or a lock around one connection.
- The contact key is stored as given (the CRM needs it); logs use a hash of it (`docs/dev-rules.md`).
- The claim and the state write happen in one transaction.

## Dependencies

story-1. Runs in parallel with story-2; the shared seam is the `ConversationStore` protocol.
