// Options page: backend address, personal token, on/off switch, suggestion mode.
import { normalizeBaseUrl } from '../background/api-client.js';

const form = document.getElementById('form');
const baseUrlInput = document.getElementById('baseUrl');
const tokenInput = document.getElementById('token');
const enabledInput = document.getElementById('enabled');
const statusEl = document.getElementById('status');
const testButton = document.getElementById('test');
const saveButton = document.getElementById('save');

const URL_ERRORS = {
  empty: 'Completați adresa serverului.',
  invalid: 'Adresa serverului nu este validă.',
  insecure: 'Adresa serverului trebuie să înceapă cu https://.',
};

function setStatus(text, tone = 'info') {
  statusEl.textContent = text;
  statusEl.dataset.tone = tone;
  statusEl.hidden = !text;
}

function setBusy(busy) {
  testButton.disabled = busy;
  saveButton.disabled = busy;
}

async function load() {
  const stored = await chrome.storage.local.get({ baseUrl: '', token: '', enabled: true, mode: 'auto' });
  baseUrlInput.value = stored.baseUrl;
  enabledInput.checked = stored.enabled !== false;
  form.elements.mode.value = stored.mode === 'manual' ? 'manual' : 'auto';
  // The saved token is never written back into the page.
  tokenInput.placeholder = stored.token ? 'Token salvat' : 'Lipiți tokenul primit';
}

// Returns true when settings were saved. Must start inside a click (permission prompt).
async function save() {
  const normalized = normalizeBaseUrl(baseUrlInput.value);
  if (!normalized.ok) {
    setStatus(URL_ERRORS[normalized.reason] || URL_ERRORS.invalid, 'error');
    baseUrlInput.focus();
    return false;
  }
  let granted = false;
  try {
    granted = await chrome.permissions.request({ origins: [normalized.permissionPattern] });
  } catch {
    granted = false;
  }
  const update = {
    baseUrl: normalized.base,
    enabled: enabledInput.checked,
    mode: form.elements.mode.value === 'manual' ? 'manual' : 'auto',
  };
  const token = tokenInput.value.trim();
  if (token) update.token = token;
  await chrome.storage.local.set(update);
  tokenInput.value = '';
  await load();
  if (!granted) {
    setStatus('Setările au fost salvate, dar accesul la server nu a fost acordat. Apăsați din nou „Salvează” și acceptați cererea din Chrome.', 'error');
    return false;
  }
  setStatus('Setările au fost salvate.', 'ok');
  return true;
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  setBusy(true);
  try {
    await save();
  } finally {
    setBusy(false);
  }
});

testButton.addEventListener('click', async () => {
  setBusy(true);
  try {
    if (!(await save())) return;
    setStatus('Se testează conexiunea…');
    const response = await chrome.runtime.sendMessage({ type: 'ecq:ping' });
    if (response?.ok) {
      setStatus(response.staff ? `Conexiune reușită. Operator: ${response.staff}.` : 'Conexiune reușită.', 'ok');
    } else {
      setStatus(response?.error?.message || 'Conexiunea nu a reușit.', 'error');
    }
  } finally {
    setBusy(false);
  }
});

load();
