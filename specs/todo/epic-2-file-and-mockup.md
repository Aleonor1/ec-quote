---
id: EPIC-2
title: "File and mockup"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E2 fisier si mockup"
---

# EPIC-2: File and mockup

## Outcome

The customer sends their artwork in the chat. The assistant tells them in plain Romanian whether it can be printed at the requested size, stores it where production will find it, and answers with one image: the design on a real photo of the kind of product they mentioned, next to the price table. An unusable file is asked for again; after the allowed attempts the conversation goes to a person. The cut line shown is honest about what it is.

## Journeys

1. J1 Good file: a 300 DPI PNG with transparency for a 5 cm sticker, then "fișierul e bun", then the offer image with the mockup on a jar.
2. J2 Weak file: 180 DPI at the final size, then the customer is told it prints but slightly soft, and may send a better file or continue.
3. J3 Unusable file: 60 DPI, or a document that is not artwork, then a request for another file with the reason; the second unusable file triggers handoff `file_unusable`.
4. J4 PDF: a vector PDF is inspected by the calculator app (fonts, pages, size) and reported in the same vocabulary.
5. J5 No file: the offer is sent with the price table only; the mockup is offered when the file arrives.
6. J6 Hostile file: an HTML page renamed `.png`, a decompression bomb, an SVG with a script; each becomes `unusable` without executing anything.

## Scope

**In:** file check hardening on a fixture corpus; storage of customer files and generated images in the existing R2 bucket through the calculator app; PDF inspection through the calculator app; real photo templates with a strict manifest; the headless cut line route in the calculator app; `make_cutline` in ec-quote; the end to end file journey on the site chat.

**Later:** Higgsfield for premium mockups on request, with a human in the loop; vectorization or upscaling as a paid option in the chat (the calculator already prices `fileEditing`).

**Out:** background removal on the server; a production cut line for an image with an opaque background; editing the customer's artwork.

## Design

- `FileChecker` (`ec_quote/files/checker.py`) stays local and offline for rasters and SVG. For PDF and PDF compatible AI the verdict also uses `POST /api/sync/artwork-inspect`, which already knows fonts, Canva exports and embedded image PPI.
- Storage: `POST /api/sync/upload-url` gives a presigned PUT and a public URL under `crm/` (kept 365 days). The artwork URL goes on the Draft Order line as the upload property; generated images get a URL the channel can deliver.
- Templates: `templates/<id>/` with a manifest validated by `ec_quote/mockup/templates.py`; selection by context keywords; a default template.
- Cut line: see `ARCHITECTURE.md`, "Headless cut line". Production geometry comes only from the calculator app's kernel. Until it exists, the outline in a mockup is a preview.

### Integrations

| System | Purpose | Endpoint | Failure behaviour |
| --- | --- | --- | --- |
| Calculator app | Upload URL | `POST /api/sync/upload-url` | The file stays local; the offer is sent without a mockup link; handoff note |
| Calculator app | PDF inspection | `POST /api/sync/artwork-inspect` | Local PyMuPDF verdict only, marked as partial |
| Calculator app | Cut line | `POST /api/sync/cutline` (story-21, new) | Preview outline, marked not for production |

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Where files are stored | The calculator app's R2 bucket through `upload-url` | Exists; production and the CRM already read from it; ec-quote holds no storage keys | Decided |
| D2 | How to get a headless cut line | Extract the studio geometry into a shared kernel in the calculator app and expose a sync route | One source of geometry for the site, the CRM and ec-quote | Reserved (architectural change in another repository) |
| D2 alt | Run the real studio in a headless browser on the VPS | Rejected | Heavy, slow, fragile, and loads third party scripts | |
| D3 | Opaque background images | Shape cut or handoff, never a server made contour | No headless background removal | Decided |
| D4 | Photo templates | 10 to 15 own photos from the owner | Owner's plan | Reserved, hand-over |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| A mockup promises a cut the plotter will not make | Medium | High | Preview outlines are labelled; production geometry only from the kernel; parity test in story-21 |
| A hostile file crashes or exhausts the service | Medium | High | Caps on bytes, pixels and pages; corpus of hostile fixtures in story-18 |
| Templates look fake | Medium | Medium | Own photos, per template blend settings, QA on golden images, owner review |

## Story map

| Story | Title | Repository | Depends on | Wave | Effort |
| --- | --- | --- | --- | --- | --- |
| [story-18](story-18-file-check-hardening-on-a-fixture-corpus.md) | File check hardening on a fixture corpus | ec-quote | story-2 | 1 | MEDIUM |
| [story-19](story-19-artwork-and-image-storage-and-pdf-inspection.md) | Artwork and image storage, PDF inspection through the calculator app | ec-quote | story-2, story-4 | 1 | MEDIUM |
| [story-20](story-20-real-photo-templates-for-mockups.md) | Real photo templates for mockups | ec-quote | story-2 | 1 | MEDIUM |
| [story-21](story-21-calculator-app-headless-cut-line.md) | [calculator-app] Headless cut line: shared geometry kernel and sync route | etichetecreative-calculator-app | (none) | 1 | LARGE |
| [story-22](story-22-make-cutline-tool.md) | `make_cutline`: calculator geometry with a labelled preview fallback | ec-quote | story-19 | 2 | MEDIUM |
| [story-23](story-23-file-journey-end-to-end-on-the-site-chat.md) | The file journey end to end on the site chat | ec-quote | story-11, story-18, story-19, story-20, story-22 | 3 | MEDIUM |

**Parallelism:** 6 stories, critical path 3, widest wave 4. story-22 ships against a recorded fixture of the story-21 contract and does not wait for its deploy.

## Hand-over

- Owner: 10 to 15 photos for templates, without a label on the product, at least 2000 px on the long side.
- Owner: decision D2, then merge and deploy of story-21 in the calculator app.

## References

- Calculator app: `cerinte-contur-studio.md`, `docs/spec-crm-studio-files.md`, `docs/spec-crm-studio-frame.md`, `app/utils/production-pdf.server.ts`, `extensions/calculator/assets/contur-studio.js`.
