// HTTP client for the ec-quote assist API. No chrome.* here so it runs under node --test.

export const TOKEN_HEADER = 'X-EcQuote-Assist-Token';
export const MAX_MESSAGES = 40;
export const MAX_TEXT_LENGTH = 4000;
export const MAX_UPLOAD_BYTES = 15 * 1024 * 1024;
export const MAX_IMAGE_BYTES = 10 * 1024 * 1024;

export const TIMEOUTS = Object.freeze({
  ping: 10_000,
  suggest: 60_000,
  upload: 90_000,
  paymentLink: 45_000,
  image: 20_000,
});

export const KINDS = Object.freeze(['reply', 'question', 'offer', 'needs_human', 'none']);

// Short staff-facing messages. Backend error text is never shown.
export const ERROR_MESSAGES = Object.freeze({
  not_configured: 'Extensia nu este configurată. Completați adresa serverului și tokenul în Opțiuni.',
  disabled: 'Asistentul este oprit din Opțiuni.',
  permission_missing: 'Accesul la server nu este acordat. Deschideți Opțiuni și salvați din nou adresa.',
  unauthorized: 'Token invalid sau expirat. Verificați tokenul în Opțiuni.',
  not_found: 'Sugestia nu mai este disponibilă. Cereți o sugestie nouă.',
  superseded: 'Sugestia a fost înlocuită de una mai nouă. Cereți o sugestie nouă.',
  rate_limited: 'Prea multe cereri. Așteptați câteva secunde și încercați din nou.',
  unavailable: 'Asistentul nu este disponibil momentan. Răspundeți manual și încercați mai târziu.',
  server: 'Serverul a întâmpinat o eroare. Încercați din nou.',
  bad_request: 'Cererea nu a putut fi procesată. Încercați din nou.',
  bad_response: 'Răspuns neașteptat de la server. Încercați din nou.',
  timeout: 'Serverul nu a răspuns la timp. Încercați din nou.',
  network: 'Serverul nu poate fi contactat. Verificați conexiunea și adresa din Opțiuni.',
  too_large: 'Fișierul este prea mare pentru a fi trimis din extensie (maximum 15 MB).',
  image_unavailable: 'Imaginea ofertei nu a putut fi încărcată.',
  aborted: 'Cererea a fost anulată.',
  unknown: 'A apărut o eroare. Încercați din nou.',
});

export function messageFor(code) {
  return ERROR_MESSAGES[code] || ERROR_MESSAGES.unknown;
}

export class AssistError extends Error {
  constructor(code, status = 0, backendCode = null) {
    super(code);
    this.name = 'AssistError';
    this.code = code;
    this.status = status;
    this.backendCode = backendCode; // diagnostics only, never displayed
    this.userMessage = messageFor(code);
  }
}

export function codeForStatus(status) {
  if (status === 401 || status === 403) return 'unauthorized';
  if (status === 404) return 'not_found';
  if (status === 409) return 'superseded';
  if (status === 413) return 'too_large';
  if (status === 429) return 'rate_limited';
  if (status === 503) return 'unavailable';
  if (status >= 500) return 'server';
  if (status >= 400) return 'bad_request';
  return 'bad_response';
}

// Accepts https anywhere and http only on loopback (local development).
export function normalizeBaseUrl(raw) {
  const value = String(raw ?? '').trim();
  if (!value) return { ok: false, reason: 'empty' };
  let url;
  try {
    url = new URL(value);
  } catch {
    return { ok: false, reason: 'invalid' };
  }
  const loopback = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
  if (url.protocol !== 'https:' && !(url.protocol === 'http:' && loopback)) {
    return { ok: false, reason: 'insecure' };
  }
  if (url.username || url.password) return { ok: false, reason: 'invalid' };
  const path = url.pathname.replace(/\/+$/, '');
  return {
    ok: true,
    base: url.origin + path,
    origin: url.origin,
    // Match patterns ignore the port.
    permissionPattern: `${url.protocol}//${url.hostname}/*`,
  };
}

function isAllowedLink(value) {
  if (typeof value !== 'string' || !value) return false;
  try {
    const url = new URL(value);
    const loopback = url.hostname === 'localhost' || url.hostname === '127.0.0.1';
    return url.protocol === 'https:' || (url.protocol === 'http:' && loopback);
  } catch {
    return false;
  }
}

const str = (value, max = 20_000) => (typeof value === 'string' ? value.slice(0, max) : '');
// Money and quantities are displayed as received; numbers are only stringified.
const display = (value) =>
  typeof value === 'string' ? value.slice(0, 80) : typeof value === 'number' ? String(value) : '';

// Backend output is untrusted data: keep known fields, coerce types, drop the rest.
export function normalizeSuggestion(raw) {
  if (!raw || typeof raw !== 'object') throw new AssistError('bad_response');
  const kind = KINDS.includes(raw.kind) ? raw.kind : 'none';
  const lines = Array.isArray(raw.offer_lines) ? raw.offer_lines.slice(0, 30) : [];
  return {
    suggestion_id: str(raw.suggestion_id, 200),
    kind,
    text: str(raw.text),
    options: (Array.isArray(raw.options) ? raw.options : [])
      .filter((o) => typeof o === 'string' && o.trim())
      .slice(0, 12)
      .map((o) => o.slice(0, 200)),
    image_url: isAllowedLink(raw.image_url) ? raw.image_url : null,
    note_for_staff: str(raw.note_for_staff, 4000),
    handoff_reason: str(raw.handoff_reason, 1000) || null,
    offer_lines: lines
      .filter((l) => l && typeof l === 'object')
      .map((l) => ({
        label: str(l.label, 200),
        quantity: display(l.quantity),
        total_ex_vat: display(l.total_ex_vat),
        total: display(l.total),
        unit_price: display(l.unit_price),
        highlighted: l.highlighted === true,
      })),
    can_create_payment_link: raw.can_create_payment_link === true,
    payment_url: isAllowedLink(raw.payment_url) ? raw.payment_url : null,
  };
}

export function buildSuggestBody(chat, messages) {
  const list = Array.isArray(messages) ? messages.slice(-MAX_MESSAGES) : [];
  return {
    chat: {
      key: str(chat?.key, 200),
      name: str(chat?.name, 200),
      phone: typeof chat?.phone === 'string' && chat.phone ? chat.phone.slice(0, 40) : null,
    },
    messages: list.map((m) => ({
      id: str(m?.id, 300),
      direction: m?.direction === 'out' ? 'out' : 'in',
      text: str(m?.text, MAX_TEXT_LENGTH),
      sent_at: typeof m?.sent_at === 'string' && m.sent_at ? m.sent_at : null,
      attachments: (Array.isArray(m?.attachments) ? m.attachments : [])
        .filter((a) => a && typeof a.upload_id === 'string' && a.upload_id)
        .map((a) => ({ upload_id: a.upload_id })),
    })),
  };
}

function mergeSignals(signal, timeoutMs) {
  const timeout = AbortSignal.timeout(timeoutMs);
  return signal ? AbortSignal.any([signal, timeout]) : timeout;
}

export function createApiClient({ baseUrl, token, fetchImpl, timeouts = TIMEOUTS } = {}) {
  const doFetch = fetchImpl || ((...args) => fetch(...args));
  const normalized = normalizeBaseUrl(baseUrl);

  async function request(path, { method = 'GET', json, form, signal, timeout }) {
    if (!normalized.ok || !token) throw new AssistError('not_configured');
    const headers = { [TOKEN_HEADER]: token, Accept: 'application/json' };
    let body;
    if (json !== undefined) {
      headers['Content-Type'] = 'application/json';
      body = JSON.stringify(json);
    } else if (form) {
      body = form; // fetch sets the multipart boundary
    }
    let response;
    try {
      response = await doFetch(normalized.base + path, {
        method,
        headers,
        body,
        signal: mergeSignals(signal, timeout),
        credentials: 'omit',
        cache: 'no-store',
        redirect: 'error',
        referrerPolicy: 'no-referrer',
      });
    } catch (error) {
      if (signal?.aborted) throw new AssistError('aborted');
      if (error?.name === 'TimeoutError') throw new AssistError('timeout');
      if (error?.name === 'AbortError') throw new AssistError('aborted');
      throw new AssistError('network');
    }
    let data = null;
    try {
      data = await response.json();
    } catch {
      data = null;
    }
    if (!response.ok) {
      const backendCode = typeof data?.error?.code === 'string' ? data.error.code.slice(0, 80) : null;
      throw new AssistError(codeForStatus(response.status), response.status, backendCode);
    }
    if (!data || typeof data !== 'object') throw new AssistError('bad_response', response.status);
    return data;
  }

  return {
    origin: normalized.ok ? normalized.origin : null,

    async ping({ signal } = {}) {
      const data = await request('/v1/assist/ping', { signal, timeout: timeouts.ping });
      if (data.ok !== true) throw new AssistError('bad_response');
      return { ok: true, staff: str(data.staff, 120) };
    },

    async suggest(chat, messages, { signal } = {}) {
      const data = await request('/v1/assist/suggest', {
        method: 'POST',
        json: buildSuggestBody(chat, messages),
        signal,
        timeout: timeouts.suggest,
      });
      return normalizeSuggestion(data.suggestion);
    },

    async upload({ chatKey, messageId, file, fileName }, { signal } = {}) {
      if (file.size > MAX_UPLOAD_BYTES) throw new AssistError('too_large');
      const form = new FormData();
      form.append('chat_key', String(chatKey));
      form.append('message_id', String(messageId));
      form.append('file', file, fileName || 'fisier');
      const data = await request('/v1/assist/upload', {
        method: 'POST',
        form,
        signal,
        timeout: timeouts.upload,
      });
      if (typeof data.upload_id !== 'string' || !data.upload_id) throw new AssistError('bad_response');
      return { upload_id: data.upload_id };
    },

    async createPaymentLink(suggestionId, editedText, { signal } = {}) {
      const data = await request(
        `/v1/assist/suggestions/${encodeURIComponent(suggestionId)}/payment-link`,
        {
          method: 'POST',
          json: { edited_text: typeof editedText === 'string' && editedText ? editedText : null },
          signal,
          timeout: timeouts.paymentLink,
        },
      );
      return normalizeSuggestion(data.suggestion);
    },

    // Offer image bytes. The token is sent only to the backend origin.
    async fetchImage(url, { signal } = {}) {
      if (!normalized.ok || !isAllowedLink(url)) throw new AssistError('image_unavailable');
      const sameOrigin = new URL(url).origin === normalized.origin;
      let response;
      try {
        response = await doFetch(url, {
          headers: sameOrigin && token ? { [TOKEN_HEADER]: token } : {},
          signal: mergeSignals(signal, timeouts.image),
          credentials: 'omit',
          referrerPolicy: 'no-referrer',
        });
      } catch {
        throw new AssistError('image_unavailable');
      }
      if (!response.ok) throw new AssistError('image_unavailable', response.status);
      const blob = await response.blob();
      if (!/^image\/(png|jpeg|webp)$/.test(blob.type) || blob.size > MAX_IMAGE_BYTES) {
        throw new AssistError('image_unavailable');
      }
      return blob;
    },
  };
}
