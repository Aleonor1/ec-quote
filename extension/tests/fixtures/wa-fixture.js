// Fake editor and helpers for the fixture pages. Records anything that would be a send.
(() => {
  const wa = (window.__wa = {
    sent: [],
    sendClicks: 0,
    enterKeys: 0,
    pastes: 0,
    beforeInputs: 0,
    attachedFiles: [],
    composerMode: 'paste', // 'paste' | 'beforeinput' | 'execCommand'
    disableMediaPreview: false,
    disableMediaCaption: false,
  });
  if (new URLSearchParams(location.search).get('theme') === 'dark') document.body.classList.add('dark');

  const composer = document.querySelector('footer [contenteditable="true"]');
  const readText = () => (composer ? composer.innerText.replace(/\n$/, '') : '');
  const send = () => {
    wa.sent.push(readText());
    composer.replaceChildren(document.createElement('p'));
  };

  function insertPlainInto(field, text) {
    const selection = getSelection();
    if (!selection.rangeCount || !field.contains(selection.anchorNode)) {
      selection.selectAllChildren(field);
      selection.collapseToEnd();
    }
    const range = selection.getRangeAt(0);
    range.deleteContents();
    const fragment = document.createDocumentFragment();
    text.split('\n').forEach((line, index) => {
      if (index) fragment.append(document.createElement('br'));
      fragment.append(document.createTextNode(line));
    });
    range.insertNode(fragment);
    selection.collapseToEnd();
  }

  function wireEditable(field, { allowFilePaste = false } = {}) {
    field.addEventListener('paste', (event) => {
      const files = event.clipboardData ? [...event.clipboardData.files] : [];
      if (allowFilePaste && files.length) {
        if (wa.disableMediaPreview) return;
        event.preventDefault();
        openMediaPreview(files[0]);
        return;
      }
      if (wa.composerMode !== 'paste') return;
      event.preventDefault();
      wa.pastes += 1;
      insertPlainInto(field, event.clipboardData.getData('text/plain'));
    });

    field.addEventListener('beforeinput', (event) => {
      if (wa.composerMode !== 'beforeinput') return;
      if (event.inputType === 'deleteContentBackward') {
        event.preventDefault();
        field.replaceChildren();
        return;
      }
      if (event.inputType === 'insertLineBreak') {
        event.preventDefault();
        wa.beforeInputs += 1;
        field.append(document.createElement('br'));
        return;
      }
      if (event.inputType === 'insertText' && typeof event.data === 'string') {
        event.preventDefault();
        wa.beforeInputs += 1;
        field.append(document.createTextNode(event.data));
      }
    });

    if (allowFilePaste) {
      field.addEventListener('drop', (event) => {
        const files = event.dataTransfer ? [...event.dataTransfer.files] : [];
        if (!files.length || wa.disableMediaPreview) return;
        event.preventDefault();
        openMediaPreview(files[0]);
      });
    }
  }

  async function openMediaPreview(file) {
    const buf = new Uint8Array(await file.arrayBuffer());
    wa.attachedFiles.push({ name: file.name, type: file.type, size: file.size, bytes: [...buf] });
    document.querySelector('[data-wa-media-preview]')?.remove();
    const preview = document.createElement('div');
    preview.setAttribute('data-wa-media-preview', 'true');
    preview.setAttribute('aria-label', 'Previzualizare media');
    const img = document.createElement('img');
    img.src = URL.createObjectURL(file);
    preview.append(img);
    if (!wa.disableMediaCaption) {
      const caption = document.createElement('div');
      caption.setAttribute('data-wa-media-caption', 'true');
      caption.setAttribute('aria-label', 'Adaugă o descriere');
      caption.setAttribute('contenteditable', 'true');
      caption.setAttribute('role', 'textbox');
      wireEditable(caption);
      preview.append(caption);
    }
    const sendPreviewBtn = document.createElement('button');
    sendPreviewBtn.type = 'button';
    sendPreviewBtn.setAttribute('aria-label', 'Trimite');
    sendPreviewBtn.addEventListener('click', () => { wa.sendClicks += 1; });
    preview.append(sendPreviewBtn);
    (document.querySelector('#main') || document.body).append(preview);
  }

  if (composer) {
    wireEditable(composer, { allowFilePaste: true });
    composer.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && !event.shiftKey) {
        wa.enterKeys += 1;
        event.preventDefault();
        send();
      }
    });
    document.querySelector('footer button[aria-label="Trimite"]').addEventListener('click', () => {
      wa.sendClicks += 1;
      send();
    });
  }

  // Images arrive as blob: URLs, like media WhatsApp has already loaded.
  function makeLogoBlob() {
    const canvas = document.createElement('canvas');
    canvas.width = 240;
    canvas.height = 150;
    const ctx = canvas.getContext('2d');
    ctx.fillStyle = '#f4f1ea';
    ctx.fillRect(0, 0, 240, 150);
    ctx.fillStyle = '#00745f';
    ctx.beginPath();
    ctx.arc(120, 75, 48, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 20px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('LOGO', 120, 82);
    const base64 = canvas.toDataURL('image/png').split(',')[1];
    const binary = atob(base64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
    return new Blob([bytes], { type: 'image/png' });
  }

  const fixtureImgs = [...document.querySelectorAll('img[data-fixture-blob]')];
  if (fixtureImgs.length) {
    const logoBlob = makeLogoBlob();
    wa.imagesReady = Promise.all(
      fixtureImgs.map(
        (img) =>
          new Promise((resolve) => {
            img.addEventListener('load', () => resolve(), { once: true });
            img.addEventListener('error', () => resolve(), { once: true });
            img.src = URL.createObjectURL(logoBlob);
            if (img.complete) resolve();
          }),
      ),
    );
  } else {
    wa.imagesReady = Promise.resolve();
  }

  let counter = 0;
  const addMessage = (direction, text, jid) => {
    counter += 1;
    const list = document.querySelector('#main [role="application"]');
    const remote = jid || (document.querySelector('#main [data-id]')?.getAttribute('data-id') || '').split('_')[1];
    const row = document.createElement('div');
    row.setAttribute('role', 'row');
    const node = document.createElement('div');
    node.setAttribute('data-id', `${direction === 'out'}_${remote}_3EB0FIXTURE${counter}`);
    const bubble = document.createElement('div');
    bubble.className = direction === 'out' ? 'message-out' : 'message-in';
    const copyable = document.createElement('div');
    copyable.className = 'copyable-text';
    copyable.setAttribute('data-pre-plain-text', `[10:3${counter}, 26.11.2026] ${direction === 'out' ? 'Etichete Creative' : 'Client'}: `);
    const span = document.createElement('span');
    span.className = 'selectable-text copyable-text';
    span.setAttribute('dir', 'ltr');
    span.append(Object.assign(document.createElement('span'), { textContent: text }));
    copyable.append(span);
    bubble.append(copyable);
    node.append(bubble);
    row.append(node);
    list.append(row);
  };
  wa.addIncoming = (text) => addMessage('in', text);
  wa.addOutgoing = (text) => addMessage('out', text);
})();
