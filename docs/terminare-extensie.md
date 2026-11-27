# Terminarea extensiei: pași

Unde suntem: extensia din `extension/` este scrisă și trece testele automate (47), dar a rulat numai pe pagini de test care imită WhatsApp Web și numai cu un server simulat. Nu a fost încărcată niciodată pe WhatsApp Web real și nu a vorbit niciodată cu backendul real.

Pașii de mai jos sunt în ordinea în care se deblochează unul pe altul. La fiecare scrie cine îl face: **owner** (tu, în browser sau în conturi) sau **sesiune** (o sesiune Claude Code în acest depozit).

## 1. Backend pornit, ca extensia să aibă la ce se conecta

Extensia nu face nimic fără backend. Pentru prima probă ajunge unul local.

**Owner** pune valorile în `.env` (model: `.env.example`), fără să le scrie în chat sau în git:

| Variabilă | Ce este |
| --- | --- |
| `CALCULATOR_SYNC_SECRET` | valoarea `QUOTE_SYNC_SECRET` din Railway, serviciul `calculator-app` |
| `ANTHROPIC_API_KEY` | cheia API a modelului |
| `SHOPIFY_SHOP_DOMAIN`, `SHOPIFY_ADMIN_TOKEN` | token de aplicație custom cu `write_draft_orders`, `read_products`, `read_orders` |
| `EC_QUOTE_INBOUND_SECRET` | orice șir de minimum 24 de caractere (`openssl rand -hex 24`) |
| `EC_QUOTE_ASSIST_TOKENS` | `nume:token` pentru fiecare coleg, separate prin virgulă; token de minimum 24 de caractere |
| `EC_QUOTE_PUBLIC_BASE_URL` | adresa la care extensia vede backendul (local: `http://localhost:8080`) |

Pornire locală:

```bash
python3 -m pip install -e ".[dev]"
python3 -m uvicorn ec_quote.api.main:app --port 8080
curl -H "X-EcQuote-Assist-Token: <tokenul tău>" http://localhost:8080/v1/assist/ping
```

Răspunsul așteptat: `{"ok": true, "staff": "<numele>"}`.

De știut: nu există încă un motor demonstrativ pentru rutele extensiei (cel din `ec_quote/api/demo_engine.py` servește doar chatul de site). Fără cheile de mai sus, `ping` și `upload` merg, dar sugestia răspunde 503. Dacă vrei să probezi panoul înainte să ai cheile, cere unei sesiuni un motor demonstrativ pentru `/v1/assist/suggest`.

## 2. Încărcarea extensiei în Chrome (owner)

1. `chrome://extensions`, activezi „Developer mode”, „Load unpacked”, alegi folderul `extension/`.
2. În pagina de opțiuni: adresa serverului și tokenul personal, apoi „Testează conexiunea”. Chrome cere acordul pentru adresa serverului; îl accepți.
3. Deschizi `https://web.whatsapp.com` și o conversație individuală (nu grup).

## 3. Verificarea pe WhatsApp Web real

Acesta este pasul care nu s-a putut face automat. Selectorii din `extension/content/selectors.js` sunt scriși după structura cunoscută a paginii, nu verificați pe ea.

**Owner** verifică și notează ce nu merge:

- [ ] În subsolul panoului scrie „Compatibilitate WhatsApp Web: ok”. Dacă scrie „de verificat”, un clic pe text arată ce element lipsește.
- [ ] Numele conversației din panou este cel corect.
- [ ] Sugestia ține cont de mesaje: text, cine a scris (client sau voi), ordinea.
- [ ] Un răspuns citat (reply) apare ca atare, nu amestecat cu textul.
- [ ] O conversație de grup arată „Conversațiile de grup nu sunt asistate”.
- [ ] La schimbarea conversației, panoul se schimbă și el, fără să rămână sugestia veche.
- [ ] „Inserează în mesaj” pune textul în caseta WhatsApp, cu rândurile păstrate, și **nu** trimite.
- [ ] Panoul nu acoperă caseta de mesaj, la fereastră mare și la fereastră îngustă.
- [ ] Tema închisă a WhatsApp schimbă și panoul.
- [ ] „Trimite fișierul la verificare” merge pe o imagine primită. Dacă nu, tragerea fișierului descărcat în panou merge.
- [ ] „Copiază imaginea” și lipirea ei în conversație merg.
- [ ] „Generează link de plată” cere confirmare și întoarce un link care se deschide.

**Sesiune**, pentru ce a picat: are nevoie de structura reală a paginii. Cel mai simplu, în WhatsApp Web deschizi DevTools, alegi în Elements nodul `#main`, „Copy outerHTML”, și îl salvezi într-un fișier. Înainte de a-l da mai departe, șterge sau înlocuiește numele, numerele și textele reale ale clienților. Sesiunea actualizează harta `SELECTORS` din `content/selectors.js` și înlocuiește fixture-urile din `extension/tests/fixtures/` cu structura reală, ca testele să păzească de acum pagina adevărată.

## 4. Ce mai are de făcut codul extensiei

Toate sunt story-uri deja scrise în `specs/todo/`; se pot da unei sesiuni cu `/ship <story>` după instalarea pack-ului ai-skills.

| Ce | Story | De ce contează |
| --- | --- | --- |
| Selectori verificați pe pagina reală și fixture-uri reale | story-11 | fără asta citirea poate fi greșită fără să se vadă |
| Inserarea în caseta reală (editorul Lexical), cu cele două căi de rezervă | story-12 | e funcția principală |
| Testul intermitent din `tests/browser/` | story-12 | unul din 47 pică uneori; trebuie găsit și reparat, nu rerulat |
| Proba butonului „Testează conexiunea” cu promptul real de permisiune | story-13 | testele ocolesc promptul |
| Atașamentele clientului citite din pagina reală | story-19 | modul în care WhatsApp expune fișierele nu e documentat |
| Imaginea de ofertă: copiere și lipire pe pagina reală | story-20 | |
| Împachetare, versiune, cheia extensiei, actualizări | story-14 | altfel fiecare coleg încarcă folderul de mână |

Două lucruri care lipsesc din contract și trebuie hotărâte de sesiune împreună cu backendul:

- un marcaj pentru „mesajul are un atașament neîncărcat încă” (acum extensia trimite textul `[imagine]` sau `[document] nume`);
- un câmp pentru răspunsul citat (acum e pus în text ca `[Răspuns la: "..."]`).

## 5. Backend pe o adresă publică, cu HTTPS

Colegii nu pot folosi `localhost`. Fișierele sunt în `deploy/` (Docker, Caddy pentru certificat), cu pașii în `deploy/README.md`. Imaginea Docker nu a fost construită niciodată; prima construire e și prima probă.

- **Owner**: un server mic și un subdomeniu (de exemplu `oferta.etichetecreative.ro`) îndreptat spre el.
- **Sesiune**: construiește imaginea, repară ce pică, pornește serviciul, verifică `/health` și `ping`.
- În opțiunile extensiei se schimbă apoi adresa serverului pe cea publică.

## 6. Verificările pe real înainte de folosire

**Sesiune**, cu cheile puse:

```bash
python3 -m ec_quote.agent.eval --cases tests/agent/eval_cases.jsonl
```

Rulează cele 39 de conversații de probă pe modelul real. Fiecare caz care pică se repară înainte de folosire.

Apoi compararea prețurilor cu calculatorul din producție pe 50 de configurații (story-6). O singură diferență oprește lansarea.

**Owner**: o comandă de probă cap la cap. Generezi un link de plată, îl deschizi, verifici că suma e cea din ofertă (plus transportul ales la plată) și că în Shopify comanda are aceleași proprietăți ca una de pe site. Draftul de probă îl ștergi din Shopify.

## 7. Conținutul pe care doar owner-ul îl poate da

- Răspunsurile din `docs/intrebari-pentru-owner.md` (27 de întrebări, 15 contradicții între surse). Până atunci asistentul nu răspunde la acele întrebări; vă spune într-o notă internă că nu are un răspuns aprobat.
- Textul termenului de producție, standard și urgent. Fără el oferta scrie „termen standard de producție, confirmat la plasarea comenzii”.
- 10-15 fotografii reale pentru mockup; instrucțiunile sunt în `templates/mockups/README.md`. Până atunci șabloanele sunt desene provizorii.

## 8. Darea în folosință

1. O săptămână doar pe calculatorul tău, cu sugestii „la cerere”, nu automat.
2. Apoi al doilea coleg, cu tokenul lui.
3. Urmăriți câte sugestii se trimit neschimbate, câte modificate și câte ignorate (story-25). Sub jumătate folosite înseamnă că trebuie lucrat la conținut, nu la extensie.
4. Distribuirea printr-o listare privată în Chrome Web Store abia după ce selectorii sunt stabili (story-14).

## Ce nu se schimbă, orice ar fi

- Extensia nu apasă Trimite, nu deschide conversații și nu face nimic în masă.
- Niciun preț care nu vine din calculator.
- Niciun secret în git, în chat sau în capturi de ecran.
- Când WhatsApp își schimbă pagina și subsolul arată „de verificat”, folosiți „Copiază textul” până se actualizează selectorii.
