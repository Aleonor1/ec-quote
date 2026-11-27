# RUNBOOK: operare, incidente și verificări ec-quote

Ghid operațional pentru echipa tehnică și owner. Pentru regulile de arhitectură consultați `CLAUDE.md` și `docs/dev-rules.md`; pentru desfășurarea pe VPS consultați `deploy/README.md`.

## 1. Verificări rapide de sănătate

```bash
# Starea serverului
curl -fsS https://oferta.etichetecreative.ro/health

# Verificarea unui token de coleg și a versiunii minime de extensie
curl -fsS -H "X-EcQuote-Assist-Token: <token>" https://oferta.etichetecreative.ro/v1/assist/ping
```

Răspunsul la `/v1/assist/ping` conține `{"ok": true, "staff": "<nume>", "backend_version": "...", "min_extension_version": "..."}`.

## 2. WhatsApp s-a schimbat

WhatsApp Web își poate modifica structura DOM fără preaviz. Toți selectorii depind de un singur fișier: `extension/content/selectors.js`.

### Ce fac colegii imediat

1. În subsolul panoului apare **Compatibilitate WhatsApp Web: de verificat** (iar iconița extensiei arată `!`).
2. Colegul face clic pe textul din subsol, copiază lista elementelor raportate ca `negăsit` și o trimite dezvoltatorului.
3. Până la livrarea actualizării:
   - dacă doar inserarea automată a picat, colegul folosește butonul **Copiază textul** / **Copiază imaginea** și lipește manual cu `Ctrl+V`;
   - dacă citirea conversației a picat, colegul oprește asistentul din **Opțiuni** (**Asistent activ** debifat) și răspunde normal în WhatsApp Web.

### Ce face dezvoltatorul pentru reparație

1. În WhatsApp Web, pe o conversație de test, deschide DevTools -> fila **Elements**, selectează nodul `#main`, alege **Copy -> Copy outerHTML** și salvează fragmentul local.
2. **Anonimizează obligatoriu** înainte de orice commit: înlocuiește toate numele reale, numerele de telefon (`4070000xxxx`), identificatorii și textele clienților cu date fictive.
3. Actualizează fixture-ul din `extension/tests/fixtures/` și ajustează doar intrarea corespunzătoare din `SELECTORS` în `extension/content/selectors.js` (atribute ARIA și `data-*` înaintea claselor, niciodată clase generate prin hash, niciodată vreun selector pentru butonul Trimite).
4. Crește versiunea în `extension/package.json` și `extension/manifest.json`.
5. Rulează verificările și pachetul:
   ```bash
   cd extension
   npm test
   npm run build
   ```
6. **Calea rapidă (minute)**: trimite colegilor arhiva `extension/dist/ec-quote-extension-<versiune>.zip` pentru încărcare neîmpachetată (`Load unpacked`, conform `docs/extensie-instalare.md`, secțiunea 2), deoarece revizia din Chrome Web Store poate dura de la câteva ore la câteva zile.
7. **Calea permanentă**: încarcă același `.zip` în Chrome Web Store Developer Dashboard (`docs/extensie-publicare.md`) și, după aprobare, ridică `EC_QUOTE_MIN_EXTENSION_VERSION` pe server.

## 3. Auditul de paritate a prețurilor (50 de configurații)

Înainte de lansare și ori de câte ori se schimbă calculatorul sau clientul de prețuri:

```bash
# Reproducere locală pe fixture-urile înregistrate (fără rețea, parte din pytest)
python3 scripts/price_audit.py --replay tests/audit/fixtures/parity

# Verificare live pe calculatorul din producție (cere CALCULATOR_SYNC_SECRET în mediu, max 1 cerere/s)
python3 scripts/price_audit.py --live --out docs/audits
```

O singură diferență de preț oprește lansarea până la remedierea cauzei.

## 4. Revocarea unui token și ștergerea datelor unui client (GDPR)

- **Revocare acces coleg**: scoateți perechea `nume:token` din `EC_QUOTE_ASSIST_TOKENS` în `.env` pe server și reporniți serviciul (`cd deploy && docker compose restart app`). Efectul este imediat.
- **Retenție automată și ștergere la cerere**: funcțiile `store.purge(now, retention_days=..., data_dir=...)` și `store.purge_contact("whatsapp", "<cheie>", data_dir=...)` din `ec_quote/agent/store.py` șterg mesajele, datele de identificare și fișierele încărcate, păstrând doar totalurile anonimizate pentru statistici (`docs/privacy.md`).
