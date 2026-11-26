// Message parser against the saved HTML fixtures (hand-written approximations of
// WhatsApp Web's markup). Runs the real content/selectors.js in Chromium.
import test, { after, before } from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import { EXTENSION_DIR, WHATSAPP, launchPlain } from '../helpers/harness.mjs';

let session;
before(async () => {
  session = await launchPlain();
});
after(async () => {
  await session.close();
});

async function read(fixture) {
  const page = await session.context.newPage();
  await page.goto(`${WHATSAPP}/${fixture}`);
  await page.evaluate(() => window.__wa.imagesReady);
  await page.addScriptTag({ path: path.join(EXTENSION_DIR, 'content', 'selectors.js') });
  const result = await page.evaluate(() => {
    const { Reader } = window.EcQuote;
    const convo = Reader.readConversation();
    return {
      convo: {
        ...convo,
        messages: convo.messages.map(({ attachment, parsed, ...rest }) => ({
          ...rest,
          attachment: attachment ? { type: attachment.type, name: attachment.name, src: attachment.src, hasEl: Boolean(attachment.el) } : null,
        })),
      },
      selfTest: Reader.selfTest(),
      composerFound: Boolean(Reader.findComposer()),
    };
  });
  await page.close();
  return result;
}

test('individual chat: title, phone, key and every message field', async () => {
  const { convo, selfTest, composerFound } = await read('chat-individual.html');
  assert.equal(convo.open, true);
  assert.equal(convo.group, false);
  assert.equal(convo.supported, true);
  assert.deepEqual(convo.chat, { key: '40722123456', name: 'Maria Ionescu', phone: '+40722123456' });
  assert.equal(convo.messages.length, 4, 'the date divider is not a message');

  const [first, second, third, fourth] = convo.messages;
  assert.equal(first.id, 'false_40722123456@c.us_3EB0C1A2B3C4D5E6F7A8');
  assert.equal(first.direction, 'in');
  assert.equal(first.text, 'Bună ziua! Aș dori o ofertă pentru etichete rotunde de 50 mm.\nCam 1000 de bucăți.');
  assert.equal(first.sent_at, new Date(2026, 10, 26, 10, 12).toISOString());
  assert.equal(first.author, 'Maria Ionescu');
  assert.equal(first.quoted, null);
  assert.equal(first.attachment, null);

  assert.equal(second.direction, 'out');
  assert.equal(second.text, 'Bună ziua! Sigur. Pe ce material le doriți: hârtie lucioasă sau vinil?');
  assert.ok(!second.text.includes('10:14'), 'the time label is not part of the text');

  assert.equal(third.direction, 'in');
  assert.equal(third.text, 'Hârtie lucioasă 🙂 cu laminare mată\nMulțumesc!', 'emoji alt text and <br> are kept');
  assert.equal(third.quoted, 'Pe ce material le doriți: hârtie lucioasă sau vinil?');
  assert.equal(third.attachment, null, 'an emoji image is not an attachment');

  assert.equal(fourth.direction, 'in');
  assert.equal(fourth.text, 'Acesta este logoul');
  assert.equal(fourth.sent_at, null, 'media rows without data-pre-plain-text have no time');
  assert.equal(fourth.attachment.type, 'image');
  assert.match(fourth.attachment.src, /^blob:https:\/\/web\.whatsapp\.com\//);

  assert.equal(composerFound, true);
  assert.equal(selfTest.status, 'ok');
  assert.deepEqual(selfTest.failed, []);
});

test('group chat is detected and not supported', async () => {
  const { convo } = await read('chat-group.html');
  assert.equal(convo.open, true);
  assert.equal(convo.group, true);
  assert.equal(convo.supported, false);
  assert.equal(convo.chat.name, 'Echipa producție');
});

test('chat without a visible number: stable id as key, phone null, document attachment', async () => {
  const { convo, selfTest } = await read('chat-lid.html');
  assert.equal(convo.group, false);
  assert.equal(convo.supported, true);
  assert.deepEqual(convo.chat, { key: '184467440737095@lid', name: 'Andrei P.', phone: null });
  assert.equal(convo.messages.length, 2);
  assert.equal(convo.messages[0].sent_at, new Date(2026, 10, 26, 15, 5).toISOString());
  const doc = convo.messages[1];
  assert.equal(doc.text, '');
  assert.equal(doc.attachment.type, 'document');
  assert.equal(doc.attachment.name, 'eticheta-vin.pdf');
  assert.equal(doc.attachment.src, null, 'no blob without clicking download');
  assert.equal(selfTest.status, 'ok');
});

test('no open chat: nothing is read and the self-test says so', async () => {
  const { convo, selfTest, composerFound } = await read('no-chat.html');
  assert.equal(convo.open, false);
  assert.deepEqual(convo.messages, []);
  assert.equal(composerFound, false);
  assert.equal(selfTest.status, 'no_chat');
});

test('self-test reports "check" with the failing parts when the markup changes', async () => {
  const page = await session.context.newPage();
  await page.goto(`${WHATSAPP}/chat-individual.html`);
  await page.addScriptTag({ path: path.join(EXTENSION_DIR, 'content', 'selectors.js') });
  const result = await page.evaluate(() => {
    // Simulate a WhatsApp update that renames the attributes the reader relies on.
    for (const node of document.querySelectorAll('#main [data-id]')) {
      node.setAttribute('data-msg', node.getAttribute('data-id'));
      node.removeAttribute('data-id');
    }
    const box = document.querySelector('footer [contenteditable]');
    box.removeAttribute('data-lexical-editor');
    box.removeAttribute('contenteditable');
    return window.EcQuote.Reader.selfTest();
  });
  await page.close();
  assert.equal(result.status, 'check');
  assert.ok(result.failed.includes('Rândurile de mesaj'));
  assert.ok(result.failed.includes('Caseta de mesaj'));
  assert.ok(!result.failed.includes('Titlul conversației'));
});
