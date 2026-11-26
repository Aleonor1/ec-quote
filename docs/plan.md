# Ofertare asistată pe WhatsApp: planul revizuit

26 noiembrie 2026. Înlocuiește varianta de dimineață. Pornește de la „Plan implementare: Ofertare instant pe site și WhatsApp” și de la decizia ta de azi: fără robot autonom pe WhatsApp.

## Ce se schimbă

Înainte: un asistent răspundea singur pe WhatsApp, prin CRM și Meta Cloud API, cu două săptămâni de mod umbră.

Acum: o extensie de Chrome pe web.whatsapp.com, pentru tine și Roxana. Extensia citește conversația deschisă, cere serverului ec-quote o propunere și o arată lângă chat: răspunsul sugerat, prețul exact din calculator, treptele de cantitate, imaginea de ofertă și, la un click, linkul de plată Shopify. Omul apasă „Inserează”, citește, corectează dacă vrea și apasă Trimite. Nimic nu pleacă singur.

Ce rămâne neschimbat: orice cifră vine din calculatorul site-ului, niciodată din model. Fără termene sub regulile de producție. Despre materiale doar afirmațiile aprobate. Cererile în afara regulilor (produs care nu e în calculator, peste prag, reducere, reclamație, fișier nefolosibil) apar ca „de văzut de om”, cu motivul, fără preț propus.

## De ce e mai simplu și mai sigur

- Nu mai atingem Meta: fără Cloud API, fără șabloane plătite, fără fereastra de 24h, fără plafon lunar. Numărul rămâne exact cum îl folosiți azi.
- Nu mai depindem de CRM pentru mesaje. Legătura cu CRM-ul devine opțională și vine mai târziu, doar pentru lead-uri.
- Fiecare mesaj e citit de un om înainte să plece. Modul umbră nu mai e o etapă, e felul de lucru.
- Mai puțin de construit: dispar puntea CRM, descărcarea fișierelor din Meta, mesajele cu butoane, cardul de aprobare, trimiterea automată a urmăririlor.
- Mai puține chei: nu mai trebuie nimic din Meta și nimic din CRM la început.

## Riscul nou, spus direct

WhatsApp Web nu are o interfață oficială pentru așa ceva și își schimbă pagina fără anunț. Când se schimbă, extensia poate să nu mai citească conversația până o actualizăm. De aceea: tot ce citește din pagină stă într-un singur fișier ușor de reparat, extensia are un autotest și, când nu poate citi sigur, spune asta și nu propune nimic. Lucrați în continuare normal, fără sugestii, până la actualizare.

Extensia face doar trei lucruri în pagină: citește conversația deschisă, pune text în căsuța de mesaj și atașează imaginea de ofertă. Nu apasă Trimite, nu deschide alte conversații, nu trimite în masă. Orice automatizare peste atât e în afara proiectului, pentru că ar pune numărul în pericol față de regulile WhatsApp.

## Epicile

| Epic | Ce livrează | Unde |
| --- | --- | --- |
| E0 Fundația | Depozitul, serverul pornit pe o gazdă, cheile, acces la calculatorul real, auditul de preț pe 50 de configurații | ec-quote, story-1 la story-6 |
| E1 Ofertare asistată în extensie (doar text) | Extensia citește conversația și arată sugestia: întrebarea de pus sau oferta cu preț și trepte; linkul de plată la un click | ec-quote (server și `extension/`), story-7 la story-14 |
| E2 Fișier, mockup și imagine de ofertă | Extensia ia fișierul clientului din WhatsApp Web, serverul îl verifică, face mockup-ul și imaginea de ofertă, extensia o atașează la mesaj | ec-quote, story-15 la story-23; calculator-app pentru linia de tăiere (story-21) |
| E3 Măsurare și reglaj | Comenzi plătite legate de oferte, cifrele de folosire, raportul săptămânal cu auditul de 20 de oferte, remindere pentru voi la 24h și 72h | ec-quote, story-24 la story-27 |
| E4 Opțional | Lead-uri în CRM; chatul de pe site | ec-quote, CRM, calculator-app, story-28 la story-31 |

Urmăririle de la 24h și 72h devin remindere afișate vouă în extensie („oferta pentru X a rămas fără răspuns”). Voi decideți dacă scrieți.

Chatul de pe site este deja scris în server, dar nu l-ai confirmat după schimbarea de azi. L-am lăsat ultimul, ca decizie deschisă.

## Cum măsurăm acum

- Timpul de la mesajul clientului până la sugestie.
- Câte sugestii pleacă neschimbate, câte editate, câte ignorate.
- Conversia din ofertă în comandă.
- Zero greșeli de preț, verificat săptămânal pe 20 de oferte.
- Costul lunar al modelului.

## Ce am nevoie de la tine

Chei și acces (doar numele; valorile le pui tu pe server, nu în depozit și nu în chat):

1. `CALCULATOR_SYNC_SECRET`: aceeași valoare ca `QUOTE_SYNC_SECRET` din calculator.
2. `ANTHROPIC_API_KEY` și modelul ales (`EC_QUOTE_MODEL`).
3. `SHOPIFY_SHOP_DOMAIN` și `SHOPIFY_ADMIN_TOKEN`: o aplicație personalizată în Shopify cu `write_draft_orders`, plus citire la produse și comenzi.
4. O gazdă pentru server (un VPS) și un subdomeniu, de exemplu `oferta.etichetecreative.ro`.
5. Numele celor care folosesc extensia (acum: Aleonor, Roxana). Fiecare primește un token propriu, ca să știm cine a generat fiecare ofertă și să putem opri un singur token.
6. Textul termenului de producție, standard și urgent, exact cum vrei să apară în mesaje. Fără el, sugestiile nu spun niciun termen.

Decizii:

1. Pragul peste care oferta e „de văzut de om”. Acum: 3000 lei fără TVA.
2. Valabilitatea ofertei. Acum: 7 zile.
3. Produsele: doar etichetele și stickerele din calculator, restul „de văzut de om”?
4. Confirmă sau completează lista de afirmații despre materiale din `config/rules.json`.
5. Câte zile păstrăm pe server conversațiile și fișierele clienților.
6. Dacă un client întreabă „vorbesc cu un robot?”: propunerea e ca extensia să nu sugereze nimic și să răspundeți voi.
7. Instalarea extensiei: manual din dosar la început, apoi listare privată în Chrome Web Store (cere un cont de dezvoltator Google, taxă unică de 5 USD).
8. Refacerea geometriei din Contur Studio ca să putem calcula linia de tăiere pe server (story-21). Până atunci mockup-ul arată un contur orientativ.
9. Chatul de pe site: îl mai vrei? Dacă da, rămâne în E4.
10. Lead-urile în CRM: le vrei, și când?
11. 10 până la 15 fotografii proprii pentru mockup-uri, fără etichetă pe produs, plus logo și culori pentru imaginea de ofertă.

## Ordinea de lucru

E0, apoi E1. E2 poate începe în paralel cu partea de extensie din E1. E3 după ce există oferte reale. E4 doar dacă îl ceri. Fiecare epic se oprește la un pull request pe care îl îmbini tu.
