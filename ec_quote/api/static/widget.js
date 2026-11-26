/*
 * Widgetul de chat ec-quote (fara dependinte). Baza viitorului bloc de tema.
 *
 * <script src="widget.js" defer data-api-base="https://quote.exemplu.ro" data-max-upload-mb="20"></script>
 *
 * Textul venit de la server se pune numai prin textContent; nimic nu se interpreteaza ca HTML.
 */
(function () {
  "use strict";

  if (window.EcQuoteChat) return;

  var script = document.currentScript;
  var cfg = (script && script.dataset) || {};
  var API = (cfg.apiBase || "").replace(/\/+$/, "");
  var MAX_MB = Number(cfg.maxUploadMb) || 20;
  var ACCEPT = ".pdf,.png,.jpg,.jpeg,.webp,.svg,application/pdf,image/png,image/jpeg,image/webp,image/svg+xml";
  var STORAGE_KEY = "ecq_session";
  var POLL_EVERY_MS = 5000;
  var POLL_FOR_MS = 15 * 60 * 1000;

  var T = {
    launcher: "Cere o ofertă",
    open: "Deschide chatul pentru ofertă",
    close: "Închide chatul",
    title: "Ofertă pe loc",
    subtitle: "Asistent automat. Prețul este cel de pe site.",
    log: "Conversație",
    welcome: "Bună ziua! Spuneți-ne ce etichete sau stickere doriți (dimensiune, cantitate, material) și primiți prețul pe loc. Puteți atașa și fișierul cu grafica.",
    inputLabel: "Mesajul dumneavoastră",
    placeholder: "Scrieți mesajul",
    send: "Trimite mesajul",
    attach: "Atașați un fișier",
    typing: "Se pregătește răspunsul",
    fileSent: "Fișier trimis: ",
    imageAlt: "Imagine trimisă de Etichete Creative",
    openImage: "Deschide imaginea într-o filă nouă",
    you: "Dumneavoastră",
    us: "Etichete Creative",
    errSend: "Mesajul nu a putut fi trimis. Verificați conexiunea și încercați din nou.",
    errRate: "Ați trimis prea multe mesaje. Încercați din nou peste un minut.",
    errFile: "Fișierul nu poate fi primit. Acceptăm PDF, PNG, JPG, WEBP sau SVG de cel mult " + MAX_MB + " MB.",
    errStart: "Chatul nu este disponibil momentan. Încercați din nou peste câteva minute."
  };

  var ICONS = {
    chat: "M4 5h16v11H9l-5 4V5z",
    close: "M6 6l12 12M18 6L6 18",
    send: "M4 12l16-7-6 16-3-6-7-3z",
    clip: "M8 12.5l6.2-6.2a3 3 0 014.3 4.3l-7.6 7.6a5 5 0 01-7-7l7-7"
  };

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (name) {
      if (name === "text") node.textContent = attrs[name];
      else node.setAttribute(name, attrs[name]);
    });
    (children || []).forEach(function (child) { node.appendChild(child); });
    return node;
  }

  function icon(name) {
    var ns = "http://www.w3.org/2000/svg";
    var svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    var path = document.createElementNS(ns, "path");
    path.setAttribute("d", ICONS[name]);
    svg.appendChild(path);
    return svg;
  }

  // Textul devine noduri de text si linkuri https; niciodata HTML.
  function appendText(parent, text) {
    var pattern = /https:\/\/[^\s<>"']+/g;
    var last = 0;
    var match;
    while ((match = pattern.exec(text))) {
      var url = match[0].replace(/[.,;:!?)]+$/, "");
      parent.appendChild(document.createTextNode(text.slice(last, match.index)));
      parent.appendChild(el("a", { href: url, target: "_blank", rel: "noopener noreferrer", text: url }));
      last = match.index + url.length;
      pattern.lastIndex = last;
    }
    parent.appendChild(document.createTextNode(text.slice(last)));
  }

  function newId() {
    var bytes = new Uint8Array(12);
    (window.crypto || window.msCrypto).getRandomValues(bytes);
    return Array.prototype.map.call(bytes, function (b) { return ("0" + b.toString(16)).slice(-2); }).join("");
  }

  var store = {
    get: function () { try { return window.sessionStorage.getItem(STORAGE_KEY); } catch (e) { return null; } },
    set: function (value) {
      try {
        if (value) window.sessionStorage.setItem(STORAGE_KEY, value);
        else window.sessionStorage.removeItem(STORAGE_KEY);
      } catch (e) { /* fara stocare: sesiunea traieste cat pagina */ }
    }
  };

  var token = store.get();
  var busy = false;
  var pollTimer = null;
  var pollUntil = 0;
  var greeted = false;

  // ---------- interfata ----------

  var launcher = el("button", {
    type: "button", "class": "ecq-launcher", "aria-expanded": "false",
    "aria-controls": "ecq-panel", "aria-label": T.open
  }, [icon("chat"), el("span", { text: T.launcher })]);

  var closeBtn = el("button", { type: "button", "class": "ecq-close", "aria-label": T.close }, [icon("close")]);
  var log = el("div", { "class": "ecq-log", role: "log", "aria-live": "polite", "aria-label": T.log, tabindex: "0" });
  var status = el("p", { "class": "ecq-status", role: "status" });
  var fileInput = el("input", { type: "file", id: "ecq-file", "class": "ecq-file", accept: ACCEPT });
  var attach = el("label", { "for": "ecq-file", "class": "ecq-attach", title: T.attach },
    [icon("clip"), el("span", { "class": "ecq-sr", text: T.attach })]);
  var input = el("textarea", { id: "ecq-input", "class": "ecq-input", rows: "1", maxlength: "4000", placeholder: T.placeholder });
  var sendBtn = el("button", { type: "submit", "class": "ecq-send", "aria-label": T.send }, [icon("send")]);
  var form = el("form", { "class": "ecq-form", novalidate: "" }, [
    fileInput, attach, el("label", { "for": "ecq-input", "class": "ecq-sr", text: T.inputLabel }), input, sendBtn
  ]);
  var panel = el("section", {
    id: "ecq-panel", "class": "ecq-panel", role: "dialog", "aria-labelledby": "ecq-title", hidden: ""
  }, [
    el("header", { "class": "ecq-header" }, [
      el("div", {}, [
        el("h2", { id: "ecq-title", "class": "ecq-title", text: T.title }),
        el("p", { "class": "ecq-subtitle", text: T.subtitle })
      ]),
      closeBtn
    ]),
    log, status, form
  ]);
  var root = el("div", { "class": "ecq", lang: "ro" }, [panel, launcher]);

  function scrollDown() { log.scrollTop = log.scrollHeight; }

  function addMessage(who, build) {
    var bubble = el("div", { "class": "ecq-bubble" });
    var row = el("div", { "class": "ecq-msg ecq-" + who }, [
      el("span", { "class": "ecq-sr", text: (who === "user" ? T.you : T.us) + ": " }), bubble
    ]);
    build(bubble);
    log.appendChild(row);
    scrollDown();
    return row;
  }

  function addNote(text, kind) {
    var note = el("p", { "class": "ecq-note ecq-note-" + kind });
    appendText(note, text);
    log.appendChild(note);
    scrollDown();
  }

  function setStatus(text) { status.textContent = text || ""; }

  function setBusy(value) {
    busy = value;
    sendBtn.disabled = value;
    fileInput.disabled = value;
    attach.classList.toggle("ecq-disabled", value);
    setStatus(value ? T.typing : "");
    status.classList.toggle("ecq-typing", value);
  }

  function render(action) {
    if (action.kind === "notice" || action.kind === "handoff") {
      addNote(action.text, action.kind);
      return;
    }
    addMessage("bot", function (bubble) {
      if (action.kind === "image" && action.image_url) {
        var img = el("img", { src: action.image_url, alt: action.text || T.imageAlt, loading: "lazy" });
        img.addEventListener("load", scrollDown);
        bubble.appendChild(el("a", {
          href: action.image_url, target: "_blank", rel: "noopener noreferrer",
          "class": "ecq-image", title: T.openImage
        }, [img]));
      }
      if (action.text) {
        var text = el("p", { "class": "ecq-text" });
        appendText(text, action.text);
        bubble.appendChild(text);
      }
      if (action.buttons && action.buttons.length) {
        var group = el("div", { "class": "ecq-buttons", role: "group", "aria-label": action.text || T.title });
        action.buttons.forEach(function (button) {
          var node = el("button", { type: "button", "class": "ecq-reply", text: button.title });
          node.addEventListener("click", function () {
            if (busy) return;
            Array.prototype.forEach.call(group.querySelectorAll("button"), function (b) { b.disabled = true; });
            node.classList.add("ecq-chosen");
            addMessage("user", function (bubble2) { bubble2.textContent = button.title; });
            deliver("/v1/chat/message", jsonBody({ button_id: button.id, message_id: newId() }));
            input.focus();
          });
          group.appendChild(node);
        });
        bubble.appendChild(group);
      }
    });
  }

  // ---------- retea ----------

  function jsonBody(data) {
    return { headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) };
  }

  function ensureSession() {
    if (token) return Promise.resolve(token);
    return fetch(API + "/v1/chat/session", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg.adSource ? { ad_source: cfg.adSource } : {})
    }).then(function (response) {
      if (!response.ok) throw { status: response.status };
      return response.json();
    }).then(function (data) {
      token = data.session_token;
      store.set(token);
      return token;
    });
  }

  function call(method, path, options, retried) {
    return ensureSession().then(function () {
      var headers = Object.assign({ Authorization: "Bearer " + token }, (options && options.headers) || {});
      return fetch(API + path, { method: method, headers: headers, body: options && options.body });
    }).then(function (response) {
      if (response.status === 401 && !retried) {
        // Sesiune expirata: una noua si o singura reincercare.
        token = null;
        store.set(null);
        return call(method, path, options, true);
      }
      if (!response.ok) throw { status: response.status };
      return response.json();
    });
  }

  function handle(payload) {
    (payload.actions || []).forEach(render);
    if (payload.poll) startPolling();
    else if ((payload.actions || []).length) stopPolling();
  }

  function fail(error, isFile) {
    var status = error && error.status;
    if (status === 429) addNote(T.errRate, "error");
    else if (isFile && (status === 413 || status === 415 || status === 422)) addNote(T.errFile, "error");
    else addNote(T.errSend, "error");
  }

  function deliver(path, options, isFile) {
    setBusy(true);
    return call("POST", path, options).then(handle).catch(function (error) { fail(error, isFile); })
      .then(function () { setBusy(false); });
  }

  function startPolling() {
    pollUntil = Date.now() + POLL_FOR_MS;
    if (pollTimer) return;
    pollTimer = window.setInterval(function () {
      if (Date.now() > pollUntil) return stopPolling();
      if (busy || document.hidden) return;
      call("GET", "/v1/chat/poll").then(function (payload) {
        var count = (payload.actions || []).length;
        (payload.actions || []).forEach(render);
        if (count && !payload.poll) stopPolling();
      }).catch(function () { /* urmatoarea incercare */ });
    }, POLL_EVERY_MS);
  }

  function stopPolling() {
    if (pollTimer) window.clearInterval(pollTimer);
    pollTimer = null;
  }

  // ---------- actiuni ----------

  function sendText() {
    var text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    resize();
    addMessage("user", function (bubble) { bubble.textContent = text; });
    deliver("/v1/chat/message", jsonBody({ text: text, message_id: newId() }));
  }

  function sendFile(file) {
    if (!file || busy) return;
    if (file.size > MAX_MB * 1024 * 1024) { addNote(T.errFile, "error"); return; }
    addMessage("user", function (bubble) { bubble.textContent = T.fileSent + file.name; });
    var data = new FormData();
    data.append("file", file);
    data.append("message_id", newId());
    deliver("/v1/chat/upload", { body: data }, true);
  }

  function resize() {
    input.style.height = "auto";
    input.style.height = Math.min(input.scrollHeight, 120) + "px";
  }

  function open() {
    panel.hidden = false;
    root.classList.add("ecq-open");
    launcher.setAttribute("aria-expanded", "true");
    launcher.setAttribute("aria-label", T.close);
    if (!greeted) {
      greeted = true;
      addMessage("bot", function (bubble) { bubble.appendChild(el("p", { "class": "ecq-text", text: T.welcome })); });
      ensureSession().catch(function () { addNote(T.errStart, "error"); });
    }
    input.focus();
  }

  function close() {
    panel.hidden = true;
    root.classList.remove("ecq-open");
    launcher.setAttribute("aria-expanded", "false");
    launcher.setAttribute("aria-label", T.open);
    launcher.focus();
  }

  launcher.addEventListener("click", function () { if (panel.hidden) open(); else close(); });
  closeBtn.addEventListener("click", close);
  form.addEventListener("submit", function (event) { event.preventDefault(); sendText(); });
  input.addEventListener("input", resize);
  input.addEventListener("keydown", function (event) {
    if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); sendText(); }
  });
  fileInput.addEventListener("change", function () {
    sendFile(fileInput.files && fileInput.files[0]);
    fileInput.value = "";
  });
  panel.addEventListener("keydown", function (event) { if (event.key === "Escape") close(); });

  function mount() { document.body.appendChild(root); }
  if (document.body) mount(); else document.addEventListener("DOMContentLoaded", mount);

  window.EcQuoteChat = { open: open, close: close };
})();
