# EC Quote Asistent WhatsApp (extensie Chrome)

Extensie Manifest V3 pentru echipa Etichete Creative. Pe WhatsApp Web citește conversația deschisă, cere serviciului `ec-quote` o sugestie de răspuns și o afișează într-un panou. Operatorul inserează textul sau atașează imaginea de ofertă în caseta de mesaj și apasă el însuși Trimite.

Extensia nu trimite mesaje, nu apasă butonul Trimite, nu deschide conversații și nu face nimic în masă. Nu are niciun selector pentru butonul Trimite și nu generează tasta Enter.

## Instalare și împachetare

1. Deschideți `chrome://extensions` și activați „Developer mode” (modul pentru dezvoltatori).
2. Apăsați „Load unpacked” și alegeți folderul `ec-quote/extension` (sau `ec-quote/extension/dist` după rularea `npm run build`).
3. La prima instalare se deschide pagina de opțiuni. O puteți redeschide din iconița extensiei.

Datorită cheii publice fixe din `manifest.json`, extensia are mereu același identificator stabil: `pihdgadpmjibpcbacfflgkipidjedkej` (`chrome-extension://pihdgadpmjibpcbacfflgkipidjedkej`).

Pentru a genera folderul curat `dist/` și arhiva `.zip` reproductibilă pentru Chrome Web Store:

```bash
cd extension
npm run build
```

Arhiva rezultată este `extension/dist/ec-quote-extension-<versiune>.zip`. Pașii detaliați sunt în `docs/extensie-instalare.md` și `docs/extensie-publicare.md`.

## Configurare

În pagina de opțiuni:

- **Adresa serverului**: adresa serviciului `ec-quote`, cu `https://` (pentru dezvoltare locală se acceptă `http://localhost` sau `http://127.0.0.1`). La salvare Chrome cere acordul pentru acces la această adresă; acceptați-l.
- **Token personal**: tokenul primit de fiecare operator. După salvare nu mai este afișat.
- **Testează conexiunea**: salvează, cere permisiunea pentru adresa serverului și apelează `/v1/assist/ping`. La succes apare numele operatorului; dacă versiunea extensiei este sub minimul cerut de server, apare mesajul de actualizare.
- **Asistent activ**: pornește sau oprește panoul din WhatsApp Web (iconița din bară afișează `OPR` când este oprit).
- **Sugestii**: automat (la fiecare mesaj nou al clientului) sau la cerere (butonul „Cere sugestie”).

## Utilizare

Panoul stă în dreapta paginii WhatsApp Web și poate fi restrâns; starea se păstrează.

- Eticheta arată tipul sugestiei: Răspuns, Întrebare pentru client, Ofertă, Necesită intervenție umană, Fără sugestie.
- „Notă internă (nu se trimite)” este doar pentru operator.
- Textul propus este editabil. „Inserează în mesaj” îl pune în caseta WhatsApp (prin eveniment de lipire sau `beforeinput` Lexical, ori `execCommand` ca rezervă); dacă acolo există deja text, alegeți între înlocuire și adăugare. „Copiază textul” îl pune în clipboard.
- Oferta apare ca tabel (cantitate, preț/buc, fără TVA, cu TVA). Pentru imaginea ofertei aveți trei acțiuni: „Atașează imaginea” (deschide previzualizarea media din WhatsApp cu fișierul neutru `oferta.png` și pune textul ofertei în descriere, fără a trimite), „Copiază imaginea” (PNG în clipboard) și „Descarcă”.
- „Generează link de plată” cere confirmare, fiindcă serverul creează o comandă nefinalizată (draft).
- „Fișier de la client”: „Trimite fișierul la verificare” citește imaginea deja încărcată în pagină. Pentru documente sau dacă citirea nu reușește, descărcați fișierul din WhatsApp și trageți-l în panou ori alegeți-l din calculator. Limita este 15 MB.
- Răspunsurile citate și atașamentele neîncărcate încă sunt trimise către server în câmpuri dedicate (`quoted_text`, `unuploaded_attachments`), fără a amesteca marcaje în textul mesajului.
- Conversațiile de grup nu sunt asistate.

## Compatibilitate WhatsApp Web și refacerea fixture-urilor

WhatsApp își schimbă pagina fără anunț. Tot ce depinde de structura ei se află într-un singur fișier, `content/selectors.js`, cu harta `SELECTORS` la început.

În subsolul panoului apare „Compatibilitate WhatsApp Web: ok” sau „de verificat” (iar iconița din bară arată `!`). Un clic pe text arată ce element nu a fost găsit. Când pagina reală s-a schimbat, urmați procedura din `RUNBOOK.md` (secțiunea „WhatsApp s-a schimbat”): salvați `#main` anonimizat în `tests/fixtures/`, actualizați `SELECTORS`, rulați `npm test` și `npm run build`.

## Teste

```bash
cd extension
npm test              # unit + browser
npm run test:unit     # client API, coordonator, cititor pur, build reproductibil, securitate manifest
npm run test:browser  # cititorul pe fixture-uri și fluxul complet cu extensia reală în Chromium
npm run build         # generează dist/ și dist/ec-quote-extension-<versiune>.zip
```
