// Test harness: fixture pages served as https://web.whatsapp.com, a mock backend, and
// a Chromium profile with the unpacked extension loaded. Nothing reaches the real WhatsApp.
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
import fs from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';

const require = createRequire(import.meta.url);
export const { chromium } = require('playwright');

const here = path.dirname(fileURLToPath(import.meta.url));
export const EXTENSION_DIR = path.resolve(here, '..', '..');
export const FIXTURES_DIR = path.resolve(here, '..', 'fixtures');
export const SCREENSHOT_DIR = path.resolve(EXTENSION_DIR, 'screenshots');
export const WHATSAPP = 'https://web.whatsapp.com';
export const TOKEN = 'test-token-0123456789';

const TYPES = { '.html': 'text/html; charset=utf-8', '.css': 'text/css', '.js': 'text/javascript', '.png': 'image/png' };

// Serve tests/fixtures as the WhatsApp Web origin.
export async function routeFixtures(context) {
  await context.route(`${WHATSAPP}/**`, async (route) => {
    const url = new URL(route.request().url());
    const name = path.basename(url.pathname) || 'chat-individual.html';
    try {
      const body = await fs.readFile(path.join(FIXTURES_DIR, name));
      await route.fulfill({ status: 200, contentType: TYPES[path.extname(name)] || 'application/octet-stream', body });
    } catch {
      await route.fulfill({ status: 404, body: 'not found' });
    }
  });
}

export const OFFER_SUGGESTION = {
  suggestion_id: 'sug_offer_1',
  kind: 'offer',
  text: 'Bună ziua! Pentru etichete rotunde de 50 mm, pe hârtie lucioasă cu laminare mată, avem următoarele variante:\n\n500 buc: 214,20 lei\n1000 buc: 333,20 lei\n2000 buc: 547,40 lei\n\nPrețurile includ TVA. Termenul de producție este de 3 zile lucrătoare de la confirmarea graficii.',
  options: [],
  image_url: null, // filled in by the mock backend
  note_for_staff: 'Logoul primit are rezoluție bună pentru 50 mm. Clientul a cerut 1000 buc; am adăugat două variante de cantitate.',
  handoff_reason: null,
  offer_lines: [
    { label: 'Etichete rotunde 50 mm', quantity: '500', total_ex_vat: '180.00', total: '214.20', unit_price: '0.3600', highlighted: false },
    { label: 'Etichete rotunde 50 mm', quantity: '1000', total_ex_vat: '280.00', total: '333.20', unit_price: '0.2800', highlighted: true },
    { label: 'Etichete rotunde 50 mm', quantity: '2000', total_ex_vat: '460.00', total: '547.40', unit_price: '0.2300', highlighted: false },
  ],
  can_create_payment_link: true,
  payment_url: null,
};

export const QUESTION_SUGGESTION = {
  suggestion_id: 'sug_question_1',
  kind: 'question',
  text: 'Mulțumim pentru detalii! Ce formă doriți pentru etichete?',
  options: ['Rotundă', 'Pătrată', 'Dreptunghiulară'],
  image_url: null,
  note_for_staff: '',
  handoff_reason: null,
  offer_lines: [],
  can_create_payment_link: false,
  payment_url: null,
};

// Mock of the ec-quote assist API. It sends CORS headers because the test profile has
// no granted host permission for 127.0.0.1 (that prompt needs a person).
export async function startMockBackend() {
  const state = { requests: [], suggest: null, suggestDelayMs: 0, minExtensionVersion: '', requireUpdate: false };
  const offerPng = await fs.readFile(path.join(FIXTURES_DIR, 'offer.png'));

  const server = http.createServer(async (req, res) => {
    const chunks = [];
    for await (const chunk of req) chunks.push(chunk);
    const raw = Buffer.concat(chunks);
    const url = new URL(req.url, 'http://127.0.0.1');
    const cors = {
      'Access-Control-Allow-Origin': req.headers.origin || '*',
      'Access-Control-Allow-Headers': 'content-type, x-ecquote-assist-token, x-ecquote-extension-version',
      'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
    };
    if (req.method === 'OPTIONS') return res.writeHead(204, cors).end();

    const record = {
      method: req.method,
      path: url.pathname,
      token: req.headers['x-ecquote-assist-token'] || null,
      version: req.headers['x-ecquote-extension-version'] || null,
      body: null,
      raw,
    };
    if ((req.headers['content-type'] || '').includes('application/json')) record.body = JSON.parse(raw.toString('utf8') || 'null');
    state.requests.push(record);

    const send = (status, body) => res.writeHead(status, { ...cors, 'Content-Type': 'application/json' }).end(JSON.stringify(body));
    const base = `http://127.0.0.1:${server.address().port}`;

    if (url.pathname === '/offer.png') return res.writeHead(200, { ...cors, 'Content-Type': 'image/png' }).end(offerPng);
    if (record.token !== TOKEN) return send(401, { error: { code: 'invalid_token', message: 'raw backend text that must not be shown' } });
    if (url.pathname === '/v1/assist/ping') {
      return send(200, {
        ok: true,
        staff: 'Ioana',
        backend_version: '0.1.0',
        min_extension_version: state.minExtensionVersion,
      });
    }
    if (state.requireUpdate) {
      return send(426, { error: { code: 'extension_update_required', message: 'update', min_extension_version: '9.0.0' } });
    }
    if (url.pathname === '/v1/assist/suggest') {
      if (state.suggestDelayMs) await new Promise((resolve) => setTimeout(resolve, state.suggestDelayMs));
      const reply = state.suggest ? state.suggest(record.body, base) : { status: 200, body: { suggestion: { ...OFFER_SUGGESTION, image_url: `${base}/offer.png` } } };
      return send(reply.status, reply.body);
    }
    if (url.pathname === '/v1/assist/upload') return send(200, { upload_id: 'up_test_1' });
    const payment = /^\/v1\/assist\/suggestions\/([^/]+)\/payment-link$/.exec(url.pathname);
    if (payment) {
      const text = (record.body && record.body.edited_text) || OFFER_SUGGESTION.text;
      return send(200, {
        suggestion: {
          ...OFFER_SUGGESTION,
          image_url: `${base}/offer.png`,
          text: `${text}\n\nPuteți plăti comanda aici: https://etichetecreative.ro/plata/test-123`,
          can_create_payment_link: false,
          payment_url: 'https://etichetecreative.ro/plata/test-123',
        },
      });
    }
    return send(404, { error: { code: 'not_found', message: 'no such route' } });
  });
  await new Promise((resolve) => server.listen(0, '127.0.0.1', resolve));
  return {
    state,
    offerPng,
    url: `http://127.0.0.1:${server.address().port}`,
    close: () => new Promise((resolve) => server.close(resolve)),
  };
}

// Chromium with the unpacked extension. Extensions need a persistent context.
export async function launchWithExtension({ viewport = { width: 1360, height: 820 } } = {}) {
  const userDataDir = await fs.mkdtemp(path.join(os.tmpdir(), 'ecq-ext-'));
  const context = await chromium.launchPersistentContext(userDataDir, {
    channel: 'chromium',
    headless: true,
    viewport,
    args: [`--disable-extensions-except=${EXTENSION_DIR}`, `--load-extension=${EXTENSION_DIR}`],
  });
  await routeFixtures(context);
  let [worker] = context.serviceWorkers();
  if (!worker) worker = await context.waitForEvent('serviceworker', { timeout: 15_000 });
  const extensionId = new URL(worker.url()).host;
  // Wait briefly for onInstalled's options tab if opened, and close stray options tabs so tests stay isolated.
  await new Promise((resolve) => setTimeout(resolve, 120));
  for (const p of context.pages()) {
    if (p.url().startsWith(`chrome-extension://${extensionId}/`)) await p.close().catch(() => {});
  }
  const configure = async (settings) => {
    const sw = context.serviceWorkers()[0] || (await context.waitForEvent('serviceworker'));
    await sw.evaluate((values) => chrome.storage.local.set(values), settings);
  };
  const close = async () => {
    await context.close();
    await fs.rm(userDataDir, { recursive: true, force: true });
  };
  return { context, extensionId, configure, close };
}

export async function launchPlain() {
  const browser = await chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1200, height: 800 } });
  await routeFixtures(context);
  return { browser, context, close: () => browser.close() };
}
