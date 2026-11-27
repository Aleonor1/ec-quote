// Background service worker: the only place that holds the token and talks to the backend.
import {
  AssistError,
  DEFAULT_VERSION,
  MAX_UPLOAD_BYTES,
  createApiClient,
  messageFor,
  normalizeBaseUrl,
} from './api-client.js';
import { createSuggestCoordinator } from './coordinator.js';

const WHATSAPP_ORIGIN = 'https://web.whatsapp.com';
const EXTENSION_VERSION = chrome.runtime.getManifest?.()?.version || DEFAULT_VERSION;
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
    version: EXTENSION_VERSION,
  };
}

async function clientFor(settings) {
  return createApiClient({
    baseUrl: settings.baseUrl,
    token: settings.token,
    version: EXTENSION_VERSION,
  });
}

// Toolbar badge indicates off, ready, or check (selector breakage / update required).
async function updateActionState(status) {
  const map = {
    off: { text: 'OPR', color: '#5b6b75', title: 'EC Quote: oprit' },
    check: { text: '!', color: '#8a5a00', title: 'EC Quote: compatibilitate WhatsApp de verificat' },
    update: { text: 'ACT', color: '#b3261e', title: 'EC Quote: actualizați extensia' },
    ready: { text: '', color: '#00745f', title: 'EC Quote: activ' },
  };
  const next = map[status] || map.ready;
  await chrome.action?.setBadgeText?.({ text: next.text }).catch(() => {});
  if (next.text) await chrome.action?.setBadgeBackgroundColor?.({ color: next.color }).catch(() => {});
  await chrome.action?.setTitle?.({ title: next.title }).catch(() => {});
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
  if (code === 'update_required') updateActionState('update');
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

async function lastSuggestionKey(chatKey) {
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(String(chatKey || '')));
  const hex = Array.from(new Uint8Array(digest).subarray(0, 8), (b) => b.toString(16).padStart(2, '0')).join('');
  return `lastSuggestion:${hex}`;
}

async function rememberSuggestion(chatKey, suggestionId) {
  if (!suggestionId) return;
  const key = await lastSuggestionKey(chatKey);
  await chrome.storage.session.set({ [key]: suggestionId }).catch(() => {});
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
    const settings = await loadSettings();
    await updateActionState(settings.enabled === false ? 'off' : 'ready');
    return { ok: true, settings: publicSettings(settings) };
  },

  async 'ecq:compat-status'({ status }) {
    const settings = await loadSettings();
    if (settings.enabled === false) await updateActionState('off');
    else if (status === 'check') await updateActionState('check');
    else await updateActionState('ready');
    return { ok: true };
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
      if (result.outdated) await updateActionState('update');
      return result;
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
    if (chatKey) {
      coordinator.cancel(chatKey);
      const key = await lastSuggestionKey(chatKey);
      await chrome.storage.session.remove(key).catch(() => {});
    } else {
      coordinator.cancelAllExcept(null);
      await chrome.storage.session.clear().catch(() => {});
    }
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
      const key = await lastSuggestionKey(chatKey);
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
  const full = await loadSettings();
  await updateActionState(full.enabled === false ? 'off' : 'ready');
  const settings = publicSettings(full);
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
