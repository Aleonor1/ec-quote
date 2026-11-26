# EC Quote Asistent WhatsApp (extensie Chrome)

Extensie Manifest V3 pentru echipa Etichete Creative. Pe WhatsApp Web citește conversația deschisă, cere serviciului `ec-quote` o sugestie de răspuns și o afișează într-un panou. Operatorul inserează textul în caseta de mesaj și apasă el însuși Trimite.

Extensia nu trimite mesaje, nu apasă butonul Trimite, nu deschide conversații și nu face nimic în masă. Nu are niciun selector pentru butonul Trimite și nu generează tasta Enter.

## Instalare

1. Deschideți `chrome://extensions` și activați „Developer mode” (modul pentru dezvoltatori).
2. Apăsați „Load unpacked” și alegeți folderul `ec-quote/extension`.
3. La prima instalare se deschide pagina de opțiuni. O puteți redeschide din iconița extensiei.

Nu există pas de build și nu există dependențe. Chrome 116 sau mai nou.

## Configurare

În pagina de opțiuni:

- **Adresa serverului**: adresa serviciului `ec-quote`, cu `https://` (pentru dezvoltare se acceptă și `http://localhost`). La salvare Chrome cere acordul pentru acces la această adresă; acceptați-l.
- **Token personal**: tokenul primit de fiecare operator. După salvare nu mai este afișat.
- **Testează conexiunea**: salvează și apelează `/v1/assist/ping`. La succes apare numele operatorului.
- **Asistent activ**: pornește sau oprește panoul din WhatsApp Web.
- **Sugestii**: automat (la fiecare mesaj nou al clientului) sau la cerere (butonul „Cere sugestie”).

## Utilizare

Panoul stă în dreapta paginii WhatsApp Web și poate fi restrâns; starea se păstrează.

- Eticheta arată tipul sugestiei: Răspuns, Întrebare pentru client, Ofertă, Necesită intervenție umană, Fără sugestie.
- „Notă internă (nu se trimite)” este doar pentru operator.
- Textul propus este editabil. „Inserează în mesaj” îl pune în caseta WhatsApp; dacă acolo există deja text, alegeți între înlocuire și adăugare. „Copiază textul” îl pune în clipboard.
- Oferta apare ca tabel (cantitate, preț/buc, fără TVA, cu TVA). Imaginea ofertei se poate copia (PNG) sau descărca, apoi o lipiți dvs. în conversație.
- „Generează link de plată” cere confirmare, fiindcă serverul creează o comandă nefinalizată (draft).
- „Fișier de la client”: „Trimite fișierul la verificare” citește imaginea deja încărcată în pagină. Pentru documente sau dacă citirea nu reușește, descărcați fișierul din WhatsApp și trageți-l în panou ori alegeți-l din calculator. Limita este 15 MB.
- Conversațiile de grup nu sunt asistate.

## De ce panou andocat și nu side panel-ul Chrome

Panoul este injectat în pagină, într-un shadow root, iar aplicația WhatsApp este îngustată ca panoul să nu acopere caseta de mesaj. Motive: este vizibil imediat lângă conversație, fără un clic în plus la fiecare fereastră; urmează tema deschisă sau închisă a WhatsApp; inserarea în caseta de mesaj se face din aceeași pagină, deci focusul ajunge sigur în editor; întreg fluxul se poate testa automat cu extensia reală. Dacă WhatsApp nu respectă lățimea rezervată, panoul se oprește deasupra casetei de mesaj. Side panel-ul ar fi fost complet izolat de pagină, dar trebuie deschis manual și nu poate fi testat cap la cap.

## Compatibilitate WhatsApp Web

WhatsApp își schimbă pagina fără anunț. Tot ce depinde de structura ei se află într-un singur fișier, `content/selectors.js`, cu harta de selectori la început.

În subsolul panoului apare „Compatibilitate WhatsApp Web: ok” sau „de verificat”. Un clic pe text arată ce element nu a fost găsit (panoul conversației, titlul, rândurile de mesaj, `data-id`, `data-pre-plain-text`, textul, caseta de mesaj). Când apare „de verificat”, se actualizează selectorii din acel fișier și se reîncarcă extensia.

## Confidențialitate și siguranță

- Se citește doar conversația deschisă de operator. Conținutul ei (cel mult ultimele 40 de mesaje vizibile) pleacă doar către adresa configurată, prin service worker.
- Extensia păstrează doar setările (`chrome.storage.local`) și ultimul identificator de sugestie pe conversație (`chrome.storage.session`, șters la închiderea browserului). Mesajele există doar în memorie, pentru conversația deschisă.
- Tokenul stă doar în service worker și în pagina de opțiuni. Scripturile din pagina WhatsApp nu au acces la el (`TRUSTED_CONTEXTS`), nu apare în DOM și nu apare în loguri.
- Textul primit de la server este tratat ca date: se afișează numai cu `textContent`, iar linkurile sunt acceptate doar cu `https`.
- Sumele vin ca text de la server și sunt afișate ca atare; extensia nu face calcule cu ele.
- Permisiuni: `storage`, `clipboardWrite`, acces la `web.whatsapp.com` și, la cerere, la adresa serverului. Fără cod încărcat de la distanță, fără analytics.

## Limite și riscuri

- Fixture-urile HTML din `tests/fixtures` sunt o aproximare scrisă de mână a structurii WhatsApp Web; nu au fost verificate pe pagina reală, fiindcă testele nu se pot autentifica în WhatsApp. Înainte de folosire, verificați o dată pe pagina reală: starea „ok” din subsol, citirea mesajelor (text, direcție, oră), inserarea textului, faptul că panoul nu acoperă caseta de mesaj și citirea unei imagini primite.
- O schimbare a paginii WhatsApp poate opri citirea sau inserarea până la actualizarea selectorilor. În acest caz folosiți „Copiază textul”.
- Se citesc doar mesajele încărcate în pagină. Ora lipsește la mesajele fără `data-pre-plain-text` (de exemplu imagini). Data se interpretează zi.lună.an.
- Când numărul de telefon nu este vizibil (contacte cu identificator `@lid`), cheia conversației este identificatorul intern, iar telefonul rămâne gol.
- Documentele pot fi citite automat doar dacă WhatsApp le-a încărcat deja; altfel se folosește calea manuală.
- Imaginea ofertei trebuie servită de pe adresa serverului configurat; de pe alt domeniu nu poate fi încărcată.
- Folosirea unor unelte neoficiale pe WhatsApp Web se face pe riscul titularului contului, chiar dacă fiecare mesaj este trimis de un om. WhatsApp poate restricționa conturile pe care detectează automatizări.

## Structură

```
manifest.json
background/   service-worker.js, api-client.js (client HTTP), coordinator.js (o cerere pe conversație)
content/      selectors.js (harta de selectori și cititorul), composer.js, media.js, main.js
panel/        panel.js, panel-style.js
options/      pagina de opțiuni
icons/        iconițe PNG
tools/        make-assets.mjs (regenerează iconițele și imaginea de test)
tests/        unit/ (node --test), browser/ (Playwright), fixtures/, helpers/
screenshots/  capturi generate de teste
```

Scripturile de conținut sunt fișiere clasice cu un spațiu de nume comun (`EcQuote`), ca să nu fie nevoie de `web_accessible_resources`. Service worker-ul și pagina de opțiuni sunt module ES.

## Teste

```bash
cd ec-quote/extension
npm test            # toate
npm run test:unit   # client API, coordonator, funcții pure ale cititorului
npm run test:browser  # cititorul pe fixture-uri și fluxul complet cu extensia reală
```

Testele folosesc `node --test` și Playwright cu Chromium, deja instalate pe mașina de dezvoltare; nu se instalează nimic în acest folder. Testele de browser încarcă extensia reală în Chromium headless, servesc fixture-urile ca `https://web.whatsapp.com` și pornesc un server local care imită `ec-quote`. Nimic nu ajunge la WhatsApp-ul real.
