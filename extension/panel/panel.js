// Docked panel UI, rendered inside a shadow root. Backend text is always set with
// textContent: nothing from the backend or from WhatsApp is ever parsed as HTML.
(() => {
  'use strict';
  const NS = (globalThis.EcQuote = globalThis.EcQuote || {});

  const KIND_LABELS = {
    reply: 'Răspuns',
    question: 'Întrebare pentru client',
    offer: 'Ofertă',
    needs_human: 'Necesită intervenție umană',
    none: 'Fără sugestie',
  };

  const SVG_NS = 'http://www.w3.org/2000/svg';
  const ICONS = {
    collapse: 'M9 6l6 6-6 6',
    expand: 'M15 6l-6 6 6 6',
  };

  function el(tag, props = {}, ...children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(props)) {
      if (value === undefined || value === null || value === false) continue;
      if (key === 'class') node.className = value;
      else if (key === 'text') node.textContent = value;
      else if (key === 'on') for (const [event, fn] of Object.entries(value)) node.addEventListener(event, fn);
      else if (key === 'data') for (const [k, v] of Object.entries(value)) node.dataset[k] = String(v);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
    for (const child of children.flat()) if (child) node.append(child);
    return node;
  }

  function icon(name) {
    const svg = document.createElementNS(SVG_NS, 'svg');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('aria-hidden', 'true');
    const path = document.createElementNS(SVG_NS, 'path');
    path.setAttribute('d', ICONS[name]);
    path.setAttribute('fill', 'none');
    path.setAttribute('stroke', 'currentColor');
    path.setAttribute('stroke-width', '2');
    path.setAttribute('stroke-linecap', 'round');
    path.setAttribute('stroke-linejoin', 'round');
    svg.append(path);
    return svg;
  }

  const button = (label, cls, onClick, extra = {}) =>
    el('button', { type: 'button', class: `btn ${cls || ''}`.trim(), text: label, on: { click: onClick }, ...extra });

  // Decimal strings are shown as received; only the separator is localized.
  function money(value) {
    const text = String(value ?? '');
    return /^-?\d+\.\d+$/.test(text) ? text.replace('.', ',') : text;
  }

  function create(on) {
    const host = document.createElement('div');
    host.id = 'ecq-assist-root';
    const shadow = host.attachShadow({ mode: 'open' });
    try {
      const sheet = new CSSStyleSheet();
      sheet.replaceSync(NS.PANEL_CSS);
      shadow.adoptedStyleSheets = [sheet];
    } catch {
      shadow.append(el('style', { text: NS.PANEL_CSS }));
    }

    const state = { suggestion: null, original: '', imageBlob: null, imageUrl: null, noticeTimer: null, busy: false };

    // ---- Static skeleton ----
    const chatName = el('div', { class: 'chat', text: 'Nicio conversație deschisă' });
    const collapseBtn = el(
      'button',
      { type: 'button', class: 'icon-btn', 'aria-label': 'Restrânge panoul', title: 'Restrânge panoul', on: { click: () => on.collapse(true) } },
      icon('collapse'),
    );
    const head = el(
      'header',
      { class: 'head' },
      el('div', { class: 'mark', text: 'EC', 'aria-hidden': 'true' }),
      el('div', { class: 'titles' }, el('div', { class: 'title', text: 'Asistent ofertare' }), chatName),
      collapseBtn,
    );

    const notice = el('div', { class: 'notice', role: 'status', hidden: true });
    const banner = el(
      'div',
      { class: 'banner', hidden: true },
      el('span', { text: 'Au apărut mesaje noi în conversație.' }),
      button('Actualizează', 'link', () => on.request()),
    );
    const view = el('div', { class: 'view', 'aria-live': 'polite' });

    // Attachment section.
    const attachInfo = el('p', { class: 'attach-info' });
    const attachBtn = button('Trimite fișierul la verificare', 'wide', () => on.uploadFromChat());
    const fileInput = el('input', {
      type: 'file',
      class: 'visually-hidden',
      tabindex: '-1',
      accept: 'image/*,application/pdf,.pdf,.ai,.eps,.svg,.psd,.cdr,.tif,.tiff',
      'aria-hidden': 'true',
    });
    fileInput.addEventListener('change', () => {
      const file = fileInput.files && fileInput.files[0];
      fileInput.value = '';
      if (file) on.uploadFile(file);
    });
    const drop = el(
      'div',
      { class: 'drop' },
      el('span', { text: 'Trageți aici fișierul descărcat sau ' }),
      button('alegeți din calculator', 'link', () => fileInput.click()),
      fileInput,
    );
    const attachStatus = el('p', { class: 'attach-status', role: 'status', hidden: true });
    const attach = el(
      'section',
      { class: 'attach', hidden: true, 'aria-label': 'Fișier de la client' },
      el('h3', { class: 'label', text: 'Fișier de la client' }),
      attachInfo,
      attachBtn,
      drop,
      attachStatus,
    );
    for (const type of ['dragenter', 'dragover']) {
      attach.addEventListener(type, (event) => {
        event.preventDefault();
        drop.dataset.over = 'true';
      });
    }
    attach.addEventListener('dragleave', () => delete drop.dataset.over);
    attach.addEventListener('drop', (event) => {
      event.preventDefault();
      delete drop.dataset.over;
      const file = event.dataTransfer && event.dataTransfer.files && event.dataTransfer.files[0];
      if (file) on.uploadFile(file);
    });

    const body = el('div', { class: 'body' }, notice, banner, view, attach);
    const confirmBox = el('div', { class: 'confirm', role: 'alertdialog', 'aria-label': 'Confirmare', hidden: true });
    const actions = el('div', { class: 'actions', hidden: true });

    const compatText = el('span', { text: 'Compatibilitate WhatsApp Web: se verifică' });
    const checks = el('ul', { class: 'checks', hidden: true, id: 'ecq-checks' });
    const compat = el(
      'button',
      {
        type: 'button',
        class: 'compat',
        'aria-expanded': 'false',
        'aria-controls': 'ecq-checks',
        title: 'Arată detaliile verificării',
        on: {
          click: () => {
            checks.hidden = !checks.hidden;
            compat.setAttribute('aria-expanded', String(!checks.hidden));
          },
        },
      },
      el('span', { class: 'dot', 'aria-hidden': 'true' }),
      compatText,
    );
    const foot = el('footer', { class: 'foot' }, compat, button('Opțiuni', 'link', () => on.openOptions()));

    const panel = el('section', { class: 'panel', 'aria-label': 'Asistent ofertare EC Quote' }, head, body, confirmBox, actions, checks, foot);
    const rail = el(
      'button',
      { type: 'button', class: 'rail', 'aria-label': 'Deschide asistentul de ofertare', title: 'Deschide asistentul de ofertare', on: { click: () => on.collapse(false) } },
      el('span', { class: 'mark', text: 'EC', 'aria-hidden': 'true' }),
      icon('expand'),
      el('span', { class: 'rail-label', text: 'Asistent ofertare' }),
    );
    const root = el('div', { class: 'ecq', data: { theme: 'light', collapsed: 'false' } }, rail, panel);
    shadow.append(root);

    // Keys typed in the panel must not reach WhatsApp's global shortcuts.
    for (const type of ['keydown', 'keyup', 'keypress']) {
      root.addEventListener(type, (event) => {
        if (event.key === 'Escape' && !confirmBox.hidden) hideConfirm();
        event.stopPropagation();
      });
    }

    // ---- Helpers ----
    let textarea = null;

    function notify(text, tone = 'info', sticky = false) {
      clearTimeout(state.noticeTimer);
      notice.textContent = text || '';
      notice.dataset.tone = tone;
      notice.hidden = !text;
      if (text && !sticky) state.noticeTimer = setTimeout(() => { notice.hidden = true; }, 7000);
    }

    function hideConfirm() {
      confirmBox.hidden = true;
      confirmBox.replaceChildren();
      actions.hidden = !actions.childElementCount;
    }

    // buttons: [{ label, primary, run }]. "Renunță" is always added.
    function confirm(message, buttons) {
      confirmBox.replaceChildren(
        el('p', { text: message }),
        el(
          'div',
          { class: 'row' },
          buttons.map((b) => button(b.label, b.primary ? 'primary' : '', () => { hideConfirm(); b.run(); })),
          button('Renunță', '', hideConfirm),
        ),
      );
      confirmBox.hidden = false;
      actions.hidden = true;
      confirmBox.querySelector('button').focus();
    }

    async function copyText(text, done) {
      try {
        await navigator.clipboard.writeText(text);
        notify(done);
      } catch {
        notify('Copierea nu a reușit. Selectați textul și folosiți Ctrl+C.', 'error');
      }
    }

    function autoSize() {
      if (!textarea) return;
      textarea.style.height = 'auto';
      textarea.style.height = `${Math.min(230, Math.max(96, textarea.scrollHeight + 2))}px`;
    }

    function setImageBlob(blob) {
      if (state.imageUrl) URL.revokeObjectURL(state.imageUrl);
      state.imageBlob = blob || null;
      state.imageUrl = blob ? URL.createObjectURL(blob) : null;
    }

    // ---- Views ----
    function renderState({ title, text, tone, action, loading }) {
      textarea = null;
      actions.replaceChildren();
      actions.hidden = true;
      hideConfirm();
      view.replaceChildren(
        el(
          'div',
          { class: 'state', data: { tone: tone || 'info' } },
          loading ? el('div', { class: 'spinner', 'aria-hidden': 'true' }) : null,
          title ? el('strong', { text: title }) : null,
          text ? el('p', { text }) : null,
          action ? button(action.label, action.primary === false ? '' : 'primary', action.run) : null,
        ),
      );
    }

    function offerTable(lines) {
      // A label shared by every row is shown once, above the table.
      const labels = new Set(lines.map((line) => line.label));
      const shared = labels.size === 1 ? lines[0].label : '';
      const rows = lines.map((line) => {
        const showLabel = !shared && line.label && line.quantity && line.label !== line.quantity;
        return el(
          'tr',
          { data: { highlighted: line.highlighted ? 'true' : 'false' } },
          el('td', {}, el('span', { text: line.quantity || line.label }), showLabel ? el('span', { class: 'line-label', text: line.label }) : null),
          el('td', { text: money(line.unit_price) }),
          el('td', { text: money(line.total_ex_vat) }),
          el('td', { text: money(line.total) }),
        );
      });
      return el(
        'div',
        {},
        el('h3', { class: 'label', text: 'Variante de preț' }),
        shared ? el('p', { class: 'table-title', text: shared }) : null,
        el(
          'div',
          { class: 'table-wrap' },
          el(
            'table',
            {},
            el('thead', {}, el('tr', {}, ['Cantitate', 'Preț/buc', 'Fără TVA', 'Cu TVA'].map((t) => el('th', { scope: 'col', text: t })))),
            el('tbody', {}, rows),
          ),
        ),
        el('p', { class: 'caption', text: 'Valori în lei, primite de la server.' }),
      );
    }

    const imageSlot = el('div', {});
    function renderImage(status) {
      if (!state.suggestion || !state.suggestion.image_url) return imageSlot.replaceChildren();
      let content;
      if (status === 'ready' && state.imageUrl) {
        const current = state.suggestion;
        const currentBlob = state.imageBlob;
        content = [
          el('img', { src: state.imageUrl, alt: 'Imaginea ofertei' }),
          el(
            'div',
            { class: 'row' },
            button('Atașează imaginea', 'small primary', () => {
              if (state.suggestion !== current || !state.imageBlob || !on.attachImage) return;
              on.attachImage(currentBlob, textarea ? textarea.value : '');
            }),
            button('Copiază imaginea', 'small', async () => {
              try {
                const png = await NS.Media.toPng(state.imageBlob);
                await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
                notify('Imaginea a fost copiată. Lipiți-o în conversație cu Ctrl+V.');
              } catch {
                notify('Imaginea nu a putut fi copiată. Folosiți „Descarcă”.', 'error');
              }
            }),
            button('Descarcă', 'small', () => {
              const link = el('a', { href: state.imageUrl, download: 'oferta.png' });
              shadow.append(link);
              link.click();
              link.remove();
            }),
          ),
        ];
      } else if (status === 'error') {
        content = [el('div', { class: 'image-state', text: 'Imaginea ofertei nu a putut fi încărcată.' })];
      } else {
        content = [el('div', { class: 'image-state', text: 'Se încarcă imaginea ofertei...' })];
      }
      imageSlot.replaceChildren(el('h3', { class: 'label', text: 'Imaginea ofertei' }), el('div', { class: 'image-box' }, content));
    }

    function renderSuggestion(suggestion) {
      hideConfirm();
      state.suggestion = suggestion;
      state.original = suggestion.text || '';
      const hasText = Boolean(state.original.trim());
      const parts = [];

      parts.push(el('div', { class: 'badge-row' }, el('span', { class: 'badge', data: { kind: suggestion.kind }, text: KIND_LABELS[suggestion.kind] || KIND_LABELS.none })));

      if (suggestion.note_for_staff || suggestion.handoff_reason) {
        parts.push(
          el(
            'div',
            { class: 'note', role: 'note' },
            el('h3', { class: 'label', text: 'Notă internă (nu se trimite)' }),
            suggestion.note_for_staff ? el('p', { text: suggestion.note_for_staff }) : null,
            suggestion.handoff_reason ? el('p', { class: 'reason', text: `Motiv: ${suggestion.handoff_reason}` }) : null,
          ),
        );
      }

      if (suggestion.payment_url) {
        parts.push(
          el(
            'div',
            {},
            el('h3', { class: 'label', text: 'Link de plată' }),
            el(
              'div',
              { class: 'pay' },
              el('span', { class: 'pay-url', text: suggestion.payment_url }),
              button('Copiază linkul', 'small', () => copyText(suggestion.payment_url, 'Linkul de plată a fost copiat.')),
            ),
          ),
        );
      }

      textarea = null;
      if (hasText) {
        textarea = el('textarea', { id: 'ecq-text', spellcheck: 'true', lang: 'ro', 'aria-describedby': 'ecq-text-hint' });
        textarea.value = state.original;
        textarea.addEventListener('input', autoSize);
        parts.push(
          el(
            'div',
            {},
            el('label', { class: 'label', for: 'ecq-text', text: 'Text propus' }),
            textarea,
            el('p', { class: 'hint', id: 'ecq-text-hint', text: 'Puteți edita textul. Mesajul îl trimiteți dvs. din WhatsApp.' }),
          ),
        );
      } else if (suggestion.kind === 'none' && !suggestion.note_for_staff) {
        parts.push(el('div', { class: 'state' }, el('p', { text: 'Nu există o sugestie pentru această conversație.' })));
      }

      if (suggestion.options.length && textarea) {
        parts.push(
          el(
            'div',
            {},
            el('h3', { class: 'label', text: 'Opțiuni de răspuns' }),
            el(
              'div',
              { class: 'chips' },
              suggestion.options.map((option) =>
                el('button', {
                  type: 'button',
                  class: 'chip',
                  text: option,
                  title: 'Adaugă varianta în text',
                  on: {
                    click: () => {
                      const current = textarea.value.replace(/\s+$/, '');
                      textarea.value = current ? `${current}\n${option}` : option;
                      autoSize();
                      textarea.focus();
                    },
                  },
                }),
              ),
            ),
          ),
        );
      }

      if (suggestion.offer_lines.length) parts.push(offerTable(suggestion.offer_lines));
      if (suggestion.image_url) {
        renderImage(state.imageBlob ? 'ready' : 'loading');
        parts.push(imageSlot);
      }

      view.replaceChildren(...parts);
      autoSize();

      const buttons = [];
      if (textarea) {
        buttons.push(button('Inserează în mesaj', 'primary wide', () => on.insert(textarea.value), { data: { action: 'insert' } }));
        buttons.push(button('Copiază textul', '', () => copyText(textarea.value, 'Textul a fost copiat.'), { data: { action: 'copy' } }));
      }
      buttons.push(button('Altă sugestie', textarea ? '' : 'wide', () => on.request(), { data: { action: 'retry' } }));
      if (suggestion.can_create_payment_link && !suggestion.payment_url) {
        buttons.push(
          button(
            'Generează link de plată',
            'wide',
            () =>
              confirm('Se va crea o comandă nefinalizată (draft) pentru acest client și un link de plată. Continuați?', [
                { label: 'Creează linkul', primary: true, run: () => on.paymentLink(textarea ? textarea.value : '') },
              ]),
            { data: { action: 'payment' } },
          ),
        );
      }
      actions.replaceChildren(...buttons);
      actions.hidden = false;
    }

    // ---- Public API ----
    return {
      host,
      confirm,
      notify,

      setTheme(theme) {
        root.dataset.theme = theme === 'dark' ? 'dark' : 'light';
      },
      setCollapsed(collapsed) {
        root.dataset.collapsed = collapsed ? 'true' : 'false';
      },
      setFloating(floating) {
        root.dataset.floating = floating ? 'true' : 'false';
      },
      setChat(name) {
        chatName.textContent = name || 'Nicio conversație deschisă';
        chatName.title = name || '';
      },
      setStale(stale) {
        banner.hidden = !stale;
      },
      setBusy(busy) {
        state.busy = busy;
        for (const b of actions.querySelectorAll('button')) b.disabled = busy;
        for (const b of imageSlot.querySelectorAll('button')) b.disabled = busy;
      },

      showLoading(text) {
        state.suggestion = null;
        setImageBlob(null);
        banner.hidden = true;
        renderState({ loading: true, text: text || 'Se pregătește sugestia...' });
      },
      showState(options) {
        state.suggestion = null;
        setImageBlob(null);
        banner.hidden = true;
        renderState(options);
      },
      showSuggestion(suggestion, { keepImage = false } = {}) {
        if (!keepImage) setImageBlob(null);
        banner.hidden = true;
        renderSuggestion(suggestion);
      },
      setImage(status, blob) {
        if (status === 'ready') setImageBlob(blob);
        renderImage(status);
      },

      suggestion: () => state.suggestion,
      isDirty: () => Boolean(textarea && textarea.value !== state.original),
      isTextEdited: () => Boolean(textarea && textarea.value.trim() !== state.original.trim()),

      // attachment: { visible, info, canRead, busy, status, tone }
      setAttachment({ visible, info, canRead, busy, status, tone }) {
        attach.hidden = !visible;
        attachInfo.textContent = info || '';
        attachBtn.hidden = !canRead;
        attachBtn.disabled = Boolean(busy);
        attachBtn.textContent = busy ? 'Se trimite...' : 'Trimite fișierul la verificare';
        attachStatus.hidden = !status;
        attachStatus.textContent = status || '';
        attachStatus.dataset.tone = tone || 'info';
      },

      setCompat(result) {
        compat.dataset.status = result.status;
        const labels = { ok: 'ok', check: 'de verificat', no_chat: 'deschideți o conversație' };
        compatText.textContent = `Compatibilitate WhatsApp Web: ${labels[result.status] || 'de verificat'}`;
        checks.replaceChildren(
          ...result.checks.map((check) =>
            el('li', { data: { ok: String(check.ok) } }, el('span', { text: check.label }), el('span', { text: check.ok ? 'ok' : 'negăsit' })),
          ),
        );
      },
    };
  }

  NS.Panel = { create, KIND_LABELS };
})();
