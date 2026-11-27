// Content script entry: watches the open chat, asks the background worker for a
// suggestion and drives the panel. It never sends a message and never opens a chat.
(() => {
  'use strict';
  const NS = globalThis.EcQuote;
  if (!NS || NS.started) return;
  NS.started = true;

  const { Reader, Composer, Media, Panel } = NS;
  const OBSERVER_DEBOUNCE_MS = 400;
  const OBSERVER_MAX_WAIT_MS = 1500;
  const MAX_MESSAGES = 40;
  const RELOAD_MESSAGE = 'Extensia a fost actualizată. Reîncărcați pagina WhatsApp Web.';

  function send(message) {
    return new Promise((resolve) => {
      const fail = () => resolve({ ok: false, error: { code: 'extension', message: RELOAD_MESSAGE } });
      try {
        chrome.runtime.sendMessage(message, (response) => {
          if (chrome.runtime.lastError || !response) fail();
          else resolve(response);
        });
      } catch {
        fail();
      }
    });
  }

  let settings = null;
  let panel = null;
  let observer = null;
  let themeObserver = null;
  let debounceTimer = null;
  let firstPending = 0;
  let appRootStyle = null; // { el, width, minWidth }
  let lastCompatStatus = null;
  let outdated = false;

  // State of the open chat only. Dropped on chat switch; nothing is persisted.
  let chat = freshChat(null);
  function freshChat(key) {
    return { key, convo: null, requestedFp: null, loading: false, seq: 0, uploads: new Map(), viewKey: null, attach: { busy: false, status: '', tone: 'info' } };
  }

  // ---- Theme and layout ----
  function detectTheme() {
    const candidates = [Reader.findComposer(), Reader.findAppRoot(), document.body];
    for (const node of candidates) {
      for (let cur = node; cur && cur.nodeType === 1; cur = cur.parentElement) {
        const match = /rgba?\(([^)]+)\)/.exec(getComputedStyle(cur).backgroundColor || '');
        if (!match) continue;
        const [r, g, b, a = 1] = match[1].split(/[,\s/]+/).filter(Boolean).map(Number);
        if (a < 0.5) continue;
        return 0.2126 * r + 0.7152 * g + 0.0722 * b < 110 ? 'dark' : 'light';
      }
    }
    return matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  function restoreAppRoot() {
    if (!appRootStyle) return;
    appRootStyle.el.style.setProperty('width', appRootStyle.width);
    appRootStyle.el.style.setProperty('min-width', appRootStyle.minWidth);
    if (!appRootStyle.width) appRootStyle.el.style.removeProperty('width');
    if (!appRootStyle.minWidth) appRootStyle.el.style.removeProperty('min-width');
    appRootStyle = null;
  }

  // Reserve room next to WhatsApp so the panel never sits on top of the message box.
  function applyLayout() {
    if (!panel) return;
    const width = settings.collapsed ? NS.PANEL_RAIL_WIDTH : NS.PANEL_WIDTH;
    const host = panel.host;
    host.style.cssText = `all: initial; position: fixed; top: 0; right: 0; bottom: 0; width: ${width}px; z-index: 2147483000;`;

    const appRoot = Reader.findAppRoot();
    if (appRoot) {
      if (!appRootStyle || appRootStyle.el !== appRoot) {
        restoreAppRoot();
        appRootStyle = { el: appRoot, width: appRoot.style.getPropertyValue('width'), minWidth: appRoot.style.getPropertyValue('min-width') };
      }
      appRoot.style.setProperty('width', `calc(100% - ${width}px)`, 'important');
      appRoot.style.setProperty('min-width', '0', 'important');
    }

    // If WhatsApp ignores the reserved room, stop above the message box instead.
    const composer = Reader.findComposer();
    const rect = composer ? composer.getBoundingClientRect() : null;
    const overlaps = Boolean(rect && rect.width && rect.right > window.innerWidth - width + 1);
    if (overlaps) host.style.bottom = `${Math.max(0, window.innerHeight - rect.top + 12)}px`;
    panel.setFloating(overlaps);
  }

  // ---- Views ----
  function showStateOnce(key, options) {
    if (chat.viewKey === key) return;
    chat.viewKey = key;
    panel.showState(options);
  }

  function fingerprint(convo) {
    const last = convo.messages[convo.messages.length - 1];
    const media = convo.messages
      .filter((m) => m.attachment)
      .map((m) => `${m.id}:${m.attachment.type}`)
      .join(',');
    return `${convo.chat.key}|${last ? last.id : ''}|${chat.uploads.size}|${media}`;
  }

  function attachmentTarget(convo) {
    const recent = convo.messages.slice(-8).filter((m) => m.direction === 'in');
    for (let i = recent.length - 1; i >= 0; i -= 1) if (recent[i].attachment) return recent[i];
    return null;
  }

  function lastInbound(convo) {
    for (let i = convo.messages.length - 1; i >= 0; i -= 1) if (convo.messages[i].direction === 'in') return convo.messages[i];
    return null;
  }

  function renderAttachment() {
    const convo = chat.convo;
    if (!convo || !convo.supported || !convo.chat || !lastInbound(convo)) return panel.setAttachment({ visible: false });
    const target = attachmentTarget(convo);
    let info = 'Dacă clientul a trimis un fișier, îl puteți verifica aici.';
    let canRead = false;
    if (target) {
      const uploaded = chat.uploads.has(target.id);
      const isImage = target.attachment.type === 'image';
      canRead = !uploaded && Boolean(target.attachment.src);
      if (uploaded) info = 'Fișierul clientului a fost trimis la verificare.';
      else if (isImage) info = 'Clientul a trimis o imagine.';
      else if (canRead) info = `Clientul a trimis un document${target.attachment.name ? `: ${target.attachment.name}` : '.'}`;
      else info = `Clientul a trimis un document${target.attachment.name ? `: ${target.attachment.name}` : ''}. Descărcați-l din WhatsApp, apoi trageți-l mai jos.`;
    }
    panel.setAttachment({ visible: true, info, canRead, busy: chat.attach.busy, status: chat.attach.status, tone: chat.attach.tone });
  }

  // ---- Suggestion ----
  async function loadImage(suggestion) {
    const response = await send({ type: 'ecq:fetch-image', url: suggestion.image_url });
    if (!panel || panel.suggestion() !== suggestion) return;
    if (response.ok) panel.setImage('ready', Media.base64ToBlob(response.base64, response.mime));
    else panel.setImage('error');
  }

  function showSuggestion(suggestion, options) {
    chat.viewKey = `suggestion:${suggestion.suggestion_id}`;
    panel.showSuggestion(suggestion, options);
    const shown = panel.suggestion();
    if (shown.image_url && !(options && options.keepImage)) loadImage(shown);
  }

  function showUpdateRequired() {
    outdated = true;
    chat.viewKey = 'update_required';
    panel.showState({
      tone: 'error',
      title: 'Actualizați extensia',
      text: 'Versiunea instalată este mai veche decât minimul cerut de server. Instalați ultima versiune pentru a continua.',
      action: { label: 'Deschide opțiunile', run: () => send({ type: 'ecq:open-options' }) },
    });
  }

  async function requestSuggestion(immediate) {
    if (outdated) return showUpdateRequired();
    const convo = chat.convo;
    if (!convo || !convo.supported || !convo.chat || !convo.messages.length) return;
    const seq = (chat.seq += 1);
    const owner = chat;
    chat.requestedFp = fingerprint(convo);
    chat.loading = true;
    chat.viewKey = 'loading';
    panel.showLoading();

    const response = await send({
      type: 'ecq:suggest',
      chat: convo.chat,
      messages: convo.messages.slice(-MAX_MESSAGES).map((m) => Reader.toApiMessage(m, chat.uploads)),
      immediate: Boolean(immediate),
    });
    if (owner !== chat || seq !== chat.seq || !panel) return; // stale answer
    chat.loading = false;

    if (response.ok) return showSuggestion(response.suggestion);
    if (response.aborted) return showIdle(convo);
    if (response.error.code === 'update_required') return showUpdateRequired();
    chat.viewKey = 'error';
    panel.showState({
      tone: 'error',
      title: 'Sugestia nu a putut fi obținută',
      text: response.error.message,
      action: response.error.code === 'not_configured' || response.error.code === 'permission_missing' || response.error.code === 'unauthorized'
        ? { label: 'Deschide opțiunile', run: () => send({ type: 'ecq:open-options' }) }
        : { label: 'Încearcă din nou', run: () => requestSuggestion(true) },
    });
  }

  function showIdle(convo) {
    const last = convo.messages[convo.messages.length - 1];
    const text = !last
      ? 'Conversația nu are încă mesaje vizibile.'
      : last.direction === 'out'
        ? 'Ultimul mesaj este trimis de dvs. Puteți cere o sugestie oricând.'
        : 'Cereți o sugestie pentru conversația deschisă.';
    showStateOnce(`idle:${last ? last.id : ''}`, {
      title: 'Nicio sugestie afișată',
      text,
      action: last ? { label: 'Cere sugestie', run: () => requestSuggestion(true) } : null,
    });
  }

  // ---- Main refresh, called on DOM changes ----
  function refresh() {
    if (!panel) return;
    const convo = Reader.readConversation();
    const compat = Reader.selfTest();
    panel.setCompat(compat);
    if (compat.status !== lastCompatStatus) {
      lastCompatStatus = compat.status;
      send({ type: 'ecq:compat-status', status: compat.status });
    }
    panel.setTheme(detectTheme());
    applyLayout();

    const key = convo.open && convo.chat ? convo.chat.key : null;
    if (key !== chat.key) {
      if (chat.key) send({ type: 'ecq:cancel', chatKey: chat.key });
      chat = freshChat(key);
    }
    chat.convo = convo;
    panel.setChat(convo.open && convo.chat ? convo.chat.name || convo.chat.phone || '' : null);
    renderAttachment();

    if (!settings.configured) {
      return showStateOnce('unconfigured', {
        title: 'Extensia nu este configurată',
        text: 'Completați adresa serverului și tokenul personal în Opțiuni.',
        action: { label: 'Deschide opțiunile', run: () => send({ type: 'ecq:open-options' }) },
      });
    }
    if (outdated) return showUpdateRequired();
    if (!convo.open || !convo.chat) {
      return showStateOnce('nochat', { title: 'Nicio conversație deschisă', text: 'Deschideți o conversație pentru a primi o sugestie de răspuns.' });
    }
    if (convo.group) return showStateOnce('group', { title: 'Conversațiile de grup nu sunt asistate' });
    if (!convo.supported) return showStateOnce('unsupported', { title: 'Acest tip de conversație nu este asistat' });

    const fp = fingerprint(convo);
    if (fp === chat.requestedFp) return;
    const last = convo.messages[convo.messages.length - 1];
    const hasSuggestion = Boolean(panel.suggestion());

    if (last && last.direction === 'in') {
      if (hasSuggestion && (panel.isDirty() || settings.mode !== 'auto')) return panel.setStale(true);
      if (settings.mode === 'auto') return void requestSuggestion(false);
      if (!chat.loading) showIdle(convo);
      return;
    }
    // Last message is ours (or there is none): the previous suggestion is spent.
    if (chat.loading) send({ type: 'ecq:cancel', chatKey: chat.key });
    chat.seq += 1;
    chat.loading = false;
    chat.requestedFp = null;
    showIdle(convo);
  }

  function scheduleRefresh() {
    const now = Date.now();
    if (!firstPending) firstPending = now;
    clearTimeout(debounceTimer);
    const wait = now - firstPending >= OBSERVER_MAX_WAIT_MS ? 0 : OBSERVER_DEBOUNCE_MS;
    debounceTimer = setTimeout(() => {
      firstPending = 0;
      refresh();
    }, wait);
  }

  // ---- Panel actions ----
  async function doInsert(text, mode) {
    const result = await Composer.insertText(text, { mode });
    if (result.ok) return panel.notify('Textul a fost inserat în caseta de mesaj. Verificați-l și trimiteți-l dvs.');
    try {
      await navigator.clipboard.writeText(text);
      panel.notify('Textul nu a putut fi inserat automat. A fost copiat: lipiți-l în caseta de mesaj cu Ctrl+V.', 'error');
    } catch {
      panel.notify('Textul nu a putut fi inserat automat. Folosiți „Copiază textul” și lipiți-l în caseta de mesaj.', 'error');
    }
  }

  function onInsert(text) {
    if (!text.trim()) return panel.notify('Nu există text de inserat.', 'error');
    if (!Composer.hasDraft()) return doInsert(text, 'append');
    panel.confirm('Caseta de mesaj conține deja text.', [
      { label: 'Înlocuiește', primary: true, run: () => doInsert(text, 'replace') },
      { label: 'Adaugă la final', run: () => doInsert(text, 'append') },
    ]);
  }

  async function doAttachImage(blob, captionText) {
    const owner = chat;
    const active = panel && panel.suggestion();
    panel.setBusy(true);
    try {
      const png = await Media.toPng(blob);
      if (owner !== chat || !panel || panel.suggestion() !== active) return;
      const result = await Composer.attachImage(png, captionText);
      if (owner !== chat || !panel) return;
      if (result.ok) {
        panel.notify('Imaginea ofertei a fost atașată în previzualizarea WhatsApp. Verificați și trimiteți dvs.');
      } else {
        panel.notify('Previzualizarea WhatsApp nu a apărut. Folosiți „Copiază imaginea” sau „Descarcă”, iar pentru text „Inserează în mesaj”.', 'error');
      }
    } catch {
      if (owner === chat && panel) {
        panel.notify('Imaginea nu a putut fi atașată automat. Folosiți „Copiază imaginea” sau „Descarcă”.', 'error');
      }
    } finally {
      if (owner === chat && panel) panel.setBusy(false);
    }
  }

  function onAttachImage(blob, captionText) {
    if (!blob) return panel.notify('Imaginea ofertei nu este încărcată.', 'error');
    if (!Composer.hasDraft()) return void doAttachImage(blob, captionText);
    panel.confirm('Caseta de mesaj conține deja text. Atașarea imaginii va pune textul ofertei în câmpul de descriere.', [
      { label: 'Atașează imaginea', primary: true, run: () => doAttachImage(blob, captionText) },
    ]);
  }

  async function onPaymentLink(text) {
    const suggestion = panel.suggestion();
    if (!suggestion || !chat.key) return;
    const owner = chat;
    panel.setBusy(true);
    panel.notify('Se creează linkul de plată...', 'info', true);
    const response = await send({
      type: 'ecq:payment-link',
      chatKey: chat.key,
      suggestionId: suggestion.suggestion_id,
      editedText: panel.isTextEdited() ? text : null,
    });
    if (owner !== chat || !panel) return;
    panel.setBusy(false);
    if (!response.ok) {
      if (response.error.code === 'update_required') return showUpdateRequired();
      return panel.notify(response.error.message, 'error');
    }
    const next = { ...response.suggestion, image_url: response.suggestion.image_url || suggestion.image_url };
    showSuggestion(next, { keepImage: next.image_url === suggestion.image_url });
    panel.notify('Linkul de plată a fost creat. Textul de mai jos îl conține.');
  }

  function setAttach(patch) {
    Object.assign(chat.attach, patch);
    renderAttachment();
  }

  async function uploadBlob(blob, fileName, messageId) {
    const owner = chat;
    if (blob.size > Media.MAX_BYTES) {
      return setAttach({ busy: false, tone: 'error', status: 'Fișierul este prea mare pentru a fi trimis din extensie (maximum 15 MB).' });
    }
    setAttach({ busy: true, tone: 'info', status: 'Se trimite fișierul la verificare...' });
    const base64 = await Media.blobToBase64(blob);
    const response = await send({ type: 'ecq:upload', chatKey: owner.key, messageId, fileName, mime: blob.type, base64 });
    if (owner !== chat || !panel) return;
    if (!response.ok) {
      if (response.error.code === 'update_required') showUpdateRequired();
      return setAttach({ busy: false, tone: 'error', status: response.error.message });
    }
    chat.uploads.set(messageId, response.upload_id);
    setAttach({ busy: false, tone: 'ok', status: 'Fișierul a fost trimis la verificare.' });
    if (panel.suggestion() && panel.isDirty()) panel.setStale(true);
    else requestSuggestion(true);
  }

  async function onUploadFromChat() {
    const target = chat.convo && attachmentTarget(chat.convo);
    if (!target) return;
    try {
      const { blob, fileName } = await Media.readAttachment(target.attachment);
      await uploadBlob(blob, fileName, target.id);
    } catch {
      setAttach({
        busy: false,
        tone: 'error',
        status: 'Fișierul nu a putut fi citit din pagină. Descărcați-l din WhatsApp, apoi trageți-l mai jos sau alegeți-l din calculator.',
      });
    }
  }

  function onUploadFile(file) {
    const convo = chat.convo;
    const target = convo && (attachmentTarget(convo) || lastInbound(convo));
    if (!target || !chat.key) return;
    uploadBlob(file, file.name, target.id);
  }

  async function onCollapse(collapsed) {
    settings.collapsed = collapsed;
    panel.setCollapsed(collapsed);
    applyLayout();
    send({ type: 'ecq:set-collapsed', collapsed });
  }

  // ---- Lifecycle ----
  function mount() {
    if (panel) return;
    panel = Panel.create({
      request: () => requestSuggestion(true),
      insert: onInsert,
      attachImage: onAttachImage,
      paymentLink: onPaymentLink,
      collapse: onCollapse,
      uploadFromChat: onUploadFromChat,
      uploadFile: onUploadFile,
      openOptions: () => send({ type: 'ecq:open-options' }),
    });
    panel.setCollapsed(settings.collapsed);
    document.documentElement.append(panel.host);
    observer = new MutationObserver(scheduleRefresh);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      characterData: true,
      attributes: true,
      attributeFilter: ['src', 'href'],
    });
    // Theme switches change attributes on <html> or <body> only.
    themeObserver = new MutationObserver(scheduleRefresh);
    themeObserver.observe(document.documentElement, { attributes: true });
    themeObserver.observe(document.body, { attributes: true });
    window.addEventListener('resize', scheduleRefresh);
    refresh();
  }

  function unmount() {
    if (!panel) return;
    observer.disconnect();
    themeObserver.disconnect();
    observer = null;
    themeObserver = null;
    lastCompatStatus = null;
    clearTimeout(debounceTimer);
    window.removeEventListener('resize', scheduleRefresh);
    if (chat.key) send({ type: 'ecq:cancel', chatKey: chat.key });
    panel.host.remove();
    panel = null;
    restoreAppRoot();
    chat = freshChat(null);
  }

  function applySettings(next) {
    const collapsed = settings ? settings.collapsed : next.collapsed;
    settings = { ...next, collapsed };
    outdated = false;
    if (!settings.enabled) return unmount();
    if (!panel) return mount();
    chat.viewKey = null;
    chat.requestedFp = null;
    refresh();
  }

  chrome.runtime.onMessage.addListener((message) => {
    if (message && message.type === 'ecq:settings-changed' && message.settings) applySettings(message.settings);
  });

  send({ type: 'ecq:get-settings' }).then((response) => {
    if (response.ok) {
      settings = null;
      applySettings(response.settings);
    }
  });
})();
