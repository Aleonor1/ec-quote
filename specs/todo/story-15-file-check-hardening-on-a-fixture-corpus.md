---
id: story-15
title: "File check hardening on a fixture corpus"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-2]
shared_files: [ec_quote/files/checker.py, ec_quote/files/problems.py, ec_quote/files/sniff.py, ec_quote/agent/offer.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-15: File check hardening on a fixture corpus

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-2

## Summary

`FileChecker` (`ec_quote/files/checker.py`) already turns a file and a final size into a `FileReport` with a verdict (`ok`, `weak`, `unusable`) and stable problem codes, never raises, and never touches the network. This story measures it against a corpus of the files customers really send and the files an attacker would send, fixes what the corpus exposes, bounds its resource use, and gives each problem code one Romanian sentence a customer understands. The thresholds stay in `config/rules.json` (`min_dpi_ok`, `min_dpi_weak`).

## User Story

As a staff member, I want to know in seconds whether the customer's file prints well at the requested size, with a sentence I can send them saying what to send instead if it does not.

## Scope

**In:** `ec_quote/files/checker.py`, `ec_quote/files/sniff.py`, `ec_quote/files/problems.py`; the module of fixed texts (`ec_quote/agent/offer.py` today) with one sentence per problem code; `tests/files/corpus/` (generated fixtures and a few small real ones without personal data), `tests/files/corpus/manifest.json` (file, size in cm, expected kind, verdict, problem codes), `tests/files/test_corpus.py`, `tests/files/test_limits.py`, `tests/files/make_corpus.py` (builds the synthetic files deterministically).

**Out:** PDF inspection through the calculator app and storage (story-16); the attempts counter and the `needs_human` rule (story-7); how the file gets from WhatsApp Web to the backend (story-19); fixing or converting the file; background removal.

## Acceptance Criteria

1. The corpus has at least 30 entries and every one yields exactly the kind, verdict and set of problem codes in its manifest row. It includes: PNG with alpha at 300 DPI at size; PNG at 180 DPI; JPEG at 60 DPI; a photo of a screen; CMYK JPEG; 16 bit PNG; a PNG with a white opaque background; animated GIF; multi page TIFF; WEBP; vector PDF; PDF that is one embedded low resolution image; PDF with 3 pages; password protected PDF; a PDF compatible AI file; an AI file without PDF compatibility; SVG with only paths; SVG with an embedded raster; SVG without a viewBox; a 0 byte file; a truncated PNG; a DOCX; a ZIP.
2. DPI at final size is computed on the limiting axis from pixels and the requested centimetres, to one decimal, and compared with thresholds injected from `Rules`: at or above `min_dpi_ok` is `ok`, at or above `min_dpi_weak` is `weak`, below is `unusable`. Changing the thresholds in the rules fixture moves the verdicts with no code change.
3. An aspect ratio that differs from the requested size by more than the tolerance yields a problem code and at most `weak`; the DPI is computed for the size the artwork would have when fitted inside.
4. Hostile set, each `unusable` with a stable code and without an exception, a network call or a subprocess: an HTML page named `.png`; a PNG declaring 50000 by 50000 pixels; a PDF with 10000 pages; a zip bomb named `.svg`; an SVG with a `<script>`, with an external `href`, with an XML entity expansion; a file that sniffs as one type and is named as another; a file larger than the byte cap.
5. Limits: a file over the byte cap is rejected before parsing; an image whose declared pixel count is over the pixel cap is rejected from its header without decoding; a PDF over the page cap is reported from its page count without rendering; the check of any corpus file finishes within a time bound asserted with a generous margin.
6. `check_file` is pure with respect to the file: it does not write next to it, does not modify it, and leaves no temporary file behind (asserted on a temporary directory).
7. Transparency and background: `has_transparency` is true only when alpha is actually used; an opaque uniform border is reported with its own problem code (it matters for the cut line, story-22).
8. Each problem code in `ec_quote/files/problems.py` has exactly one Romanian sentence for the suggested customer text and one short note for staff, in one module and each sentence has a code (a test compares the two sets); sentences state the fact and the remedy, with no em dash, no emoji, no jargon such as "DPI" without the plain explanation.
9. For a `weak` verdict the customer text says it can be printed and what the visible effect is; for `unusable` it says what to send instead. Both are pinned by tests for three example reports.
10. `FileChecker` reads no file other than its input and takes thresholds and caps by injection (no rules loader of its own, see story-1).

## Technical Notes

- Pillow: set `Image.MAX_IMAGE_PIXELS` to the cap and read the size from the header before `load()`. PyMuPDF: open without rendering to count pages; render at most page 1 and only at a bounded size.
- SVG is parsed as text with the standard library parser configured to forbid entities; it is never rendered here.
- Synthetic fixtures are generated in the test session from `make_corpus.py`; real files committed are under 200 KB each.
