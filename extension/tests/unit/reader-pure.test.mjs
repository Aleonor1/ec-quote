// DOM-free helpers of the WhatsApp reader. DOM parsing is covered in tests/browser.
import test from 'node:test';
import assert from 'node:assert/strict';
import '../../content/selectors.js';

const { Reader } = globalThis.EcQuote;

test('parseDataId reads direction, chat id and phone', () => {
  const individual = Reader.parseDataId('false_40722123456@c.us_3EB0C1A2B3C4');
  assert.equal(individual.fromMe, false);
  assert.equal(individual.jid, '40722123456@c.us');
  assert.equal(individual.phoneDigits, '40722123456');
  assert.equal(individual.isGroup, false);
  assert.equal(individual.messageId, '3EB0C1A2B3C4');

  const group = Reader.parseDataId('true_120363041234567890@g.us_3EB0AA_40733111222@c.us');
  assert.equal(group.fromMe, true);
  assert.equal(group.isGroup, true);
  assert.equal(group.participant, '40733111222@c.us');
  assert.equal(group.phoneDigits, null);

  const lid = Reader.parseDataId('false_184467440737095@lid_3A5F00');
  assert.equal(lid.isIndividual, true);
  assert.equal(lid.phoneDigits, null);

  assert.equal(Reader.parseDataId('album-123'), null);
  assert.equal(Reader.parseDataId(''), null);
});

test('parsePrePlainText handles Romanian and English formats', () => {
  const ro = Reader.parsePrePlainText('[10:12, 26.11.2026] Maria Ionescu: ');
  assert.equal(ro.author, 'Maria Ionescu');
  assert.equal(ro.sentAt, new Date(2026, 10, 26, 10, 12).toISOString());

  const en = Reader.parsePrePlainText('[3:05 PM, 11/26/2026] Andrei P.: ');
  assert.equal(en.author, 'Andrei P.');
  assert.equal(en.sentAt, new Date(2026, 10, 26, 15, 5).toISOString());

  const dayFirstSlash = Reader.parsePrePlainText('[09:00, 05/03/2026] Ana: ');
  assert.equal(dayFirstSlash.sentAt, new Date(2026, 2, 5, 9, 0).toISOString());

  const midnight = Reader.parsePrePlainText('[12:30 AM, 1/2/26] X: ');
  assert.equal(midnight.sentAt, new Date(2026, 1, 1, 0, 30).toISOString());

  const iso = Reader.parsePrePlainText('[18:45, 2026-11-26] Y: ');
  assert.equal(iso.sentAt, new Date(2026, 10, 26, 18, 45).toISOString());
});

test('parsePrePlainText returns null time for unknown formats', () => {
  assert.deepEqual(Reader.parsePrePlainText(''), { sentAt: null, author: '' });
  assert.equal(Reader.parsePrePlainText('[ieri] Maria: ').sentAt, null);
  assert.equal(Reader.parsePrePlainText('[10:12, 31.02.2026] Maria: ').sentAt, null);
  assert.equal(Reader.parsePrePlainText('[25:99, 26.11.2026] Maria: ').sentAt, null);
});

test('phoneFromTitle only accepts titles that are phone numbers', () => {
  assert.equal(Reader.phoneFromTitle('+40 722 123 456'), '40722123456');
  assert.equal(Reader.phoneFromTitle('+40 (722) 123-456'), '40722123456');
  assert.equal(Reader.phoneFromTitle('Maria Ionescu'), null);
  assert.equal(Reader.phoneFromTitle('Comanda 1042'), null);
  assert.equal(Reader.phoneFromTitle('12345'), null);
});

test('toApiMessage folds quoted context, placeholders and upload ids', () => {
  const uploads = new Map([['m2', 'up_1']]);
  assert.deepEqual(
    Reader.toApiMessage({ id: 'm1', direction: 'in', text: 'Hârtie', sent_at: null, quoted: 'Ce material?', attachment: null }, uploads),
    { id: 'm1', direction: 'in', text: '[Răspuns la: "Ce material?"]\nHârtie', sent_at: null, attachments: [] },
  );
  assert.deepEqual(
    Reader.toApiMessage({ id: 'm2', direction: 'in', text: '', sent_at: 'x', quoted: null, attachment: { type: 'image', name: '' } }, uploads),
    { id: 'm2', direction: 'in', text: '[imagine]', sent_at: 'x', attachments: [{ upload_id: 'up_1' }] },
  );
  assert.equal(
    Reader.toApiMessage({ id: 'm3', direction: 'in', text: '', sent_at: null, quoted: null, attachment: { type: 'document', name: 'a.pdf' } }, uploads).text,
    '[document] a.pdf',
  );
});

test('hashText is stable and cleanText strips direction marks', () => {
  assert.equal(Reader.hashText('Maria'), Reader.hashText('Maria'));
  assert.notEqual(Reader.hashText('Maria'), Reader.hashText('Mario'));
  assert.equal(Reader.cleanText('‎Bună ziua  \n\n\n\nLa revedere '), 'Bună ziua\n\nLa revedere');
});
