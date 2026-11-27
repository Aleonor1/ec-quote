// Puts text and the offer image into WhatsApp's message box. It never sends: no key press
// that submits, no click on any WhatsApp control. The staff member reads and sends.
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  const OFFER_FILENAME = 'oferta.png';
  const normalize = (text) => String(text || '').replace(/\s+/g, ' ').trim();
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function composerText(composer) {
    return composer ? NS.Reader.textOf(composer) : '';
  }

  function selectContents(field, collapseToEnd) {
    const selection = field.ownerDocument.getSelection();
    if (!selection) return;
    const range = field.ownerDocument.createRange();
    range.selectNodeContents(field);
    if (collapseToEnd) range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  // Path 1: synthetic paste event read by Lexical's clipboard handler without touching system clipboard.
  function dispatchPasteText(field, text) {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    const event = new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true });
    field.dispatchEvent(event);
    return event.defaultPrevented;
  }

  // Path 2 (fallback 1): Lexical beforeinput handler (insertText + insertLineBreak per line, never insertParagraph/send).
  function dispatchBeforeInputText(field, text, replaceExisting) {
    if (typeof InputEvent !== 'function') return false;
    let handled = false;
    if (replaceExisting) {
      const clear = new InputEvent('beforeinput', { inputType: 'deleteContentBackward', bubbles: true, cancelable: true });
      field.dispatchEvent(clear);
    }
    const lines = text.split('\n');
    for (let i = 0; i < lines.length; i += 1) {
      if (i > 0) {
        const br = new InputEvent('beforeinput', { inputType: 'insertLineBreak', bubbles: true, cancelable: true });
        if (field.dispatchEvent(br) === false) handled = true;
      }
      if (lines[i]) {
        const ins = new InputEvent('beforeinput', { inputType: 'insertText', data: lines[i], bubbles: true, cancelable: true });
        if (field.dispatchEvent(ins) === false) handled = true;
      }
    }
    return handled;
  }

  // Path 3 (fallback 2): browser editing command on the current selection.
  function execInsertText(field, text) {
    try {
      return Boolean(field.ownerDocument.execCommand('insertText', false, text));
    } catch {
      return false;
    }
  }

  async function insertIntoField(field, text, { mode = 'append' } = {}) {
    if (!field) return { ok: false, reason: 'no_composer' };
    const value = String(text || '').replace(/\r\n?/g, '\n').trim();
    if (!value) return { ok: false, reason: 'empty' };

    const fullNorm = normalize(value);
    const before = normalize(composerText(field));
    const atEnd = mode !== 'replace' && Boolean(before);
    if (!atEnd && before === fullNorm) return { ok: true, method: 'noop' };
    const landed = () => {
      const current = normalize(composerText(field));
      return atEnd ? current !== before && current.endsWith(fullNorm) : current === fullNorm;
    };

    // 1. Synthetic paste.
    field.focus();
    selectContents(field, atEnd);
    dispatchPasteText(field, value);
    await wait(60);
    if (landed()) return { ok: true, method: 'paste' };

    // 2. Lexical beforeinput events.
    field.focus();
    selectContents(field, atEnd);
    dispatchBeforeInputText(field, value, !atEnd && Boolean(before));
    await wait(60);
    if (landed()) return { ok: true, method: 'beforeinput' };

    // 3. execCommand fallback.
    field.focus();
    selectContents(field, atEnd);
    execInsertText(field, value);
    await wait(60);
    if (landed()) return { ok: true, method: 'execCommand' };

    return { ok: false, reason: 'not_inserted' };
  }

  async function insertText(text, options = {}) {
    return insertIntoField(NS.Reader.findComposer(), text, options);
  }

  function dispatchFilePaste(target, file) {
    const data = new DataTransfer();
    data.items.add(file);
    const event = new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true });
    target.dispatchEvent(event);
    return event.defaultPrevented;
  }

  function dispatchFileDrop(target, file) {
    if (typeof DragEvent !== 'function') return false;
    const data = new DataTransfer();
    data.items.add(file);
    const event = new DragEvent('drop', { dataTransfer: data, bubbles: true, cancelable: true });
    target.dispatchEvent(event);
    return event.defaultPrevented;
  }

  // Places oferta.png into WhatsApp's composer so WhatsApp opens its media preview, then puts
  // the offer text in the preview's caption input. Stops there: never clicks Send.
  async function attachImage(pngBlob, captionText = '', { timeoutMs = 1500 } = {}) {
    const composer = NS.Reader.findComposer();
    if (!composer) return { ok: false, reason: 'no_composer' };
    if (!pngBlob || !pngBlob.size) return { ok: false, reason: 'empty_image' };

    const doc = composer.ownerDocument;
    const file = new File([pngBlob], OFFER_FILENAME, { type: 'image/png' });
    composer.focus();
    dispatchFilePaste(composer, file);
    await wait(90);

    if (!NS.Reader.findMediaPreview(doc)) {
      dispatchFileDrop(composer, file);
    }

    const deadline = Date.now() + Math.max(120, timeoutMs);
    let preview = NS.Reader.findMediaPreview(doc);
    let caption = NS.Reader.findMediaCaption(doc);
    while ((!preview || !caption) && Date.now() < deadline) {
      await wait(40);
      preview = NS.Reader.findMediaPreview(doc);
      caption = NS.Reader.findMediaCaption(doc);
    }

    if (!preview) return { ok: false, reason: 'preview_not_opened' };
    const cleanCaption = String(captionText || '').replace(/\r\n?/g, '\n').trim();
    if (!cleanCaption) return { ok: true };
    if (!caption) return { ok: false, reason: 'caption_not_found' };

    const inserted = await insertIntoField(caption, cleanCaption, { mode: 'replace' });
    return inserted.ok ? { ok: true } : { ok: false, reason: 'caption_not_inserted' };
  }

  NS.Composer = {
    OFFER_FILENAME,
    insertIntoField,
    insertText,
    attachImage,
    composerText,
    hasDraft: () => Boolean(normalize(composerText(NS.Reader.findComposer()))),
  };
})();
