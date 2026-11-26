---
id: story-20
title: "Real photo templates for mockups"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-2]
shared_files: [ec_quote/mockup/templates.py, ec_quote/mockup/warp.py, ec_quote/mockup/compose.py, ec_quote/mockup/service.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-20: Real photo templates for mockups

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-and-mockup.md) · **Depends on:** story-2

## Summary

The plan's mockups are the customer's design composited on 10 to 15 of the owner's own photos (a jar, a bottle, a cup, a box, a bag), not generated images. The mockup module already has a strict template manifest (`ec_quote/mockup/templates.py`), selection by context keywords, a warp for flat and cylindrical surfaces and a blend step. Today it runs on placeholder templates. This story turns the owner's photos into templates, checks each one with a calibration design, makes the choice of template predictable, and adds a command that validates a template folder so the owner or a session can add a photo later without touching code.

## User Story

As a customer, I want to see my label on a product like mine, in a photo that looks real, so that I can decide without imagining it.

## Scope

**In:** `templates/mockups/<id>/` (manifest, photo and optional mask or shading files, in the manifest format `ec_quote/mockup/templates.py` already defines) for each owner photo, replacing the generated placeholders (`ec_quote/mockup/make_placeholders.py`); `templates/mockups/README.md` (how to add one, in Romanian); `ec_quote/mockup/templates.py`, `warp.py`, `compose.py`, `service.py` (only what the real photos require); `scripts/template_check.py` (validates a folder and renders a calibration sheet); `tests/mockup/test_real_templates.py`, `tests/mockup/golden/<id>.png`, `tests/mockup/test_selection.py`.

**Out:** generated backgrounds or products (Higgsfield stays manual and on request); the cut line shape (story-22); the offer table (story-9); retouching the photos.

## Acceptance Criteria

1. Every folder under `templates/mockups/` loads through `load_templates` with the strict manifest: id equal to the folder name, the photo's pixel size, the label area (a quad for flat surfaces or cylinder parameters), the physical size of that area in centimetres, context keywords in Romanian without diacritics, a blend mode and opacity, and an optional default flag; an unknown key, a missing file or a quad outside the photo fails with the folder and key named.
2. Exactly one template is the default; `load_templates` fails if there is none or more than one.
3. `scripts/template_check.py templates/mockups/` exits 0 on the committed templates and writes a calibration sheet per template: a checkerboard with a border and corner marks composited on the photo.
4. For each template, the calibration design composited by `make_mockup` matches `tests/mockup/golden/<id>.png` within a tolerance, and the four corner marks of the design land within 3 pixels of the manifest's label area corners (flat) or of the projected cylinder edges.
5. The design's aspect ratio is preserved: a 5 by 5 cm design on a label area of 8 by 6 cm is centred and scaled to fit, never stretched; a design larger than the area in real centimetres is scaled down to fit and the result is flagged `scaled_to_fit`.
6. Transparent pixels of the design show the photo; outside the label area and under the optional occlusion mask (a lid, a hand) not one pixel of the photo changes (asserted by comparing regions with the original photo).
7. Selection: `select_template(templates, hint)` is deterministic; a table of at least 30 Romanian hints ("borcan de miere", "sticla de vin", "pahar cafea", "cutie pizza", "punga hartie", "laptop") maps to the expected template id; a hint with no match returns the default; diacritics and case do not matter; ties resolve by the manifest order.
8. The output is a JPEG or PNG of at most 1600 px on the long side and at most 600 KB, with no metadata from the customer's file or the photo (EXIF removed).
9. `make_mockup` never raises on a design that passed `check_file`; a design it cannot place returns the mockup error type and the engine sends the offer without a mockup.
10. The same design, template and settings give the same output bytes on the same platform.
11. `templates/mockups/README.md` explains in Romanian, in numbered steps, how to add a photo, fill the manifest and run the check command.

## Technical Notes

- Pillow only; perspective by a projective transform, cylinders by column remapping as in `warp.py`. No new dependency.
- Photos are committed as JPEG at most 2400 px on the long side, quality around 85, so the repository stays small.
- With fewer photos from the owner than planned, the story ships the ones received; the acceptance criteria apply to whatever is in `templates/mockups/`, minimum 3 including the default. No placeholder template remains selectable in production.

## Hand-over

Owner: 10 to 15 photos of products without a label, lit as in the shop's product pictures, at least 2000 px on the long side, with a note of the real size of the label area in centimetres for each. Owner review of the calibration sheets and of 5 sample mockups before launch.
