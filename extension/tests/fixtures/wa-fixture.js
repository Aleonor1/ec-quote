// Fake editor and helpers for the fixture pages. Records anything that would be a send.
(() => {
  const wa = (window.__wa = { sent: [], sendClicks: 0, enterKeys: 0, pastes: 0 });
  if (new URLSearchParams(location.search).get('theme') === 'dark') document.body.classList.add('dark');

  const composer = document.querySelector('footer [contenteditable="true"]');
  const readText = () => (composer ? composer.innerText.replace(/\n$/, '') : '');
  const send = () => {
    wa.sent.push(readText());
    composer.replaceChildren(document.createElement('p'));
  };

  if (composer) {
    // Like Lexical: take plain text from the paste event and insert it at the selection.
    composer.addEventListener('paste', (event) => {
      event.preventDefault();
      wa.pastes += 1;
      const text = event.clipboardData.getData('text/plain');
      const selection = getSelection();
      if (!selection.rangeCount || !composer.contains(selection.anchorNode)) {
        selection.selectAllChildren(composer);
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
    });
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
  wa.imagesReady = Promise.all(
    [...document.querySelectorAll('img[data-fixture-blob]')].map(
      (img) =>
        new Promise((resolve) => {
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
          canvas.toBlob((blob) => {
            img.addEventListener('load', resolve, { once: true });
            img.src = URL.createObjectURL(blob);
          }, 'image/png');
        }),
    ),
  );

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
