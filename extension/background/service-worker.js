// Background service worker: the only place that holds the token and talks to the backend.
import {
  AssistError,
  MAX_UPLOAD_BYTES,
  createApiClient,
  messageFor,
  normalizeBaseUrl,
} from './api-client.js';
import { createSuggestCoordinator } from './coordinator.js';

const WHATSAPP_ORIGIN = 'https://web.whatsapp.com';
const DEFAULTS = Object.freeze({
  baseUrl: '',
  token: '',
  enabled: true,
  mode: 'auto', // 'auto' | 'manual'
  panelCollapsed: false,
});

// Keep the token out of reach of content scripts.
chrome.storage.local.setAccessLevel?.({ accessLevel: 'TRUSTED_CONTEXTS' }).catch(() => {});

async function loadSettings() {
  const stored = await chrome.storage.local.get(DEFAULTS);
  return { ...DEFAULTS, ...stored };
}

function publicSettings(settings) {
  return {
    enabled: settings.enabled !== false,
    mode: settings.mode === 'manual' ? 'manual' : 'auto',
    collapsed: settings.panelCollapsed === true,
    configured: normalizeBaseUrl(settings.baseUrl).ok && Boolean(settings.token),
  };
}

async function clientFor(settings) {
  return createApiClient({ baseUrl: settings.baseUrl, token: settings.token });
}

// A failed fetch without the host permission looks like a network error; tell them apart.
async function refineError(error, settings) {
  if (error instanceof AssistError && error.code === 'network') {
    const normalized = normalizeBaseUrl(settings.baseUrl);
    if (normalized.ok) {
      const granted = await chrome.permissions
        .contains({ origins: [normalized.permissionPattern] })
        .catch(() => true);
      if (!granted) return new AssistError('permission_missing');
    }
  }
  return error;
}

function failure(error) {
  const code = error instanceof AssistError ? error.code : 'unknown';
  // Log codes only: never the token, never message contents.
  if (code !== 'aborted') console.warn('[ec-quote] request failed:', code, error?.status || '');
  return { ok: false, error: { code, message: messageFor(code) } };
}

const coordinator = createSuggestCoordinator({
  run: async ({ chat, messages }, signal) => {
    const settings = await loadSettings();
    try {
      return await (await clientFor(settings)).suggest(chat, messages, { signal });
    } catch (error) {
      throw await refineError(error, settings);
    }
  },
});

const lastSuggestionKey = (chatKey) => `lastSuggestion:${chatKey}`;

async function rememberSuggestion(chatKey, suggestionId) {
  if (!suggestionId) return;
  await chrome.storage.session.set({ [lastSuggestionKey(chatKey)]: suggestionId }).catch(() => {});
}

function base64ToBytes(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) bytes[i] = binary.charCodeAt(i);
  return bytes;
}

async function blobToBase64(blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = '';
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

const handlers = {
  async 'ecq:get-settings'() {
    return { ok: true, settings: publicSettings(await loadSettings()) };
  },

  async 'ecq:set-collapsed'({ collapsed }) {
    await chrome.storage.local.set({ panelCollapsed: collapsed === true });
    return { ok: true };
  },

  async 'ecq:open-options'() {
    await chrome.runtime.openOptionsPage();
    return { ok: true };
  },

  async 'ecq:ping'() {
    const settings = await loadSettings();
    try {
      const result = await (await clientFor(settings)).ping();
      return { ok: true, staff: result.staff };
    } catch (error) {
      return failure(await refineError(error, settings));
    }
  },

  async 'ecq:suggest'({ chat, messages, immediate }) {
    const settings = await loadSettings();
    if (settings.enabled === false) return failure(new AssistError('disabled'));
    if (!publicSettings(settings).configured) return failure(new AssistError('not_configured'));
    if (!chat?.key) return failure(new AssistError('bad_request'));
    coordinator.cancelAllExcept(chat.key);
    const outcome = await coordinator.request(chat.key, { chat, messages }, { immediate: immediate === true });
    if (outcome.aborted) return { ok: false, aborted: true };
    if (outcome.error) {
      if (outcome.error?.code === 'aborted') return { ok: false, aborted: true };
      return failure(outcome.error);
    }
    await rememberSuggestion(chat.key, outcome.value.suggestion_id);
    return { ok: true, suggestion: outcome.value };
  },

  async 'ecq:cancel'({ chatKey }) {
    if (chatKey) coordinator.cancel(chatKey);
    else coordinator.cancelAllExcept(null);
    return { ok: true };
  },

  async 'ecq:upload'({ chatKey, messageId, fileName, mime, base64 }) {
    const settings = await loadSettings();
    try {
      if (typeof base64 !== 'string' || !chatKey || !messageId) throw new AssistError('bad_request');
      if (base64.length > (MAX_UPLOAD_BYTES * 4) / 3 + 16) throw new AssistError('too_large');
      const file = new Blob([base64ToBytes(base64)], { type: mime || 'application/octet-stream' });
      const client = await clientFor(settings);
      return { ok: true, ...(await client.upload({ chatKey, messageId, file, fileName })) };
    } catch (error) {
      return failure(await refineError(error, settings));
    }
  },

  async 'ecq:payment-link'({ chatKey, suggestionId, editedText }) {
    const settings = await loadSettings();
    try {
      if (!suggestionId || !chatKey) throw new AssistError('bad_request');
      // Refuse a suggestion that is no longer the latest one for this chat.
      const key = lastSuggestionKey(chatKey);
      const stored = await chrome.storage.session.get(key).catch(() => ({}));
      if (stored[key] && stored[key] !== suggestionId) throw new AssistError('superseded');
      const client = await clientFor(settings);
      const suggestion = await client.createPaymentLink(suggestionId, editedText);
      await rememberSuggestion(chatKey, suggestion.suggestion_id || suggestionId);
      return { ok: true, suggestion };
    } catch (error) {
      return failure(await refineError(error, settings));
    }
  },

  async 'ecq:fetch-image'({ url }) {
    const settings = await loadSettings();
    try {
      const blob = await (await clientFor(settings)).fetchImage(url);
      return { ok: true, mime: blob.type, base64: await blobToBase64(blob) };
    } catch (error) {
      return failure(error);
    }
  },
};

// Only our own pages and our content script on WhatsApp Web may talk to the worker.
function isTrustedSender(sender) {
  if (!sender || sender.id !== chrome.runtime.id) return false;
  const url = sender.url || '';
  if (url.startsWith(chrome.runtime.getURL(''))) return true;
  return Boolean(sender.tab) && url.startsWith(`${WHATSAPP_ORIGIN}/`);
}

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  const handler = message && typeof message.type === 'string' ? handlers[message.type] : null;
  if (!handler || !isTrustedSender(sender)) return false;
  handler(message)
    .then(sendResponse)
    .catch((error) => sendResponse(failure(error)));
  return true; // async response
});

// Tell open WhatsApp tabs when settings change (they cannot read storage themselves).
chrome.storage.onChanged.addListener(async (changes, area) => {
  if (area !== 'local') return;
  if (!('enabled' in changes || 'mode' in changes || 'baseUrl' in changes || 'token' in changes)) return;
  const settings = publicSettings(await loadSettings());
  const tabs = await chrome.tabs.query({ url: `${WHATSAPP_ORIGIN}/*` }).catch(() => []);
  for (const tab of tabs) {
    chrome.tabs.sendMessage(tab.id, { type: 'ecq:settings-changed', settings }).catch(() => {});
  }
});

chrome.action.onClicked.addListener(() => {
  chrome.runtime.openOptionsPage();
});

chrome.runtime.onInstalled.addListener(({ reason }) => {
  if (reason === 'install') chrome.runtime.openOptionsPage();
});
