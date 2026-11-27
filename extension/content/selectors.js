// WhatsApp Web reader. Everything that depends on WhatsApp's DOM lives in this file.
// WhatsApp changes its markup without notice: when the self-test in the panel footer
// reports "de verificat", update the SELECTORS map below and nothing else.
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  // Each entry is a list tried in order; the first selector that matches wins.
  // Attributes and ARIA roles first, stable semantic class names last, no hashed classes.
  const SELECTORS = {
    // Root of the WhatsApp application (used to reserve room for the panel).
    appRoot: ['#app', 'body > div[id]'],
    // The open conversation column.
    chatPane: ['#main', '[data-testid="conversation-panel-wrapper"]'],
    // Chat title inside the conversation header (relative to chatPane).
    headerTitle: [
      'header [data-testid="conversation-info-header-chat-title"]',
      'header span[dir="auto"][title]',
      'header span[dir="auto"]',
    ],
    // One element per message, carrying WhatsApp's message id (relative to chatPane).
    messageNode: ['div[role="row"] [data-id]', '[data-id^="true_"], [data-id^="false_"]'],
    // Wrapper that carries "[time, date] author: " (relative to a message).
    prePlainText: ['[data-pre-plain-text]'],
    // Message text or media caption (relative to a message).
    textBody: [
      'span.selectable-text.copyable-text',
      '[data-testid="msg-text"]',
      '.copyable-text span[dir]',
    ],
    // Quoted reply block inside a message.
    quoted: [
      '[aria-label="Mesaj citat"]',
      '[aria-label="Quoted message"]',
      '[data-testid="quoted-message"]',
      '.quoted-mention',
    ],
    // Text inside the quoted block.
    quotedText: ['.quoted-mention', 'span[dir="auto"]'],
    // Direction markers (stable, non-hashed class names) used when the id has no prefix.
    outgoing: ['.message-out'],
    incoming: ['.message-in'],
    // Loaded image of an image message.
    image: ['img[src^="blob:"]'],
    // Image message whose low-res preview is rendered before WhatsApp finishes loading its blob URL.
    imagePlaceholder: [
      '[aria-label="Deschide imaginea"] img',
      '[aria-label="Open picture"] img',
      '[data-testid="image-thumb"] img',
    ],
    // Emoji and other inline images that are not attachments.
    inlineImage: ['img.emoji', 'img[data-plain-text]', 'img[draggable="false"][alt]:not([src^="blob:"])'],
    // Document bubble markers.
    document: [
      '[data-icon^="document"]',
      '[data-testid^="document"]',
      '[data-icon="audio-download"]',
      '[title^="Descarcă"]',
      '[title^="Download"]',
    ],
    // File name inside a document bubble.
    documentName: ['[data-testid="document-title"]', 'span[dir="auto"]'],
    // Already downloaded document, if WhatsApp exposes one.
    documentBlob: ['a[href^="blob:"]'],
    // The message box (relative to chatPane). The send button is deliberately absent:
    // the extension has no selector for it and never touches it.
    composer: [
      'footer div[contenteditable="true"][role="textbox"]',
      'footer [data-lexical-editor="true"]',
      'footer div[contenteditable="true"]',
    ],
    // Media attachment preview opened by WhatsApp after pasting/dropping an image, and its caption input.
    // Never includes any button inside the preview.
    mediaPreview: [
      '[data-testid="media-editor"]',
      '[aria-label="Previzualizare media"]',
      '[aria-label="Media preview"]',
      '[data-wa-media-preview="true"]',
    ],
    mediaCaption: [
      '[data-testid="media-caption-input-container"] div[contenteditable="true"]',
      '[aria-label="Adaugă o descriere"][contenteditable="true"]',
      '[aria-label="Add a caption"][contenteditable="true"]',
      '[data-wa-media-caption="true"][contenteditable="true"]',
    ],
  };

  function first(root, key) {
    if (!root) return null;
    for (const selector of SELECTORS[key]) {
      try {
        const found = root.querySelector(selector);
        if (found) return found;
      } catch {
        // An invalid selector must not break the others.
      }
    }
    return null;
  }

  function all(root, key) {
    if (!root) return [];
    for (const selector of SELECTORS[key]) {
      try {
        const found = root.querySelectorAll(selector);
        if (found.length) return [...found];
      } catch {
        // Try the next one.
      }
    }
    return [];
  }

  function matchesAny(el, key) {
    return SELECTORS[key].some((selector) => {
      try {
        return el.matches(selector);
      } catch {
        return false;
      }
    });
  }

  function closestAny(el, key, stopAt) {
    for (let node = el; node && node !== stopAt; node = node.parentElement) {
      if (matchesAny(node, key)) return node;
    }
    return null;
  }

  // ---- Pure helpers (unit tested without a DOM) ----

  // "false_40712345678@c.us_3EB0A1" -> parts. Group ids carry the participant as a 4th part.
  function parseDataId(raw) {
    const value = String(raw || '');
    const match = /^(true|false)_([^_\s]+@[a-z.]+)_([^_\s]+)(?:_(\S+))?$/i.exec(value);
    if (!match) return null;
    const jid = match[2];
    const server = jid.slice(jid.indexOf('@') + 1).toLowerCase();
    const user = jid.slice(0, jid.indexOf('@'));
    return {
      fromMe: match[1] === 'true',
      jid,
      server,
      user,
      messageId: match[3],
      participant: match[4] || null,
      isGroup: server === 'g.us',
      isIndividual: server === 'c.us' || server === 's.whatsapp.net' || server === 'lid',
      phoneDigits: (server === 'c.us' || server === 's.whatsapp.net') && /^\d{6,15}$/.test(user) ? user : null,
    };
  }

  // A chat title that is itself a phone number ("+40 712 345 678") -> digits, else null.
  function phoneFromTitle(title) {
    const value = String(title || '').trim();
    if (!/^\+?[\d\s().-]{7,22}$/.test(value)) return null;
    const digits = value.replace(/\D/g, '');
    return digits.length >= 7 && digits.length <= 15 ? digits : null;
  }

  // "[10:15, 26.11.2026] Ana Pop: " -> { sentAt: ISO string | null, author }.
  function parsePrePlainText(raw) {
    const value = String(raw || '');
    const match = /^\s*\[([^\]]+)\]\s*(.*?):?\s*$/.exec(value);
    if (!match) return { sentAt: null, author: '' };
    const author = match[2].trim();
    const stamp = match[1];
    const time = /(\d{1,2})[:.](\d{2})(?::\d{2})?\s*([ap])?\.?\s?(?:m\.?)?/i.exec(stamp);
    const date = /(\d{1,4})[./-](\d{1,2})[./-](\d{1,4})/.exec(stamp.replace(time ? time[0] : '', ' '));
    if (!time || !date) return { sentAt: null, author };
    let hour = Number(time[1]);
    const minute = Number(time[2]);
    const meridiem = time[3] ? time[3].toLowerCase() : null;
    if (meridiem === 'p' && hour < 12) hour += 12;
    if (meridiem === 'a' && hour === 12) hour = 0;
    const a = Number(date[1]);
    const b = Number(date[2]);
    const c = Number(date[3]);
    let year;
    let month;
    let day;
    if (date[1].length === 4) {
      [year, month, day] = [a, b, c];
    } else {
      year = c < 100 ? 2000 + c : c;
      // Day first (Romanian locale) unless only month-first is possible.
      if (b > 12 && a <= 12) [month, day] = [a, b];
      else [day, month] = [a, b];
    }
    if (month < 1 || month > 12 || day < 1 || day > 31 || hour > 23 || minute > 59) {
      return { sentAt: null, author };
    }
    const local = new Date(year, month - 1, day, hour, minute, 0, 0);
    if (Number.isNaN(local.getTime()) || local.getDate() !== day) return { sentAt: null, author };
    return { sentAt: local.toISOString(), author };
  }

  // Small stable hash for chats that expose neither a phone number nor an id.
  function hashText(text) {
    let hash = 0x811c9dc5;
    for (let i = 0; i < text.length; i += 1) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 0x01000193);
    }
    return (hash >>> 0).toString(16).padStart(8, '0');
  }

  function cleanText(text) {
    return String(text || '')
      .replace(/[‎‏‪-‮﻿]/g, '')
      .replace(/ /g, ' ')
      .replace(/[ \t]+\n/g, '\n')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
  }

  // ---- DOM reading ----

  // Text with emoji (img alt) and line breaks preserved.
  function textOf(el) {
    let out = '';
    const walk = (node) => {
      for (const child of node.childNodes) {
        if (child.nodeType === 3) {
          out += child.nodeValue;
        } else if (child.nodeType === 1) {
          const tag = child.tagName;
          if (tag === 'IMG') out += child.getAttribute('data-plain-text') || child.getAttribute('alt') || '';
          else if (tag === 'BR') out += '\n';
          else if (child.getAttribute('role') === 'button') continue; // "Read more"
          else walk(child);
        }
      }
    };
    walk(el);
    return cleanText(out);
  }

  function readQuoted(node) {
    const quoted = first(node, 'quoted');
    if (!quoted) return { el: null, text: '' };
    const inner = first(quoted, 'quotedText') || quoted;
    return { el: quoted, text: textOf(inner) };
  }

  function readAttachment(node, skip) {
    const inside = (el) => skip.some((s) => s && s.contains(el));
    const image = all(node, 'image').find((img) => !inside(img) && !matchesAny(img, 'inlineImage'));
    if (image) return { type: 'image', name: '', src: image.currentSrc || image.src, el: image };
    const pendingImage = all(node, 'imagePlaceholder').find((img) => !inside(img) && !matchesAny(img, 'inlineImage'));
    if (pendingImage) return { type: 'image', name: '', src: null, el: pendingImage };
    const marker = all(node, 'document').find((el) => !inside(el));
    if (marker) {
      const nameEl = first(node, 'documentName');
      const name = cleanText(marker.getAttribute('title') || '').replace(/^(Descarcă|Download)\s*/i, '').replace(/^["„“”]|["„“”]$/g, '')
        || (nameEl && !inside(nameEl) ? textOf(nameEl) : '');
      const link = first(node, 'documentBlob');
      return { type: 'document', name: name.slice(0, 200), src: link ? link.href : null, el: link };
    }
    return null;
  }

  function readMessage(node) {
    const id = node.getAttribute('data-id') || '';
    const parsed = parseDataId(id);
    let direction = null;
    if (parsed) direction = parsed.fromMe ? 'out' : 'in';
    else if (closestAny(node, 'outgoing') || first(node, 'outgoing')) direction = 'out';
    else if (closestAny(node, 'incoming') || first(node, 'incoming')) direction = 'in';
    if (!direction) return null; // system row (date divider, notice)

    const quoted = readQuoted(node);
    const pre = first(node, 'prePlainText');
    const meta = parsePrePlainText(pre ? pre.getAttribute('data-pre-plain-text') : '');
    const body = all(node, 'textBody').find((el) => !(quoted.el && quoted.el.contains(el)));
    const text = body ? textOf(body) : '';
    const attachment = readAttachment(node, [quoted.el, body]);
    if (!text && !attachment) return null;

    return {
      id,
      direction,
      text,
      sent_at: meta.sentAt,
      author: meta.author,
      quoted: quoted.text || null,
      attachment, // { type, name, src, el } | null, never sent to the backend as is
      parsed,
    };
  }

  function readMessages(pane) {
    const seen = new Set();
    const messages = [];
    for (const node of all(pane, 'messageNode')) {
      const id = node.getAttribute('data-id');
      if (!id || seen.has(id)) continue;
      // Skip wrappers nested inside another message node.
      if (node.parentElement && node.parentElement.closest('[data-id]')) continue;
      seen.add(id);
      const message = readMessage(node);
      if (message) messages.push(message);
    }
    return messages;
  }

  // Returns { open, group, supported, chat: { key, name, phone }, messages }.
  function readConversation(doc = document) {
    const pane = first(doc, 'chatPane');
    if (!pane) return { open: false, group: false, supported: false, chat: null, messages: [] };

    const titleEl = first(pane, 'headerTitle');
    const name = titleEl ? cleanText(titleEl.getAttribute('title') || textOf(titleEl)) : '';
    const messages = readMessages(pane);

    // The chat id is the remote id shared by the rows.
    const counts = new Map();
    for (const m of messages) if (m.parsed) counts.set(m.parsed.jid, (counts.get(m.parsed.jid) || 0) + 1);
    const jid = [...counts.entries()].sort((x, y) => y[1] - x[1])[0]?.[0] || null;
    const sample = messages.find((m) => m.parsed && m.parsed.jid === jid)?.parsed || null;

    const group = Boolean(sample && sample.isGroup) || messages.some((m) => m.parsed && m.parsed.participant);
    const supported = !group && (!sample || sample.isIndividual);
    const digits = (sample && sample.phoneDigits) || phoneFromTitle(name);
    let key = null;
    if (digits) key = digits;
    else if (jid) key = jid;
    else if (name) key = `titlu-${hashText(name)}`;

    return {
      open: true,
      group,
      supported,
      chat: key ? { key, name, phone: digits ? `+${digits}` : null } : null,
      messages,
    };
  }

  // Backend shape for one message: quoted reply and unuploaded attachments sit in dedicated fields.
  function toApiMessage(message, uploads) {
    const uploadId = uploads && uploads.get(message.id);
    const unuploaded = !uploadId && message.attachment
      ? [{ kind: message.attachment.type, filename: message.attachment.name || null }]
      : [];
    return {
      id: message.id,
      direction: message.direction,
      text: message.text || '',
      quoted_text: message.quoted ? message.quoted.slice(0, 1000) : null,
      sent_at: message.sent_at,
      attachments: uploadId ? [{ upload_id: uploadId }] : [],
      unuploaded_attachments: unuploaded,
    };
  }

  function findComposer(doc = document) {
    return first(first(doc, 'chatPane'), 'composer');
  }

  function findMediaPreview(doc = document) {
    return first(doc, 'mediaPreview');
  }

  function findMediaCaption(doc = document) {
    const preview = findMediaPreview(doc);
    return first(preview || doc, 'mediaCaption');
  }

  function findAppRoot(doc = document) {
    return first(doc, 'appRoot');
  }

  // Reports which selectors match on the current page, so breakage is visible.
  function selfTest(doc = document) {
    const pane = first(doc, 'chatPane');
    const nodes = pane ? all(pane, 'messageNode') : [];
    const parsedIds = nodes.filter((n) => parseDataId(n.getAttribute('data-id'))).length;
    const withMeta = nodes.filter((n) => first(n, 'prePlainText')).length;
    const withText = nodes.filter((n) => first(n, 'textBody')).length;
    const checks = [
      { name: 'appRoot', label: 'Rădăcina aplicației', ok: Boolean(first(doc, 'appRoot')), needsChat: false },
      { name: 'chatPane', label: 'Panoul conversației', ok: Boolean(pane), needsChat: true },
      { name: 'headerTitle', label: 'Titlul conversației', ok: Boolean(first(pane, 'headerTitle')), needsChat: true },
      { name: 'messageNode', label: 'Rândurile de mesaj', ok: nodes.length > 0, needsChat: true },
      { name: 'dataId', label: 'Identificatorul mesajului (data-id)', ok: parsedIds > 0, needsChat: true },
      { name: 'prePlainText', label: 'Ora mesajului (data-pre-plain-text)', ok: withMeta > 0, needsChat: true },
      { name: 'textBody', label: 'Textul mesajului', ok: withText > 0, needsChat: true },
      { name: 'composer', label: 'Caseta de mesaj', ok: Boolean(first(pane, 'composer')), needsChat: true },
    ];
    let status;
    if (!checks[0].ok) status = 'check';
    else if (!pane) status = 'no_chat';
    else status = checks.every((c) => c.ok) ? 'ok' : 'check';
    return {
      status, // 'ok' | 'check' | 'no_chat'
      checks,
      failed: checks.filter((c) => !c.ok && (pane || !c.needsChat)).map((c) => c.label),
      counts: { messages: nodes.length, parsedIds, withMeta, withText },
    };
  }

  NS.SELECTORS = SELECTORS;
  NS.Reader = {
    parseDataId,
    parsePrePlainText,
    phoneFromTitle,
    hashText,
    cleanText,
    textOf,
    readConversation,
    toApiMessage,
    findComposer,
    findMediaPreview,
    findMediaCaption,
    findAppRoot,
    selfTest,
  };
})();
