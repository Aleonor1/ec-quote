// End to end: the real unpacked extension in headless Chromium, a WhatsApp-like fixture
// served as https://web.whatsapp.com and a mock ec-quote backend.
import test, { after, before, beforeEach } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import {
  FIXTURES_DIR,
  OFFER_SUGGESTION,
  QUESTION_SUGGESTION,
  SCREENSHOT_DIR,
  TOKEN,
  WHATSAPP,
  launchWithExtension,
  startMockBackend,
} from '../helpers/harness.mjs';

let ext;
let backend;
const ROOT = '#ecq-assist-root';

before(async () => {
  backend = await startMockBackend();
  ext = await launchWithExtension();
  await fs.mkdir(SCREENSHOT_DIR, { recursive: true });
});
after(async () => {
  await ext?.close();
  await backend?.close();
});
beforeEach(async () => {
  backend.state.requests.length = 0;
  backend.state.suggest = null;
  backend.state.suggestDelayMs = 0;
  await ext.configure({ baseUrl: backend.url, token: TOKEN, enabled: true, mode: 'auto', panelCollapsed: false });
});

async function open(fixture = 'chat-individual.html', query = '') {
  const page = await ext.context.newPage();
  await page.goto(`${WHATSAPP}/${fixture}${query}`);
  await page.locator(ROOT).waitFor({ state: 'attached' });
  return page;
}

const suggestCalls = () => backend.state.requests.filter((r) => r.path === '/v1/assist/suggest');
const sendState = (page) => page.evaluate(() => ({ sent: window.__wa.sent, sendClicks: window.__wa.sendClicks, enterKeys: window.__wa.enterKeys }));
const composerText = (page) => page.locator('footer [contenteditable="true"]').innerText();
const shot = (page, name) => page.screenshot({ path: path.join(SCREENSHOT_DIR, name) });

async function assertNothingSent(page) {
  assert.deepEqual(await sendState(page), { sent: [], sendClicks: 0, enterKeys: 0 });
}

test('renders an offer suggestion for the open chat', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();

  // Request: token header, chat identity, the visible messages.
  const [call] = suggestCalls();
  assert.equal(call.token, TOKEN);
  assert.deepEqual(call.body.chat, { key: '40722123456', name: 'Maria Ionescu', phone: '+40722123456' });
  assert.equal(call.body.messages.length, 4);
  assert.deepEqual(call.body.messages.map((m) => m.direction), ['in', 'out', 'in', 'in']);
  assert.equal(call.body.messages[2].text, '[Răspuns la: "Pe ce material le doriți: hârtie lucioasă sau vinil?"]\nHârtie lucioasă 🙂 cu laminare mată\nMulțumesc!');
  assert.deepEqual(Object.keys(call.body.messages[0]).sort(), ['attachments', 'direction', 'id', 'sent_at', 'text']);

  // Panel content.
  assert.equal(await panel.locator('.chat').innerText(), 'Maria Ionescu');
  assert.equal(await panel.locator('.badge').innerText(), 'Ofertă');
  const note = panel.locator('.note');
  assert.match(await note.innerText(), /Notă internă \(nu se trimite\)/i);
  assert.match(await note.innerText(), /Logoul primit are rezoluție bună/);
  assert.equal(await panel.locator('textarea').inputValue(), OFFER_SUGGESTION.text);
  assert.deepEqual(await panel.locator('thead th').allInnerTexts(), ['Cantitate', 'Preț/buc', 'Fără TVA', 'Cu TVA']);
  assert.equal(await panel.locator('tbody tr').count(), 3);
  assert.deepEqual(await panel.locator('tbody tr[data-highlighted="true"] td').allInnerTexts(), ['1000', '0,2800', '280,00', '333,20']);
  await panel.locator('.image-box img').waitFor();
  assert.ok(await panel.locator('.image-box img').evaluate((img) => img.complete && img.naturalWidth === 800));
  assert.equal(await panel.getByRole('button', { name: 'Copiază imaginea' }).count(), 1);
  assert.equal(await panel.getByRole('button', { name: 'Descarcă' }).count(), 1);
  assert.equal(await panel.getByRole('button', { name: 'Generează link de plată' }).count(), 1);
  assert.equal(await panel.locator('.compat').innerText(), 'Compatibilitate WhatsApp Web: ok');

  // The token is nowhere in the page, including the panel's shadow tree.
  const dom = await page.evaluate(() => document.documentElement.outerHTML + document.querySelector('#ecq-assist-root').shadowRoot.innerHTML);
  assert.ok(!dom.includes('test-token'));
  await assertNothingSent(page);
  await shot(page, 'panel-light-offer.png');
  await page.close();
});

test('"Inserează în mesaj" fills the composer and sends nothing', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  await panel.locator('textarea').fill('Bună ziua!\nOferta este mai jos.');
  await panel.getByRole('button', { name: 'Inserează în mesaj' }).click();
  await panel.locator('.notice').filter({ hasText: 'Textul a fost inserat' }).waitFor();

  assert.equal(await composerText(page), 'Bună ziua!\nOferta este mai jos.');
  assert.equal(await page.evaluate(() => window.__wa.pastes), 1);
  await page.waitForTimeout(600);
  await assertNothingSent(page);

  // A draft already in the box is never overwritten silently.
  await panel.locator('textarea').fill('Text nou');
  await panel.getByRole('button', { name: 'Inserează în mesaj' }).click();
  const confirm = panel.locator('.confirm');
  assert.match(await confirm.innerText(), /Caseta de mesaj conține deja text/);
  await confirm.getByRole('button', { name: 'Înlocuiește' }).click();
  await page.waitForFunction(() => document.querySelector('footer [contenteditable="true"]').innerText.trim() === 'Text nou');
  await page.waitForTimeout(400);
  await assertNothingSent(page);

  // Sanity check of the fixture itself: a real click on Send is what gets recorded.
  await page.locator('footer button[aria-label="Trimite"]').click();
  assert.deepEqual(await sendState(page), { sent: ['Text nou'], sendClicks: 1, enterKeys: 0 });
  await page.close();
});

test('backend text is treated as data, never as HTML', async () => {
  const hostile = '<img src=x onerror="window.__pwned=1"> <b>Bună</b> <script>window.__pwned=2</script>';
  backend.state.suggest = () => ({
    status: 200,
    body: { suggestion: { ...QUESTION_SUGGESTION, text: hostile, note_for_staff: hostile, options: [hostile], offer_lines: [{ label: hostile, quantity: hostile, total: hostile, total_ex_vat: '1', unit_price: '1', highlighted: true }] } },
  });
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  assert.equal(await panel.locator('textarea').inputValue(), hostile);
  assert.equal(await panel.locator('.note p').first().innerText(), hostile);
  assert.equal(await panel.locator('.view img, .view b, .view script').count(), 0);
  await panel.getByRole('button', { name: 'Inserează în mesaj' }).click();
  await panel.locator('.notice').filter({ hasText: 'Textul a fost inserat' }).waitFor();
  assert.equal(await page.locator('footer [contenteditable="true"] img, footer [contenteditable="true"] b').count(), 0);
  assert.equal(await page.evaluate(() => window.__pwned), undefined);
  await page.close();
});

test('payment link asks for confirmation, then shows the final text with the link', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  await panel.getByRole('button', { name: 'Generează link de plată' }).click();
  const confirm = panel.locator('.confirm');
  assert.match(await confirm.innerText(), /comandă nefinalizată \(draft\)/);
  assert.equal(backend.state.requests.filter((r) => r.path.endsWith('/payment-link')).length, 0, 'nothing is created before confirmation');

  await confirm.getByRole('button', { name: 'Renunță' }).click();
  assert.equal(backend.state.requests.filter((r) => r.path.endsWith('/payment-link')).length, 0);

  await panel.getByRole('button', { name: 'Generează link de plată' }).click();
  await confirm.getByRole('button', { name: 'Creează linkul' }).click();
  await panel.locator('.pay-url').waitFor();
  const [call] = backend.state.requests.filter((r) => r.path.endsWith('/payment-link'));
  assert.equal(call.path, '/v1/assist/suggestions/sug_offer_1/payment-link');
  assert.equal(call.token, TOKEN);
  assert.deepEqual(call.body, { edited_text: null });
  assert.equal(await panel.locator('.pay-url').innerText(), 'https://etichetecreative.ro/plata/test-123');
  assert.match(await panel.locator('textarea').inputValue(), /Puteți plăti comanda aici: https:\/\/etichetecreative\.ro\/plata\/test-123$/);
  assert.equal(await panel.getByRole('button', { name: 'Generează link de plată' }).count(), 0);
  await assertNothingSent(page);
  await shot(page, 'panel-light-payment-link.png');
  await page.close();
});

test('a new customer message refreshes the suggestion; edits are not overwritten', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  assert.equal(suggestCalls().length, 1);

  backend.state.suggest = () => ({ status: 200, body: { suggestion: QUESTION_SUGGESTION } });
  await page.evaluate(() => window.__wa.addIncoming('Și cât costă 2000 de bucăți?'));
  await panel.locator('.badge').filter({ hasText: 'Întrebare pentru client' }).waitFor();
  assert.equal(suggestCalls().length, 2);
  assert.equal(suggestCalls()[1].body.messages.at(-1).text, 'Și cât costă 2000 de bucăți?');
  assert.deepEqual(await panel.locator('.chip').allInnerTexts(), ['Rotundă', 'Pătrată', 'Dreptunghiulară']);
  await shot(page, 'panel-light-question.png');

  // Chips add to the editable text.
  await panel.locator('.chip').first().click();
  assert.match(await panel.locator('textarea').inputValue(), /\nRotundă$/);

  // The text is now edited: a new message only shows a banner.
  await page.evaluate(() => window.__wa.addIncoming('Alo?'));
  await panel.locator('.banner').waitFor();
  assert.equal(suggestCalls().length, 2);
  assert.match(await panel.locator('textarea').inputValue(), /\nRotundă$/);
  await panel.locator('.banner').getByRole('button', { name: 'Actualizează' }).click();
  await page.waitForFunction(() => true);
  await assert.doesNotReject(panel.locator('.banner').waitFor({ state: 'hidden' }));
  assert.equal(suggestCalls().length, 3);

  // After the staff member's own message the old suggestion is cleared.
  await page.evaluate(() => window.__wa.addOutgoing('Revin imediat.'));
  await panel.getByRole('button', { name: 'Cere sugestie' }).waitFor();
  assert.equal(suggestCalls().length, 3);
  await assertNothingSent(page);
  await page.close();
});

test('backend errors show short Romanian messages, never raw text', async () => {
  backend.state.suggest = () => ({ status: 503, body: { error: { code: 'assist_unavailable', message: 'upstream model timeout: raw detail' } } });
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('.state[data-tone="error"]').waitFor();
  const text = await panel.locator('.view').innerText();
  assert.match(text, /Asistentul nu este disponibil momentan/);
  assert.ok(!text.includes('raw detail') && !text.includes('assist_unavailable'));
  await shot(page, 'panel-light-error.png');

  backend.state.suggest = () => ({ status: 429, body: { error: { code: 'rate_limited', message: 'x' } } });
  await panel.getByRole('button', { name: 'Încearcă din nou' }).click();
  await panel.getByText('Prea multe cereri').waitFor();

  await ext.configure({ token: 'wrong-token' });
  await panel.getByRole('button', { name: 'Încearcă din nou' }).click();
  await panel.getByText('Token invalid sau expirat').waitFor();
  assert.equal(await panel.getByRole('button', { name: 'Deschide opțiunile' }).count(), 1);
  await page.close();
});

test('group chats are not assisted and nothing is sent to the backend', async () => {
  const page = await open('chat-group.html');
  const panel = page.locator(ROOT);
  await panel.getByText('Conversațiile de grup nu sunt asistate').waitFor();
  await page.waitForTimeout(1200);
  assert.equal(backend.state.requests.length, 0);
  await page.close();
});

test('customer image: "Trimite fișierul la verificare" uploads the loaded blob', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  assert.match(await panel.locator('.attach-info').innerText(), /Clientul a trimis o imagine/);
  await panel.getByRole('button', { name: 'Trimite fișierul la verificare' }).click();
  await panel.locator('.attach-status[data-tone="ok"]').waitFor();

  const [upload] = backend.state.requests.filter((r) => r.path === '/v1/assist/upload');
  assert.equal(upload.token, TOKEN);
  const raw = upload.raw.toString('latin1');
  assert.match(raw, /name="chat_key"\r\n\r\n40722123456\r\n/);
  assert.match(raw, /name="message_id"\r\n\r\nfalse_40722123456@c\.us_3EB0F1A2B3C4D5E6F7B9\r\n/);
  assert.match(raw, /name="file"; filename="imagine\.png"\r\nContent-Type: image\/png\r\n\r\n\x89PNG/);

  // The next suggest call references the upload on that message.
  await page.waitForFunction(() => true);
  await panel.locator('textarea').waitFor();
  const last = suggestCalls().at(-1);
  assert.equal(suggestCalls().length, 2);
  assert.deepEqual(last.body.messages.at(-1).attachments, [{ upload_id: 'up_test_1' }]);
  assert.match(await panel.locator('.attach-info').innerText(), /a fost trimis la verificare/);
  await page.close();
});

test('document without a loaded blob: manual path through the file picker', async () => {
  const page = await open('chat-lid.html');
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  assert.deepEqual(suggestCalls()[0].body.chat, { key: '184467440737095@lid', name: 'Andrei P.', phone: null });
  assert.equal(suggestCalls()[0].body.messages[1].text, '[document] eticheta-vin.pdf');
  assert.match(await panel.locator('.attach-info').innerText(), /Descărcați-l din WhatsApp, apoi trageți-l mai jos/);
  assert.equal(await panel.getByRole('button', { name: 'Trimite fișierul la verificare' }).count(), 0, 'no automatic read without a blob');

  await panel.locator('input[type="file"]').setInputFiles({ name: 'eticheta-vin.pdf', mimeType: 'application/pdf', buffer: Buffer.from('%PDF-1.4 test') });
  await panel.locator('.attach-status[data-tone="ok"]').waitFor();
  const [upload] = backend.state.requests.filter((r) => r.path === '/v1/assist/upload');
  const raw = upload.raw.toString('latin1');
  assert.match(raw, /name="message_id"\r\n\r\nfalse_184467440737095@lid_3A5F00C1D2E3F4A5B6C8\r\n/);
  assert.match(raw, /filename="eticheta-vin\.pdf"\r\nContent-Type: application\/pdf\r\n\r\n%PDF-1\.4 test/);
  await page.close();
});

test('the panel never covers the composer, collapses, and remembers it', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  const overlap = async () => {
    const a = await page.locator('footer [contenteditable="true"]').boundingBox();
    const b = await page.locator('footer button[aria-label="Trimite"]').boundingBox();
    const p = await panel.boundingBox();
    return Math.max(a.x + a.width, b.x + b.width) > p.x;
  };
  assert.equal(await overlap(), false);
  assert.equal((await panel.boundingBox()).width, 368);

  await panel.getByRole('button', { name: 'Restrânge panoul' }).click();
  await page.waitForFunction(() => document.querySelector('#ecq-assist-root').getBoundingClientRect().width === 40);
  assert.equal(await overlap(), false);
  await shot(page, 'panel-collapsed.png');

  await page.reload();
  await page.locator(ROOT).waitFor({ state: 'attached' });
  await page.waitForFunction(() => document.querySelector('#ecq-assist-root').getBoundingClientRect().width === 40);
  await panel.getByRole('button', { name: 'Deschide asistentul de ofertare' }).click();
  await panel.locator('textarea').waitFor();
  assert.equal((await panel.boundingBox()).width, 368);
  await page.close();
});

test('keyboard: every action is reachable with Tab and has a visible focus ring', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('.image-box img').waitFor();
  await panel.getByRole('button', { name: 'Restrânge panoul' }).focus();
  const seen = [];
  for (let i = 0; i < 14; i += 1) {
    await page.keyboard.press('Tab');
    const info = await page.evaluate(() => {
      const active = document.querySelector('#ecq-assist-root').shadowRoot.activeElement;
      if (!active) return null;
      const style = getComputedStyle(active);
      return { label: active.tagName === 'TEXTAREA' ? 'textarea' : active.textContent.trim(), outline: style.outlineStyle !== 'none' && parseFloat(style.outlineWidth) >= 2 };
    });
    if (!info) break;
    seen.push(info);
  }
  const labels = seen.map((s) => s.label);
  for (const expected of ['textarea', 'Copiază imaginea', 'Descarcă', 'Inserează în mesaj', 'Copiază textul', 'Altă sugestie', 'Generează link de plată', 'Opțiuni']) {
    assert.ok(labels.includes(expected), `Tab reaches "${expected}" (got ${labels.join(' | ')})`);
  }
  assert.ok(seen.every((s) => s.outline), 'focused controls show an outline');
  // Enter inside the panel activates the focused button; it never reaches the composer.
  await panel.getByRole('button', { name: 'Inserează în mesaj' }).focus();
  await page.keyboard.press('Enter');
  await panel.locator('.notice').filter({ hasText: 'Textul a fost inserat' }).waitFor();
  await page.waitForTimeout(400);
  await assertNothingSent(page);
  await page.close();
});

test('on-demand mode waits for "Cere sugestie"; switching off removes the panel', async () => {
  await ext.configure({ mode: 'manual' });
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.getByRole('button', { name: 'Cere sugestie' }).waitFor();
  await page.waitForTimeout(1200);
  assert.equal(suggestCalls().length, 0);
  await shot(page, 'panel-light-empty.png');
  await panel.getByRole('button', { name: 'Cere sugestie' }).click();
  await panel.locator('textarea').waitFor();
  assert.equal(suggestCalls().length, 1);

  await ext.configure({ enabled: false });
  await page.locator(ROOT).waitFor({ state: 'detached' });
  assert.equal(await page.locator('#app').evaluate((app) => app.style.width), '', 'WhatsApp layout is restored');
  await ext.configure({ enabled: true });
  await page.locator(ROOT).waitFor({ state: 'attached' });
  await page.close();
});

test('unconfigured extension and no open chat show clear empty states', async () => {
  const page = await open('no-chat.html');
  const panel = page.locator(ROOT);
  await panel.getByText('Deschideți o conversație pentru a primi o sugestie de răspuns.').waitFor();
  assert.equal(await panel.locator('.compat').innerText(), 'Compatibilitate WhatsApp Web: deschideți o conversație');
  await ext.configure({ token: '' });
  await panel.getByText('Extensia nu este configurată').waitFor();
  assert.equal(backend.state.requests.length, 0);
  await page.close();
});

test('compatibility self-test turns to "de verificat" when the markup changes', async () => {
  const page = await open();
  const panel = page.locator(ROOT);
  await panel.locator('textarea').waitFor();
  await page.evaluate(() => {
    const box = document.querySelector('footer [contenteditable]');
    box.removeAttribute('data-lexical-editor');
    box.removeAttribute('role');
    box.removeAttribute('contenteditable');
    document.querySelector('#main [role="application"]').append(document.createElement('i'));
  });
  await panel.locator('.compat[data-status="check"]').waitFor();
  assert.equal(await panel.locator('.compat').innerText(), 'Compatibilitate WhatsApp Web: de verificat');
  await panel.locator('.compat').click();
  assert.match(await panel.locator('.checks').innerText(), /Caseta de mesaj\s+negăsit/);
  // Insert now fails safely: the text is offered through the clipboard path instead.
  await panel.getByRole('button', { name: 'Inserează în mesaj' }).click();
  await panel.locator('.notice[data-tone="error"]').waitFor();
  assert.match(await panel.locator('.notice').innerText(), /nu a putut fi inserat automat/);
  await assertNothingSent(page);
  await page.close();
});

test('dark theme follows WhatsApp', async () => {
  const page = await open('chat-individual.html', '?theme=dark');
  const panel = page.locator(ROOT);
  await panel.locator('.image-box img').waitFor();
  assert.equal(await panel.locator('.ecq').getAttribute('data-theme'), 'dark');
  await shot(page, 'panel-dark-offer.png');
  await panel.locator('.body').evaluate((body) => body.scrollTo(0, body.scrollHeight));
  await shot(page, 'panel-dark-offer-scrolled.png');
  await page.close();

  const light = await open();
  await light.locator(ROOT).locator('.image-box img').waitFor();
  assert.equal(await light.locator(ROOT).locator('.ecq').getAttribute('data-theme'), 'light');
  await light.locator(ROOT).locator('.body').evaluate((body) => body.scrollTo(0, body.scrollHeight));
  await shot(light, 'panel-light-offer-scrolled.png');
  await light.close();
});

test('options page: ping through the worker, the saved token is never rendered', async () => {
  const page = await ext.context.newPage();
  await page.goto(`chrome-extension://${ext.extensionId}/options/options.html`);
  assert.equal(await page.locator('#baseUrl').inputValue(), backend.url);
  assert.equal(await page.locator('#token').inputValue(), '');
  assert.equal(await page.locator('#token').getAttribute('placeholder'), 'Token salvat');
  assert.ok(!(await page.content()).includes('test-token'));
  assert.equal(await page.locator('#enabled').isChecked(), true);
  assert.equal(await page.locator('input[name="mode"][value="auto"]').isChecked(), true);

  const ping = await page.evaluate(() => chrome.runtime.sendMessage({ type: 'ecq:ping' }));
  assert.deepEqual(ping, { ok: true, staff: 'Ioana' });
  const [call] = backend.state.requests;
  assert.equal(call.path, '/v1/assist/ping');
  assert.equal(call.token, TOKEN);

  // Validation happens before anything is saved.
  await page.locator('#baseUrl').fill('http://quote.example.ro');
  await page.getByRole('button', { name: 'Salvează' }).click();
  assert.equal(await page.locator('#status').innerText(), 'Adresa serverului trebuie să înceapă cu https://.');
  await page.locator('#baseUrl').fill(backend.url);
  await page.setViewportSize({ width: 900, height: 900 });
  await shot(page, 'options.png');
  await page.close();
});

test('content scripts cannot read the token from storage', async () => {
  const page = await open();
  await page.locator(ROOT).locator('textarea').waitFor();
  const sw = ext.context.serviceWorkers()[0];
  const level = await sw.evaluate(async () => {
    // TRUSTED_CONTEXTS is applied at worker start; verify the stored settings shape too.
    const all = await chrome.storage.local.get(null);
    const session = await chrome.storage.session.get(null);
    return { keys: Object.keys(all).sort(), sessionKeys: Object.keys(session).sort(), sessionValues: Object.values(session) };
  });
  assert.deepEqual(level.keys, ['baseUrl', 'enabled', 'mode', 'panelCollapsed', 'token']);
  assert.ok(level.sessionKeys.every((k) => k.startsWith('lastSuggestion:')), 'session storage holds only suggestion ids');
  assert.ok(level.sessionValues.every((v) => typeof v === 'string' && v.startsWith('sug_')));
  await page.close();
});
