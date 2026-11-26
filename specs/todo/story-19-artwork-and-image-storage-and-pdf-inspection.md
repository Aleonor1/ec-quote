---
id: story-19
title: "Artwork and image storage, PDF inspection through the calculator app"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-2, story-4]
shared_files: [ec_quote/pricing/client.py, ec_quote/files/checker.py, ec_quote/api/app.py, ec_quote/api/main.py]
track: full
models: {implementer: large, qa: standard, ui: none, review: large}
---

# story-19: Artwork and image storage, PDF inspection through the calculator app

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-and-mockup.md) · **Depends on:** story-2, story-4

## Summary

A customer's file has to end up where production finds it, and the images ec-quote generates have to be reachable by URL so a channel can deliver them (the CRM sends WhatsApp images by link). The calculator app already has both pieces, server to server with the same secret ec-quote uses for prices: `POST /api/sync/upload-url` (a presigned upload to the R2 bucket, public URL, keys under `crm/`, kept 365 days) and `POST /api/sync/artwork-inspect` (pages, fonts, Canva export, page size and minimum image PPI for a PDF or a PDF compatible AI file already in that storage). This story adds a small storage client and uses the inspection to complete the local verdict for PDF files. ec-quote holds no storage keys.

## User Story

As production, I want the customer's file attached to the order like a file uploaded on the site, and as a customer I want to see my mockup in the chat whatever channel I use.

## Scope

**In:** `ec_quote/integrations/storage.py` (new: `ArtworkStorage` with `upload(path, mime, filename) -> url` and `inspect_pdf(url) -> dict | None`); `ec_quote/files/checker.py` (merge of the remote inspection into the `FileReport` for PDF and AI); `ec_quote/agent/tools.py` (artwork URL kept in conversation state and passed to `create_checkout`; generated images uploaded before they are returned); `ec_quote/api/app.py` (prefer the storage URL over the media token URL when one exists); `ec_quote/api/main.py` (construction); `tests/integrations/test_storage.py`, `tests/files/test_pdf_remote_inspect.py`, fixtures of both endpoints' responses.

**Out:** changes in the calculator app (both endpoints exist); retention in the bucket (the calculator app's cleanup owns it); the cut line (story-22); virus scanning.

## Acceptance Criteria

1. `upload` calls `POST /api/sync/upload-url` with `{filename, contentType, size}` and the `X-Sync-Secret` header, then PUTs the bytes to the returned `uploadUrl` with the same content type and length, and returns `fileUrl`; the fake transport asserts both requests and their order.
2. The content type sent is the one decided by `ec_quote/files/sniff.py`, not the declared one; the file name is reduced to a safe base name; a type or size the endpoint rejects (400) is reported as `storage_rejected` with no retry.
3. The presigned URL is used once, within its expiry, and its host is not required to be on the general allow list (it comes from the trusted calculator response) but must be `https`; a non `https` upload URL is refused.
4. 401 from the calculator is `StorageUnauthorized` (reported once, like pricing), 503 "storage not configured" and 5xx are `StorageUnavailable` with one retry; in each failure the conversation continues: the file check uses local results, the offer is sent without an image link when the image could not be stored, and staff are told in the handoff note or lead.
5. `inspect_pdf(url)` returns the calculator's result for a PDF or PDF compatible AI file and `None` for 422 `not_pdf`; it is called only for files that sniff as PDF or AI and only with a URL returned by `upload`.
6. For a PDF the `FileReport` combines both sources: page count and vector or raster kind from the local check; fonts not embedded, a Canva export, more than one page, and a minimum embedded image PPI below the thresholds (scaled to the requested size from `pageSizeMm`) each add their problem code. With the remote inspection unavailable the report carries the code `inspection_partial` and the verdict is at most `weak`.
7. An AI file without PDF compatibility yields `unusable` with the code whose sentence tells the customer to save with PDF compatibility or export a PDF, the same advice the site gives.
8. Files arrive as local paths (`POST /v1/chat/upload` on the site, the fetcher for CRM media URLs). The same file sent twice in a conversation (same SHA-256) is uploaded once; the stored URL is reused.
9. The artwork URL passed to `create_checkout` is the stored URL of the last file with verdict `ok` or `weak` that the customer did not replace; with no such file no artwork property is added.
10. Generated images (offer image, mockup) are uploaded as PNG and the returned actions carry `image_url` on the storage host; without storage every channel still gets the expiring `/v1/media/{token}` URL of story-11, which the CRM downloads at once (bridge spec, section 3).
11. No file name, URL or secret appears in logs; the log has the SHA-256 prefix, size, type and outcome.

## Technical Notes

- `CalculatorClient` already carries the base URL, the secret and the retry policy; share its HTTP plumbing instead of a second client configuration.
- The storage host for the SSRF allow list of story-4 is `settings.uploadPublicBaseUrl` from the calculator config.
- Customer files under `crm/` live 365 days in the bucket. ec-quote's own retention (EPIC-0 D4) covers its local copies and conversation rows, not the bucket.

## Hand-over

None beyond `CALCULATOR_SYNC_SECRET`, already required for prices.
