---
id: EPIC-2
title: "File check, mockup and offer image in the extension"
status: proposed
prompt: "Plan implementare: Ofertare instant pe site si WhatsApp, E2 fisier si mockup; revised 2026-11-26 for the Chrome extension"
---

# EPIC-2: File check, mockup and offer image in the extension

## Outcome

The customer sends their artwork in the WhatsApp chat. The staff member clicks once next to it in the panel; the backend tells them in plain words whether it prints well at the requested size and gives them the sentence to send if it does not; it stores the file where production will find it; and the offer comes with one picture: the design on a real photo of the kind of product the customer mentioned, with the price table under it. One click places that picture in the message for the person to send. The cut line shown is honest about what it is.

## Journeys

1. J1 Good file: the customer sends a logo "as document"; the person clicks "Verifică fișierul"; the panel says it is good; the offer appears with the mockup on a jar; "Atașează imaginea" opens WhatsApp's preview with the picture and the caption; the person sends.
2. J2 Weak file: 180 DPI at the final size; the panel says it prints but slightly soft and suggests the sentence for the customer; the offer is still available.
3. J3 Unusable file: a 60 DPI photo; the panel suggests asking for another file, with the reason; after the second unusable file the panel says it is theirs to handle.
4. J4 PDF: a vector PDF is inspected by the calculator app (fonts, pages, size) and reported in the same words.
5. J5 No file yet: the offer has the price table image only; the mockup appears when a file is checked.
6. J6 Hostile or odd file: an HTML page renamed `.png`, an oversized image, an SVG with a script; each becomes "unusable" without executing anything.
7. J7 WhatsApp does not hand over the file: the panel asks the person to click the file once in WhatsApp, or to drop the saved file on the panel.

## Scope

**In:** file check hardening on a fixture corpus; storage of customer artwork in the existing R2 bucket through the calculator app, and PDF inspection through it; real photo templates; the offer image; obtaining customer attachments in the extension and uploading them; attaching the offer image in the extension; the headless cut line route in the calculator app; `make_cutline` in ec-quote; the end to end file journey.

**Later:** Higgsfield for premium mockups on request, by a person; vectorization or upscaling as a paid option (the calculator already prices `fileEditing`).

**Out:** background removal on the server; a production cut line for an image with an opaque background; editing the customer's artwork; sending anything; fetching files the person did not point at.

## Design

- `FileChecker` (`ec_quote/files/checker.py`) stays local and offline for rasters and SVG. For PDF and PDF compatible AI the verdict also uses `POST /api/sync/artwork-inspect`.
- Files reach the backend through `POST /v1/assist/upload`, only on a staff click, one file at a time. Customer artwork then goes to the calculator app's R2 bucket through `POST /api/sync/upload-url` (keys under `crm/`, kept 365 days) so the Draft Order line carries it like a site upload.
- Templates: `templates/mockups/<id>/` with a manifest validated by `ec_quote/mockup/templates.py`; selection by context keywords; one default.
- The offer image is built from the same `Offer` object as the text and fetched by the extension with the staff token.
- In the page the extension may, in addition to EPIC-1: obtain the bytes of an attachment the person pointed at, and place the offer image in the composer. Still nothing is sent.
- Cut line: see `ARCHITECTURE.md`, "Headless cut line". Production geometry comes only from the calculator app's kernel; until it exists the outline in a mockup is a labelled preview.

### Integrations

| System | Purpose | Endpoint | Failure behaviour |
| --- | --- | --- | --- |
| Calculator app | Upload URL | `POST /api/sync/upload-url` | The offer is still produced; a staff note says the file must be attached to the order by hand |
| Calculator app | PDF inspection | `POST /api/sync/artwork-inspect` | Local PyMuPDF verdict only, marked as partial |
| Calculator app | Cut line | `POST /api/sync/cutline` (story-21, new) | Preview outline, marked not for production |
| WhatsApp Web | Attachment bytes, composer paste | The page | A named state and the drop on panel fallback; copy or download for the image |

## Decisions

| # | Decision | Chosen | Why | Bucket |
| --- | --- | --- | --- | --- |
| D1 | Where customer files are stored | The calculator app's R2 bucket through `upload-url` | Exists; production already reads from it; ec-quote holds no storage keys | Decided |
| D2 | How to get a headless cut line | Extract the studio geometry into a shared kernel in the calculator app and expose a sync route | One source of geometry for the site and ec-quote | Reserved (architectural change in another repository) |
| D2 alt | Run the real studio in a headless browser on the host | Rejected | Heavy, slow, fragile, loads third party scripts | |
| D3 | Opaque background images | Shape cut or a person, never a server made contour | No headless background removal | Decided |
| D4 | Photo templates | 10 to 15 own photos from the owner | Owner's plan | Reserved, hand-over |
| D5 | When files leave the browser | Only on the staff member's click, one file | Privacy and WhatsApp scope | Decided |

## Risks

| Risk | Likelihood | Impact | Mitigation |
| --- | --- | --- | --- |
| WhatsApp Web does not expose attachment bytes in a readable way, or changes how | Medium to high | Medium | story-19 confines it to one module with a failure state and supports dropping a saved file on the panel |
| WhatsApp photos are recompressed and look worse than the original | High | Medium | story-19: the staff note and suggested text ask for the file "as document" |
| A mockup promises a cut the plotter will not make | Medium | High | Preview outlines are labelled; production geometry only from the kernel; parity test in story-21 |
| A hostile file crashes or exhausts the service | Medium | High | Caps on bytes, pixels and pages; hostile fixtures in story-15 |
| Templates look fake | Medium | Medium | Own photos, per template blend settings, golden images, owner review |

## Story map

| Story | Title | Where | Depends on | Wave | Effort |
| --- | --- | --- | --- | --- | --- |
| [story-15](story-15-file-check-hardening-on-a-fixture-corpus.md) | File check hardening on a fixture corpus | backend | story-2 | 1 | MEDIUM |
| [story-16](story-16-artwork-storage-and-pdf-inspection.md) | Artwork storage and PDF inspection through the calculator app | backend | story-2, story-4 | 1 | MEDIUM |
| [story-17](story-17-real-photo-templates-for-mockups.md) | Real photo templates for mockups | backend | story-2 | 1 | MEDIUM |
| [story-18](story-18-offer-image-with-mockup-and-price-table.md) | Offer image: mockup and price table in one picture | backend | story-9, story-17 | 2 | MEDIUM |
| [story-19](story-19-extension-customer-attachments-to-file-check.md) | Extension: customer attachments from WhatsApp Web to the file check | extension, backend | story-12, story-13, story-15 | 2 | HIGH |
| [story-20](story-20-extension-attach-the-offer-image.md) | Extension: attach the offer image for the person to send | extension | story-12, story-18 | 3 | MEDIUM |
| [story-21](story-21-calculator-app-headless-cut-line.md) | [calculator-app] Headless cut line: shared geometry kernel and sync route | etichetecreative-calculator-app | (none) | 1 | LARGE |
| [story-22](story-22-make-cutline-tool.md) | `make_cutline`: calculator geometry with a labelled preview fallback | backend | story-16 | 2 | MEDIUM |
| [story-23](story-23-file-journey-end-to-end-in-assisted-mode.md) | The file journey end to end in assisted mode | backend, extension | story-15, story-16, story-17, story-18, story-19, story-20, story-22 | 4 | MEDIUM |

**Parallelism:** 9 stories, critical path 4, widest wave 4. The backend stories 15, 16, 17 and the calculator app story 21 can start as soon as EPIC-0 is merged, in parallel with the extension work of EPIC-1. story-22 ships against a recorded fixture of the story-21 contract and does not wait for its deploy.

## Hand-over

- Owner: 10 to 15 photos for templates, without a label on the product, at least 2000 px on the long side; logo and brand colours.
- Owner: decision D2, then merge and deploy of story-21 in the calculator app.
- Staff: one real conversation with a photo and one with a PDF sent as a document, for fixtures.

## References

- Calculator app: `cerinte-contur-studio.md`, `docs/spec-crm-studio-files.md`, `docs/spec-crm-studio-frame.md`, `app/utils/production-pdf.server.ts`, `extensions/calculator/assets/contur-studio.js`.
