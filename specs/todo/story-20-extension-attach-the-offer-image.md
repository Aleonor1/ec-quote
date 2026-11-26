---
id: story-20
title: "Extension: attach the offer image for the person to send"
effort: MEDIUM
epic: EPIC-2
depends_on: [story-12, story-18]
shared_files: [extension/content/selectors.js, extension/content/composer.js, extension/panel/]
track: full
models: {implementer: large, qa: standard, ui: standard, review: large}
---

# story-20: Extension: attach the offer image for the person to send

**Repository:** ec-quote (`extension/`) · **Epic:** [EPIC-2](epic-2-file-mockup-and-offer-image.md) · **Depends on:** story-12, story-18

## Summary

The offer suggestion now comes with a picture. The staff member needs to get it into the WhatsApp message without saving and re-uploading it. The panel shows the offer image; "Atașează imaginea" places it in WhatsApp's composer as an attachment with the offer text as its caption, exactly as if the person had pasted a picture, and stops there: WhatsApp shows its own preview and the person presses Send. If WhatsApp's page does not accept it, the panel falls back to copying the image to the clipboard and to a download button.

## User Story

As a staff member, I want the offer picture in the message with one click, and to see it in WhatsApp's own preview before I send it.

## Scope

**In:** `extension/panel/` (image preview, attach, copy, download actions); `extension/background/api-client.js` (fetch the image with the token); `extension/content/composer.js` (place an image file into the composer through the selector map); `extension/content/selectors.js` (entries for the composer's paste target and the media preview's caption field); `extension/test/attach-image.test.js`.

**Out:** building the image (story-18); sending; attaching anything other than the offer image of the current suggestion; documents.

## Acceptance Criteria

1. For a suggestion with an image, the panel shows it scaled to the panel width with alt text, fetched by the service worker with the assist token; the image bytes are not stored anywhere by the extension.
2. "Atașează imaginea" delivers the image to WhatsApp's composer as a pasted or dropped file, so that WhatsApp opens its own media preview with that image; the offer text is placed in the preview's caption field; nothing is sent.
3. The test scan of story-12 still holds: no code clicks send, in the composer or in the media preview, and the selector map has no entry for either send button.
4. If the media preview does not appear within the configured time, or the caption field cannot be found, the panel says so in Romanian and offers "Copiază imaginea" (writes the PNG to the clipboard for the person to paste) and "Descarcă" (saves the PNG through a link), and the text insert of story-12 remains available separately.
5. Attach works on the image of the current suggestion only: after the chat changes or the suggestion is replaced, the old image cannot be attached (the action is disabled and the fetched bytes are dropped).
6. If the composer already holds text typed by the person, attaching asks before replacing the caption; the person's text is never discarded silently.
7. The attached file's name is neutral (`oferta.png`), carries no customer or staff name, and its bytes equal the bytes fetched from the backend (asserted in the test by comparing the file delivered to the fixture page with the fake backend's image).
8. Clipboard use happens only on the person's click on "Copiază imaginea"; the extension requests no clipboard read permission.
9. A failed image fetch (401, 404, network) shows a Romanian message and leaves the text suggestion usable.
10. Tests run on the page fixtures with a fake backend: a fixture whose composer accepts a paste event shows the preview state; a fixture without the caption field triggers the fallback.

## UI Notes

Image block between the offer table and the buttons; buttons in order: Inserează textul, Atașează imaginea, Link de plată. States: loading image, ready, attaching, attached (waiting for the person to send), fallback. Checked by the UI test session on the fixture page.

## Technical Notes

- WhatsApp's composer accepts images through paste and drop; dispatching a paste event carrying the file on the focused composer follows the page's own path and shows its preview. This is inside the project's line (placing content for a person to send); pressing any button in the preview is not.
- The behaviour of the media preview is as undocumented and changeable as the rest of the page; its selectors live in the map with their own self-test entries.

## Hand-over

None.
