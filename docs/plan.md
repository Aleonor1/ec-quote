# Ofertare instant: planul revizuit după ce am citit codul

26 noiembrie 2026. Pornește de la „Plan implementare: Ofertare instant pe site și WhatsApp”. Ținta rămâne aceeași: preț, mockup și link de plată în sub 5 minute, 24/7, pe WhatsApp și în chatul de pe site, cu un singur motor. Modelul doar înțelege și întreabă; orice cifră vine din unelte.

## Ce s-a schimbat față de planul inițial

| Planul presupunea | Ce există deja | Urmarea |
| --- | --- | --- |
| Construim o unealtă de preț | Calculatorul dă prețul exact de pe site, de la server la server: `POST /api/sync/line` și `GET /api/sync/calculator-config` | Iese din E0. ec-quote doar îl cheamă. Rămâne un audit pe 50 de configurații. |
| Construim verificarea fișierelor de la zero | Pentru PDF și AI există inspecția din calculator (`POST /api/sync/artwork-inspect`) și încărcarea în stocare (`POST /api/sync/upload-url`) | Pentru PDF refolosim. Pentru PNG și JPG verificarea se face în ec-quote (rezoluție la mărimea finală). |
| ec-quote primește webhook-ul WhatsApp și ține numărul | CRM-ul are deja webhook-ul Meta, Coexistence cu aplicația de pe telefon, inboxul, șabloanele cu plafon lunar, drafturile AI și trimiterea automată cu fereastra de 24h și buton de oprire | Iese din E0 tot ce ține de Meta. ec-quote nu deține numărul. CRM-ul îi trimite mesajele și livrează răspunsurile. |
| Aprobarea din modul umbră se construiește separat | CRM-ul are drafturi cu aprobă, editează, respinge | Aprobarea cu un click se face în inboxul CRM. |
| Linia de tăiere se face pe server | Contur Studio calculează conturul numai în browser. Serverul face doar PDF-ul de producție dintr-un proof deja aprobat | Se adaugă o poveste în calculator (contur fără browser). Până atunci mockup-ul folosește un contur de previzualizare, nu de producție. Fără eliminare de fundal pe server: o poză cu fundal plin primește formă simplă sau merge la om. |
| Chatul de pe site cheamă direct ec-quote | Un secret nu poate sta în browser | Chatul trece prin App Proxy-ul calculatorului (o rută nouă și un bloc de temă). |

Ce se adaugă în CRM (E3): puntea către ec-quote (trimite mesajul, livrează răspunsul), descărcarea fișierelor primite pe WhatsApp (azi CRM-ul păstrează doar identificatorul), mesaje cu butoane (azi există doar text, imagine și șablon), aprobarea ofertei în inbox, șablonul pentru urmărirea de la 72h.

## Epicile revizuite

| Epic | Ce livrează | ec-quote | calculator-app | CRM |
| --- | --- | --- | --- | --- |
| E0 Fundația | Motorul pornește cap la cap cu toate modulele legate, reguli validate, stare care rezistă la repornire, securitate, instalare pe VPS | story-1 la story-5 | | |
| E1 Preț și ofertă (întâi în chatul de pe site) | Preț exact, trepte de cantitate, oferta ca text și imagine, link de plată, predare la om, lead în CRM, urmărirea comenzilor plătite, urmărire la 24h și 72h, cifre și auditul săptămânal de 20 de oferte | story-6 la story-11, story-14 la story-17 | story-12 (ruta de proxy), story-13 (blocul de chat din temă) | contractul punții (lead și predare) |
| E2 Fișier și mockup | Verificarea fișierului, stocarea lui, șabloane foto reale, linie de tăiere, drumul complet cu fișier | story-18 la story-20, story-22, story-23 | story-21 (contur fără browser) | |
| E3 Mod umbră pe WhatsApp | Mesajele WhatsApp ajung la motor, omul aprobă fiecare ofertă cu un click, 2 săptămâni | adaptări mici | | puntea, fișierele, butoanele, aprobarea, șablonul de 72h |
| E4 Live | Trecerea pe autonom la 95% oferte aprobate neschimbate, monitorizare, oprire de urgență | comutatorul și alertele | chatul devine public | comutatorul și raportul |
| E5 Optimizare continuă | Auditul săptămânal, ajustarea întrebărilor, mockup premium la cerere | după E4 | | |

Higgsfield rămâne doar pentru mockup premium la cerere, cu om în buclă. Nu intră în drumul automat.

## Ce am nevoie de la tine

Decizii:

1. Pragul de valoare peste care oferta merge la om. Acum: 3000 lei fără TVA.
2. Valabilitatea ofertei (acum 7 zile) și dacă urmărirea de la 72h vine cu un stimulent. Dacă da, care, și el trebuie să existe în Shopify, altfel nu îl spunem.
3. Produsele de la lansare. Propunere: doar etichetele și stickerele din calculator. Bannerele, mesh-ul și pachetele fixe merg la om.
4. Găzduirea: care VPS, ce domeniu (de exemplu `quote.etichetecreative.ro`).
5. Tonul și dacă asistentul se prezintă de la primul mesaj ca fiind automat. Oricum recunoaște când e întrebat.
6. Termenele de producție pe care are voie să le spună (standard și urgent). Lipsesc din `config/rules.json`; fără ele nu spune niciun termen.
7. Lista de afirmații despre materiale. Acum sunt trei în `config/rules.json`; completeaz-o sau confirm-o.
8. Câte zile păstrăm conversațiile și fișierele clienților.
9. Chatul de pe site, în perioada de test: vizibil doar cu un link special, sau public din prima zi cu aprobare la fiecare ofertă.

Chei și acces (doar numele; valorile le pui tu în `.env` pe VPS, nu în depozit și nu în chat):

- `CALCULATOR_SYNC_SECRET`: aceeași valoare ca `QUOTE_SYNC_SECRET` din calculator.
- `ANTHROPIC_API_KEY` și `EC_QUOTE_MODEL`.
- `SHOPIFY_SHOP_DOMAIN` și `SHOPIFY_ADMIN_TOKEN`: o aplicație personalizată în Shopify cu drept de scriere la comenzi ciornă și de citire la produse și comenzi.
- `CRM_BASE_URL` și `CRM_API_SECRET`.
- `EC_QUOTE_INBOUND_SECRET`: îl generezi tu; aceeași valoare se pune în CRM și în calculator.
- Acces SSH la VPS și un subdomeniu cu certificat.
- 10 până la 15 fotografii proprii pentru șabloanele de mockup (borcan, sticlă, pahar, cutie, pungă, laptop și ce mai vinzi des), fără etichetă pe ele.
- În Meta: aprobarea șablonului pentru mesajul de la 72h (îl propunem în E3).

## Cum măsurăm

Primul răspuns sub 1 minut. Oferta completă sub 5 minute. Conversia din ofertă în comandă: întâi măsurăm punctul de plecare, apoi ținta e +50%. Sub 30% din conversații predate unui om. Zero greșeli de preț, verificat săptămânal pe 20 de oferte. Cost sub aproximativ 100 EUR pe lună la 300 de cereri.

## Ordinea de lucru

E0, apoi E1 și E2 în paralel pe chatul de pe site, apoi E3 (două săptămâni de mod umbră pe WhatsApp), apoi E4. Fiecare epic se oprește la un pull request pe care îl îmbini tu.
