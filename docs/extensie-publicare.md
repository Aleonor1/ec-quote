# Publicarea și administrarea extensiei în Chrome Web Store (pentru owner)

Extensia `EC Quote Asistent WhatsApp` este distribuită intern echipei Etichete Creative printr-o listare privată (sau nelistată, restricționată la conturi Google nominalizate) în Chrome Web Store.

## 1. Identificatorul fix al extensiei și cheia publică

`extension/manifest.json` conține cheia publică RSA (`key`), astfel încât extensia primește același identificator atât la încărcarea neîmpachetată (`Load unpacked`), cât și din pachet:

- **ID extensie**: `pihdgadpmjibpcbacfflgkipidjedkej`
- **Origine Chrome**: `chrome-extension://pihdgadpmjibpcbacfflgkipidjedkej`

Setați pe server în `.env`:

```bash
EC_QUOTE_EXTENSION_ORIGINS=chrome-extension://pihdgadpmjibpcbacfflgkipidjedkej
EC_QUOTE_MIN_EXTENSION_VERSION=0.1.0
```

Notă: la prima încărcare a arhivei `.zip` în Chrome Web Store Developer Dashboard, dacă magazinul atribuie un ID propriu listării noi, copiați noul ID din panoul Chrome Web Store și adăugați și acea origine `chrome-extension://<id-store>` în `EC_QUOTE_EXTENSION_ORIGINS` (separate prin virgulă). Nu comiteți niciodată vreo cheie privată `.pem` în depozit.

## 2. Construirea pachetului reproductibil

Din rădăcina depozitului:

```bash
cd extension
npm test
npm run build
```

Rezultatul este `extension/dist/ec-quote-extension-<versiune>.zip` (fără teste, fixture-uri sau unelte de dezvoltare). La fiecare versiune nouă creșteți câmpul `version` în ambele fișiere: `extension/package.json` și `extension/manifest.json`.

## 3. Crearea contului și încărcarea ca listare privată

1. Deschideți [Chrome Web Store Developer Dashboard](https://chrome.google.com/webstore/devconsole) și înregistrați contul de dezvoltator (taxă unică de înregistrare de 5 USD).
2. În fila **Account**, adăugați în secțiunea **Trusted Testers** (sau în grupul Google Workspace al firmei) adresele de Google ale colegilor care au voie să instaleze extensia.
3. Apăsați **New Item** și încărcați fișierul `extension/dist/ec-quote-extension-0.1.0.zip`.
4. În fila **Distribution / Visibility**:
   - alegeți **Private** (vizibilă exclusiv conturilor Google listate în Trusted Testers sau pe domeniul firmei; nu apare în căutările publice și nu poate fi instalată de altcineva cu linkul).

## 4. Textele pentru formularul Chrome Web Store (Privacy practices & Listing)

### Descriere scurtă (Română)
Sugestii interne de răspuns și oferte pentru operatorii Etichete Creative în WhatsApp Web. Fiecare mesaj este revizuit și trimis manual de operator.

### Single Purpose Statement (English, pentru recenzorul Chrome Web Store)
Assists Etichete Creative customer-support staff on WhatsApp Web by reading the currently open individual customer chat and displaying suggested replies and price quotes from the company's internal backend so the human operator can review, edit, and manually send them. The extension never sends messages automatically and never interacts with other chats.

### Permission Justifications (English)

- **`host_permissions` (`https://web.whatsapp.com/*`)**: Required to inject the staff side panel next to WhatsApp Web, read the visible messages of the single conversation opened by the operator, and insert the operator-approved reply text or offer image preview into the message composer when the operator clicks Insert or Attach. The extension never clicks Send and never navigates between chats.
- **`optional_host_permissions` (`https://*/*`, `http://localhost/*`, `http://127.0.0.1/*`)**: Requested at runtime in the Options page only for the specific company backend URL configured by the staff member, allowing the background service worker to request reply suggestions and fetch offer images over HTTPS.
- **`storage`**: Stores only the staff member's configured backend URL, personal authentication token, panel collapsed state, and auto/manual mode in `chrome.storage.local`, plus the last suggestion ID per chat in `chrome.storage.session`. No customer messages or personal data are stored.
- **`clipboardWrite`**: Used only when the operator clicks "Copiază textul", "Copiază linkul", or "Copiază imaginea" in the panel to copy the suggested offer text or PNG offer card to the clipboard.

### Data Usage Disclosures (aliniate cu `docs/privacy.md`)

- Colectează date de comunicare (mesajele conversației deschise, numele afișat și numărul de telefon al interlocutorului) exclusiv pentru funcționalitatea aplicației interne a operatorului Etichete Creative.
- Nu vinde date către terți, nu folosește date pentru publicitate sau profilare și nu încarcă cod de la distanță.

## 5. Publicarea unei actualizări

1. Creșteți versiunea (`major.minor.patch`) în `extension/package.json` și `extension/manifest.json`.
2. Rulați `cd extension && npm test && npm run build`.
3. În Chrome Web Store Developer Dashboard -> produsul existent -> **Package** -> **Upload new package**, încărcați noul `.zip` și apăsați **Submit for review**.
4. Dacă versiunea veche nu mai trebuie folosită, după publicarea noii versiuni actualizați pe server `EC_QUOTE_MIN_EXTENSION_VERSION=<noua-versiune>` și reporniți containerul `app`: extensiile neactualizate vor afișa imediat „Actualizați extensia”.
