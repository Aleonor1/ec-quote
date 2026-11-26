---
id: story-22
title: "make_cutline: calculator geometry with a labelled preview fallback"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-16]
shared_files: [ec_quote/contracts.py, ec_quote/agent/tools.py, ec_quote/mockup/service.py, ec_quote/mockup/compose.py]
track: full
models: {implementer: standard, qa: standard, ui: none, review: standard}
---

# story-22: make_cutline: calculator geometry with a labelled preview fallback

**Repository:** ec-quote · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-16 (stored artwork URL). Uses the contract of story-21 through a recorded fixture; does not wait for its deploy.

## Summary

`make_cutline` is one of the plan's tools: the outline along which the sticker will be cut, shown in the mockup. Production geometry can come only from the calculator app (story-21, `POST /api/sync/cutline`), because that is the code production already trusts. This story adds the tool to ec-quote as a client of that route. While the route is not deployed, or when it is down, the tool returns a simple outline computed locally for the mockup only, and says so in its result: such an outline is never called a cut line to the customer and never travels to the order.

## User Story

As a customer, I want to see the shape my sticker will have, and as production I never want a guessed outline to reach an order.

## Scope

**In:** `ec_quote/contracts.py` (`CutlineResult`: `source: "calculator" | "preview"`, `kind: "contour" | "shape"`, paths in millimetres, `warnings`; `CutlinePort`); `ec_quote/integrations/cutline.py` (new: client of the route); `ec_quote/mockup/outline.py` (new: local preview outline from alpha with Pillow); `ec_quote/agent/tools.py` (the `make_cutline` tool, state); `ec_quote/mockup/service.py`, `compose.py` (clip the design to the outline and draw it); the module of fixed texts; `tests/integrations/test_cutline.py`, `tests/mockup/test_outline.py`, `tests/integrations/fixtures/cutline/*.json`.

**Out:** the route itself (story-21); production files; emboss; background removal.

## Acceptance Criteria

1. With the route available (fake transport replaying the fixture), `make_cutline(artwork_url, width_cm, height_cm, shape)` returns `source: "calculator"` with the route's `kind`, `paths` and `warnings` unchanged, as `Decimal` millimetres.
2. The request carries `X-Sync-Secret`, the stored artwork URL of story-16 (never a customer supplied URL) and the validated choices of the current line; the tool refuses to run before a file with verdict `ok` or `weak` exists.
3. A 404 (route not deployed), 5xx, timeout or `StorageUnavailable` yields `source: "preview"`: for a design with used transparency, the outline of the alpha mask grown by a fixed margin and smoothed; for an opaque design, the requested fixed shape. The result carries the warning `preview_only`.
4. A 422 `no_contour` with reason `opaque_background` yields a result with `kind: "shape"` for the fallback shape when the product allows a fixed shape, and otherwise a signal handled by story-7's rules; the suggested text explains that a contour needs a transparent background.
5. The mockup draws the design clipped to the outline with the border the outline implies; with `source: "calculator"` the outline is drawn as the cut line; with `source: "preview"` it is drawn without the cut line styling.
6. Suggested text: with `source: "calculator"` the fixed sentence may say the dotted line is where the sticker is cut; with `source: "preview"` the fixed sentence says the shape is indicative and the exact cut line is confirmed before production. Both pinned by tests; the guard of story-8 rejects model text that calls a preview a cut line.
7. A preview outline is never stored on the offer as cut geometry and never sent to `create_checkout`; a test asserts the Draft Order attributes contain no geometry for a preview result.
8. A calculator result is stored on the offer with its `kind` and warnings, and its warnings are included in `note_for_staff`.
9. The local outline runs within the pixel cap of story-15, never raises on a file that passed `check_file`, and for a transparent circle fixture differs from the true circle by less than 2% of the diameter.
10. The same inputs give the same result; a second call for the same file hash, size and shape in a conversation returns the stored result without a network call.

## Technical Notes

- The local outline is deliberately simple (Pillow alpha threshold, max filter for the margin, contour of the mask). It does not implement production rules and must not grow into a second geometry engine.
- Path format follows `ProofData` of the calculator app: millimetres, design at (0,0), y down, closed loops.
- When story-21 is deployed, nothing changes here but the fixture being replaced by a recorded live response.

## Dependencies

story-16. Contract: story-21 in the calculator app.
