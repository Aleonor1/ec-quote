# Confidențialitate, date transmise și administrarea accesului

Acest document descrie ce date citește extensia Chrome pentru ofertare asistată pe WhatsApp Web, unde ajung acestea, cât timp sunt păstrate și cum se revocă accesul sau se șterg datele unui client.

## Ce citește extensia

Extensia citește exclusiv conversația individuală deschisă în fila activă de WhatsApp Web, numai cât timp panoul asistentului este pornit de un coleg. Conversațiile de grup sunt ignorate. Extensia nu apasă niciodată Trimite: un om verifică textul și îl expediază personal.

## Ce trimite și unde

Datele pleacă numai către serverul configurat al Etichete Creative, prin `HTTPS` (`http` simplu este acceptat doar pe `localhost` pentru dezvoltare). O cerere către `/v1/assist/suggest` conține exclusiv:
- datele conversației deschise: cheia contactului (`key`, numărul sau identificatorul conversației), numele afișat (`name`) și, dacă este vizibil, numărul de telefon (`phone`);
- pentru fiecare mesaj vizibil din conversație: identificatorul (`id`), direcția (`direction`), textul (`text`), momentul trimiterii (`sent_at`), textul mesajului citat la răspuns (`quoted_text`) și descriptorii atașamentelor încărcate ori neîncărcate (`attachments`, `unuploaded_attachments`);
- antetele tehnice: tokenul personal în `X-EcQuote-Assist-Token` și versiunea extensiei în `X-EcQuote-Extension-Version`.

Un fișier din conversație este transmis la `/v1/assist/upload` numai atunci când colegul apasă explicit butonul de verificare tehnică sau trage fișierul în panou.

## Ce păstrează extensia și backendul

- **În extensie:** nu se salvează niciun text de mesaj, nume, număr sau fișier în `chrome.storage`, `localStorage`, `IndexedDB` ori cache. În `chrome.storage.local` se salvează doar adresa serverului, tokenul personal revocabil și comutatorul pornit/oprit (`chrome.storage.local` nu este criptat pe disc; `chrome.storage.sync` nu este folosit, astfel că tokenul nu este sincronizat pe alte dispozitive). Datele din memorie sunt eliberate la schimbarea conversației, la oprirea panoului și la închiderea filei.
- **Pe serverul Etichete Creative:** mesajele, starea conversației, sugestiile și fișierele încărcate sunt stocate în directorul `EC_QUOTE_DATA_DIR` pe durata stabilită de `retention_days` în `config/rules.json` (90 de zile). După acest termen, funcția `purge(now)` șterge textele mesajelor, întrebările înregistrate, numele, numerele de telefon și fișierele încărcate, păstrând doar sumele și stările ofertelor pentru statistici, cu cheia contactului înlocuită de amprenta ei `SHA-256`. Dacă `retention_days` este `DECIZIE_DESCHISA`, ștergerea automată este oprită și semnalează explicit acest lucru. Jurnalele de sistem nu conțin texte de mesaje, nume, numere sau tokenuri.

## Trimiterea către furnizorul modelului

Pentru înțelegerea cererii și pregătirea sugestiei, textul mesajelor din conversația curentă și extrasul din catalogul de produse sunt trimise către furnizorul modelului (`Anthropic`, prin API comercial în calitate de persoană împuternicită, fără utilizarea datelor pentru antrenarea modelelor). Numărul de telefon, adresa de e-mail și linkurile de plată nu sunt incluse în prompturi.

## Ce nu se colectează niciodată

Nu se citesc și nu se transmit niciodată: alte conversații din WhatsApp Web, lista de conversații, conversațiile de grup sau membrii lor, fotografiile de profil, fișierele neverificate de coleg, istoricul de navigare, cookie-urile sau identificatori ai browserului ori ai calculatorului în afara versiunii extensiei.

## Revocarea unui token și ștergerea datelor la cerere

- **Revocarea accesului unui coleg:** proprietarul elimină sau înlocuiește intrarea `nume:token` din variabila `EC_QUOTE_ASSIST_TOKENS` pe server și repornește serviciul; accesul vechiului token încetează imediat, fără a afecta ceilalți colegi. Din pagina de opțiuni a extensiei, deconectarea șterge tokenul și adresa salvate local.
- **Ștergerea datelor unui client la cerere:** proprietarul rulează `SqliteStore(data_dir / "conversations.sqlite3").purge_contact("whatsapp", "<key>", data_dir=data_dir)` pe server (care șterge imediat mesajele, numele, telefonul și fișierele clientului și anonimizează cheia) și șterge eventualele comenzi nefinalizate (Draft Orders) din Shopify.
