// Puts text into WhatsApp's message box. It never sends: no Enter key, no click on any
// WhatsApp control. The staff member reads the text and presses Send.
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  const normalize = (text) => String(text || '').replace(/\s+/g, ' ').trim();

  function composerText(composer) {
    return composer ? NS.Reader.textOf(composer) : '';
  }

  function selectContents(composer, collapseToEnd) {
    const selection = composer.ownerDocument.getSelection();
    if (!selection) return;
    const range = composer.ownerDocument.createRange();
    range.selectNodeContents(composer);
    if (collapseToEnd) range.collapse(false);
    selection.removeAllRanges();
    selection.addRange(range);
  }

  // Synthetic paste: the editor reads the text from the event, nothing touches the clipboard.
  function dispatchPaste(composer, text) {
    const data = new DataTransfer();
    data.setData('text/plain', text);
    const event = new ClipboardEvent('paste', { clipboardData: data, bubbles: true, cancelable: true });
    composer.dispatchEvent(event);
    return event.defaultPrevented; // true when the editor handled it
  }

  const nextFrame = () => new Promise((resolve) => setTimeout(resolve, 60));

  // mode: 'append' (default) | 'replace'. Returns { ok, reason }.
  async function insertText(text, { mode = 'append' } = {}) {
    const composer = NS.Reader.findComposer();
    if (!composer) return { ok: false, reason: 'no_composer' };
    const value = String(text || '').replace(/\r\n?/g, '\n').trim();
    if (!value) return { ok: false, reason: 'empty' };

    const before = normalize(composerText(composer));
    composer.focus();
    selectContents(composer, mode !== 'replace');

    dispatchPaste(composer, value);
    await nextFrame();
    let after = normalize(composerText(composer));

    if (after === before || !after.includes(normalize(value).slice(0, 40))) {
      // Fallback for editors that ignore synthetic paste events.
      composer.focus();
      selectContents(composer, mode !== 'replace');
      try {
        composer.ownerDocument.execCommand('insertText', false, value);
      } catch {
        // Reported below.
      }
      await nextFrame();
      after = normalize(composerText(composer));
    }

    const ok = after.includes(normalize(value).slice(0, 40));
    return ok ? { ok: true } : { ok: false, reason: 'not_inserted' };
  }

  NS.Composer = { insertText, composerText, hasDraft: () => Boolean(normalize(composerText(NS.Reader.findComposer()))) };
})();
