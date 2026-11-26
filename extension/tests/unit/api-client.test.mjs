import test from 'node:test';
import assert from 'node:assert/strict';
import {
  AssistError,
  ERROR_MESSAGES,
  TOKEN_HEADER,
  buildSuggestBody,
  codeForStatus,
  createApiClient,
  normalizeBaseUrl,
  normalizeSuggestion,
} from '../../background/api-client.js';

const TOKEN = 'tok-secret-123';
const json = (status, body) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

function recorder(responder) {
  const calls = [];
  const fetchImpl = async (url, init) => {
    calls.push({ url, init });
    return responder(url, init);
  };
  return { calls, fetchImpl };
}

const client = (fetchImpl, extra = {}) => createApiClient({ baseUrl: 'https://quote.example.ro/', token: TOKEN, fetchImpl, ...extra });

test('normalizeBaseUrl accepts https and loopback http only', () => {
  assert.deepEqual(normalizeBaseUrl(' https://quote.example.ro/api/ '), {
    ok: true,
    base: 'https://quote.example.ro/api',
    origin: 'https://quote.example.ro',
    permissionPattern: 'https://quote.example.ro/*',
  });
  assert.equal(normalizeBaseUrl('http://127.0.0.1:8080').permissionPattern, 'http://127.0.0.1/*');
  assert.equal(normalizeBaseUrl('http://quote.example.ro').reason, 'insecure');
  assert.equal(normalizeBaseUrl('').reason, 'empty');
  assert.equal(normalizeBaseUrl('nu este url').reason, 'invalid');
  assert.equal(normalizeBaseUrl('https://user:pass@quote.example.ro').reason, 'invalid');
});

test('ping sends the token header and returns the staff name', async () => {
  const { calls, fetchImpl } = recorder(() => json(200, { ok: true, staff: 'Ioana' }));
  const result = await client(fetchImpl).ping();
  assert.deepEqual(result, { ok: true, staff: 'Ioana' });
  assert.equal(calls[0].url, 'https://quote.example.ro/v1/assist/ping');
  assert.equal(calls[0].init.method, 'GET');
  assert.equal(calls[0].init.headers[TOKEN_HEADER], TOKEN);
  assert.equal(calls[0].init.credentials, 'omit');
});

test('suggest posts the contract body, capped at the last 40 messages', async () => {
  const { calls, fetchImpl } = recorder(() => json(200, { suggestion: { suggestion_id: 's1', kind: 'reply', text: 'Bună ziua!' } }));
  const messages = Array.from({ length: 55 }, (_, i) => ({
    id: `m${i}`,
    direction: i % 2 ? 'out' : 'in',
    text: `mesaj ${i}`,
    sent_at: null,
    attachments: i === 54 ? [{ upload_id: 'u1', extra: 'x' }, { nope: 1 }] : [],
    author: 'not in the contract',
  }));
  const suggestion = await client(fetchImpl).suggest({ key: '40722123456', name: 'Maria', phone: '+40722123456', extra: 1 }, messages);
  const { url, init } = calls[0];
  assert.equal(url, 'https://quote.example.ro/v1/assist/suggest');
  assert.equal(init.method, 'POST');
  assert.equal(init.headers[TOKEN_HEADER], TOKEN);
  assert.equal(init.headers['Content-Type'], 'application/json');
  const body = JSON.parse(init.body);
  assert.deepEqual(body.chat, { key: '40722123456', name: 'Maria', phone: '+40722123456' });
  assert.equal(body.messages.length, 40);
  assert.equal(body.messages[0].id, 'm15');
  assert.deepEqual(body.messages[39], { id: 'm54', direction: 'in', text: 'mesaj 54', sent_at: null, attachments: [{ upload_id: 'u1' }] });
  assert.equal(suggestion.kind, 'reply');
  assert.equal(suggestion.text, 'Bună ziua!');
  assert.deepEqual(suggestion.options, []);
  assert.equal(suggestion.can_create_payment_link, false);
});

test('buildSuggestBody sends phone null when the number is not visible', () => {
  const body = buildSuggestBody({ key: '1844@lid', name: 'Andrei' }, []);
  assert.deepEqual(body, { chat: { key: '1844@lid', name: 'Andrei', phone: null }, messages: [] });
});

test('normalizeSuggestion keeps money as strings and drops unsafe links', () => {
  const s = normalizeSuggestion({
    suggestion_id: 's2',
    kind: 'something-new',
    text: 42,
    options: ['Hârtie', '', 7, 'Vinil'],
    image_url: 'javascript:alert(1)',
    payment_url: 'https://etichetecreative.ro/pay/1',
    note_for_staff: 'Verificați fișierul',
    offer_lines: [{ label: 'Rotunde', quantity: 1000, total_ex_vat: '280.00', total: '333.20', unit_price: '0.2800', highlighted: true }, null],
    can_create_payment_link: 'yes',
  });
  assert.equal(s.kind, 'none');
  assert.equal(s.text, '');
  assert.deepEqual(s.options, ['Hârtie', 'Vinil']);
  assert.equal(s.image_url, null);
  assert.equal(s.payment_url, 'https://etichetecreative.ro/pay/1');
  assert.deepEqual(s.offer_lines, [{ label: 'Rotunde', quantity: '1000', total_ex_vat: '280.00', total: '333.20', unit_price: '0.2800', highlighted: true }]);
  assert.equal(s.can_create_payment_link, false);
  assert.throws(() => normalizeSuggestion(null), AssistError);
});

test('HTTP errors map to codes with Romanian messages and never expose backend text', async () => {
  const cases = [
    [401, 'unauthorized'],
    [404, 'not_found'],
    [409, 'superseded'],
    [429, 'rate_limited'],
    [503, 'unavailable'],
    [500, 'server'],
    [422, 'bad_request'],
  ];
  for (const [status, code] of cases) {
    assert.equal(codeForStatus(status), code);
    const { fetchImpl } = recorder(() => json(status, { error: { code: 'assist_unavailable', message: 'Traceback: raw backend detail' } }));
    await assert.rejects(client(fetchImpl).suggest({ key: 'k' }, []), (error) => {
      assert.ok(error instanceof AssistError);
      assert.equal(error.code, code);
      assert.equal(error.status, status);
      assert.equal(error.userMessage, ERROR_MESSAGES[code]);
      assert.ok(!error.userMessage.includes('Traceback'));
      assert.ok(!error.message.includes(TOKEN));
      return true;
    });
  }
});

test('every error message is Romanian text without em dashes', () => {
  for (const message of Object.values(ERROR_MESSAGES)) {
    assert.ok(message.length > 10);
    assert.ok(!/[—–]/.test(message));
  }
});

test('non JSON error bodies and non JSON success bodies are handled', async () => {
  const html = recorder(() => new Response('<html>Bad gateway</html>', { status: 502 }));
  await assert.rejects(client(html.fetchImpl).ping(), { code: 'server' });
  const okHtml = recorder(() => new Response('ok', { status: 200 }));
  await assert.rejects(client(okHtml.fetchImpl).ping(), { code: 'bad_response' });
});

test('network failures map to "network"', async () => {
  const fetchImpl = async () => {
    throw new TypeError('Failed to fetch');
  };
  await assert.rejects(client(fetchImpl).ping(), { code: 'network' });
});

const hangingFetch = (url, init) =>
  new Promise((_, reject) => {
    init.signal.addEventListener('abort', () => reject(init.signal.reason));
  });

test('an aborted request rejects with "aborted"', async () => {
  const controller = new AbortController();
  const pending = client(hangingFetch).suggest({ key: 'k' }, [], { signal: controller.signal });
  controller.abort();
  await assert.rejects(pending, { code: 'aborted' });
});

test('a request that exceeds the timeout rejects with "timeout"', async () => {
  const api = client(hangingFetch, { timeouts: { ping: 20, suggest: 20, upload: 20, paymentLink: 20, image: 20 } });
  // AbortSignal.timeout does not keep Node's event loop alive on its own.
  const keepAlive = setTimeout(() => {}, 2000);
  try {
    await assert.rejects(api.ping(), { code: 'timeout' });
  } finally {
    clearTimeout(keepAlive);
  }
});

test('missing configuration fails before any request', async () => {
  const { calls, fetchImpl } = recorder(() => json(200, {}));
  await assert.rejects(createApiClient({ baseUrl: '', token: TOKEN, fetchImpl }).ping(), { code: 'not_configured' });
  await assert.rejects(createApiClient({ baseUrl: 'https://quote.example.ro', token: '', fetchImpl }).ping(), { code: 'not_configured' });
  assert.equal(calls.length, 0);
});

test('upload sends multipart fields and returns the upload id', async () => {
  const { calls, fetchImpl } = recorder(() => json(200, { upload_id: 'up_9' }));
  const file = new Blob(['%PDF-1.4'], { type: 'application/pdf' });
  const result = await client(fetchImpl).upload({ chatKey: '40722123456', messageId: 'false_x_1', file, fileName: 'eticheta.pdf' });
  assert.deepEqual(result, { upload_id: 'up_9' });
  const { url, init } = calls[0];
  assert.equal(url, 'https://quote.example.ro/v1/assist/upload');
  assert.equal(init.headers[TOKEN_HEADER], TOKEN);
  assert.equal(init.headers['Content-Type'], undefined, 'fetch must set the multipart boundary');
  assert.ok(init.body instanceof FormData);
  assert.equal(init.body.get('chat_key'), '40722123456');
  assert.equal(init.body.get('message_id'), 'false_x_1');
  assert.equal(init.body.get('file').name, 'eticheta.pdf');
});

test('payment link posts edited_text (or null) to the suggestion URL', async () => {
  const { calls, fetchImpl } = recorder(() => json(200, { suggestion: { suggestion_id: 's 1', kind: 'offer', text: 'Final', payment_url: 'https://pay.example.ro/x' } }));
  const api = client(fetchImpl);
  const first = await api.createPaymentLink('s 1', 'Text editat');
  await api.createPaymentLink('s 1', null);
  assert.equal(calls[0].url, 'https://quote.example.ro/v1/assist/suggestions/s%201/payment-link');
  assert.deepEqual(JSON.parse(calls[0].init.body), { edited_text: 'Text editat' });
  assert.deepEqual(JSON.parse(calls[1].init.body), { edited_text: null });
  assert.equal(first.payment_url, 'https://pay.example.ro/x');
});

test('fetchImage sends the token only to the backend origin and accepts images only', async () => {
  const png = () => new Response(new Blob(['x'], { type: 'image/png' }), { status: 200 });
  const same = recorder(png);
  await client(same.fetchImpl).fetchImage('https://quote.example.ro/v1/assist/offers/1.png');
  assert.equal(same.calls[0].init.headers[TOKEN_HEADER], TOKEN);
  const other = recorder(png);
  await client(other.fetchImpl).fetchImage('https://cdn.example.com/1.png');
  assert.equal(other.calls[0].init.headers[TOKEN_HEADER], undefined);
  const html = recorder(() => new Response(new Blob(['<html>'], { type: 'text/html' }), { status: 200 }));
  await assert.rejects(client(html.fetchImpl).fetchImage('https://quote.example.ro/x'), { code: 'image_unavailable' });
  await assert.rejects(client(same.fetchImpl).fetchImage('http://quote.example.ro/x.png'), { code: 'image_unavailable' });
});
