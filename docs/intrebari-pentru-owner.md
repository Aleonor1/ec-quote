# Întrebări pentru owner

Fișier generat cu `python3 -m ec_quote.knowledge.export_questions`. Nu se editează de mână:
răspunsurile se trec în `knowledge/<subiect>.json`, la intrarea cu id-ul din paranteză.

Stare la 2026-11-26: 61 răspunsuri verificate, 27 întrebări deschise, 15 contradicții între surse.

Până primesc răspuns, asistentul nu spune nimic clienților despre aceste subiecte:
sugestia apare ca „de văzut de om”.

## Întrebări deschise

### Comandă și cantități

1. Acceptăm comenzi sub cantitatea minimă din calculator (de exemplu 10 sau 20 de bucăți)? Dacă da, în ce condiții? (nu / da, la prețul minimului) (`cantitate-sub-minim`)
   - Clientul întreabă: „Se poate comanda sub cantitatea minimă?”
   - Ce am găsit: Calculatorul refuză cantitățile sub minim; nicio sursă nu spune dacă facem excepții.

### Fișiere și grafică

2. Cât costă grafica făcută de noi la stickere și etichete (opțiunea „Nu am grafică, o faceți voi”) și câte runde de modificări include? (ex.: gratuit, 2 runde) (`cost-grafica`)
   - Clientul întreabă: „Cât costă grafica făcută de voi la stickere și etichete?”
   - Ce am găsit: Site-ul publică prețuri pentru grafică doar la cărți de vizită și flyere (25 și 70 lei) și grafică gratuită la bannere; la stickere și etichete nu apare niciun cost.
3. Putem reproduce o culoare Pantone exactă sau trimite o probă de culoare înainte de tiraj? (nu / da, în ce condiții) (`culoare-exacta`)
   - Clientul întreabă: „Puteți garanta o culoare exactă (Pantone)?”
   - Ce am găsit: Politicile spun doar că diferențele de culoare față de ecran nu pot fi reclamate.

### Livrare

4. Livrăm în afara României? Dacă da, în ce țări, cu ce cost și cum se comandă, având în vedere că la checkout există doar România? (nu / da, cu ofertă separată) (`livrare-strainatate`)
   - Clientul întreabă: „Livrați în afara României?”
   - Ce am găsit: Pagina „Despre noi” spune „Livrăm în toată Europa”, dar în Shopify singura zonă de livrare este România.
5. Poate clientul să ridice personal comanda din Cluj-Napoca? Dacă da, de la ce adresă și în ce program? (nu / da, adresa și orele) (`ridicare-personala`)
   - Clientul întreabă: „Pot ridica personal comanda?”
   - Ce am găsit: În Shopify nu este configurată ridicarea locală; pagina de contact arată la locație doar „România”. Există două adrese în surse (vezi contradicția adresa).
6. Putem livra la locker (easybox, Packeta) sau la punct de ridicare, și poate clientul să aleagă curierul? (ex.: doar la adresă, cu GLS) (`livrare-locker`)
   - Clientul întreabă: „Livrați la easybox sau la un punct de ridicare?”
   - Ce am găsit: Politica de confidențialitate pomenește „punct de ridicare sau locker ales”, dar la checkout există o singură metodă, „Transport”.
7. Cum explicăm clientului regula din Termeni, punctul 5, despre kilometrii suplimentari (taxa se achită la curier, iar cea plătită cu cardul se returnează)? (o propoziție) (`livrare-km-suplimentari`)
   - Clientul întreabă: „Se plătește ceva în plus pentru localitățile îndepărtate?”
   - Ce am găsit: Termenii și condițiile, secțiunea 5, au o formulare greu de transmis ca atare clientului.

### Materiale, finisaje și adeziv

8. Putem face stickere și etichete cu finisaj lucios (lac lucios) la cerere, sau doar mat? (doar mat / și lucios, la cerere) (`finisaj-lucios`)
   - Clientul întreabă: „Se pot face și cu finisaj lucios?”
   - Ce am găsit: rules.json aprobă doar „lac UV mat”; site-ul pomenește „strat de lac pentru strălucire” la Gold, Chrome și Holografic.
9. Pe ce suprafețe ține bine adezivul Standard și când recomandăm Foarte puternic (plastic, sticlă, carton, textile, suprafețe texturate sau prăfuite)? (o propoziție pentru fiecare adeziv) (`adeziv-suprafete`)
   - Clientul întreabă: „Pe ce suprafețe se lipesc?”
   - Ce am găsit: Site-ul listează utilizări (sticlă, ambalaje, laptopuri), dar nu spune ce adeziv se potrivește pe fiecare suprafață.
10. Se pot dezlipi stickerele fără să lase urme de adeziv? Avem adeziv removabil? (da / nu / doar la cerere) (`adeziv-removabil`)
   - Clientul întreabă: „Se dezlipesc fără să lase urme?”
   - Ce am găsit: Calculatorul oferă doar Standard și Foarte puternic; nicio sursă nu vorbește despre dezlipire fără urme.
11. Facem etichete pe hârtie (albă sau kraft), sau doar pe folie și vinil? (doar folie și vinil / și hârtie) (`material-hartie`)
   - Clientul întreabă: „Faceți etichete pe hârtie sau kraft?”
   - Ce am găsit: Toate materialele de pe site sunt folie sau vinil; owner-ul a exclus din reclame etichetele de carton (2026-11-17), dar nu scrie dacă le producem.
12. La etichetele pe rolă: ce diametru are miezul, câte etichete intră pe o rolă și se pot aplica cu mașina de etichetat? (ex.: miez 76 mm, doar aplicare manuală) (`role-detalii`)
   - Clientul întreabă: „Ce specificații au rolele?”
   - Ce am găsit: Site-ul spune doar „pe planșe sau role, lățime 40-50 cm”.
13. Facem etichete pentru haine, print DTF sau tricouri personalizate? (da / nu) (`textile-dtf`)
   - Clientul întreabă: „Faceți etichete pentru haine sau print DTF?”
   - Ce am găsit: Există o colecție „Tricouri Personalizate” fără produse; owner-ul a exclus DTF și etichetele pentru haine din reclamele Google (2026-11-17).

### Mostre

14. Trimitem mostre gratuite? Ce conține setul, cine plătește transportul și cum le cere clientul? (ex.: da, set cu 5 materiale, gratuit, cu transport inclus) (`mostre-gratuite`)
   - Clientul întreabă: „Trimiteți mostre?”
   - Ce am găsit: În Shopify există produse nelistate „Mostre ...” și un profil de livrare „Mostre (livrare gratuită)”; owner-ul a lansat pe 2026-11-17 o ofertă de mostre gratuite tratată manual pe WhatsApp. Condițiile nu sunt scrise nicăieri.
15. Facem o mostră tipărită cu designul clientului înainte de comanda mare? Dacă da, cât costă și în cât timp? (nu / da, condițiile) (`mostra-cu-designul-meu`)
   - Clientul întreabă: „Pot primi o mostră tipărită cu designul meu?”
   - Ce am găsit: Site-ul oferă doar simulare grafică gratuită, nu o mostră fizică tipărită cu designul clientului.

### Plată și facturare

16. Acceptăm plata ramburs, la curier? (da / nu) (`plata-ramburs`)
   - Clientul întreabă: „Se poate plăti ramburs, la livrare?”
   - Ce am găsit: La ultimele 100 de comenzi apar doar card, OP pe bază de proformă și credit magazin; nicio sursă nu spune dacă rambursul este acceptat sau refuzat.
17. Ce date cerem pentru factura pe firmă și unde le trece clientul: la checkout sau ni le trimite pe WhatsApp? (ex.: CUI și denumire, în câmpul Companie de la checkout) (`date-factura-firma`)
   - Clientul întreabă: „Ce date trebuie pentru factura pe firmă?”
   - Ce am găsit: Nicio sursă citită nu descrie cum se introduc datele firmei.
18. Acceptăm plata la termen pentru firme (după livrare, la 15 sau 30 de zile)? (nu / da, în ce condiții) (`plata-la-termen`)
   - Clientul întreabă: „Se poate plăti la termen?”
   - Ce am găsit: Nicio sursă citită nu vorbește despre plata la termen.
19. La plata prin OP, producția începe la primirea dovezii de plată sau după ce intră banii în cont? (una dintre cele două) (`op-incepe-productia`)
   - Clientul întreabă: „Când începe producția la plata prin OP?”
   - Ce am găsit: Nicio sursă citită nu spune când pornește producția la plata prin OP.

### Rezistența materialelor

20. Câți ani rezistă la exterior, în soare și ploaie, un Sticker Standard și un Sticker Premium, fără să se decoloreze? (ex.: 2 ani, respectiv 4 ani) (`durata-exterior`)
   - Clientul întreabă: „Câți ani rezistă la exterior?”
   - Ce am găsit: Site-ul spune doar „durabilitate în timp” și „ani buni”, fără o cifră.
21. Rezistă stickerele și etichetele la mașina de spălat vase? Dacă da, pe care material și cu ce adeziv? (da / nu / doar spălare de mână) (`masina-spalat-vase`)
   - Clientul întreabă: „Rezistă în mașina de spălat vase?”
   - Ce am găsit: Nicio sursă citită nu vorbește despre mașina de spălat vase.
22. Rezistă etichetele lipite pe produse ținute la frigider? Dar la congelator, și până la ce temperatură? (ex.: frigider da, congelator da până la -18 grade) (`frigider-congelator`)
   - Clientul întreabă: „Rezistă la frigider sau la congelator?”
   - Ce am găsit: Nicio sursă citită nu vorbește despre frigider, congelator sau condens.
23. Până la ce temperatură rezistă stickerele și etichetele (cuptor cu microunde, borcane umplute la cald, lumânări, motor)? (ex.: până la 80 de grade) (`temperatura-ridicata`)
   - Clientul întreabă: „Rezistă la temperaturi ridicate?”
   - Ce am găsit: Nicio sursă citită nu dă o temperatură maximă.
24. Putem spune că etichetele sunt sigure pentru contact direct cu alimentele, sau doar pentru ambalaj? Avem vreun certificat? (da cu certificat / doar pe ambalaj) (`contact-alimentar`)
   - Clientul întreabă: „Pot fi lipite direct pe alimente?”
   - Ce am găsit: Site-ul recomandă etichetele pentru ambalaje de alimente, dar nu spune nimic despre contactul direct sau despre certificate.
25. Rezistă printul la alcool, dezinfectant, benzină sau solvenți? (ex.: alcool da, solvenți nu) (`rezistenta-chimicale`)
   - Clientul întreabă: „Rezistă la alcool, dezinfectant sau solvenți?”
   - Ce am găsit: Nicio sursă citită nu vorbește despre alcool, dezinfectant sau solvenți.

### Termene și urgențe

26. În câte zile lucrătoare livrăm o comandă de stickere sau etichete cu opțiunea Urgență și care este textul exact de spus clientului? (ex.: expediere în 1-2 zile lucrătoare de la aprobarea graficii) (`urgenta-termen`)
   - Clientul întreabă: „În cât timp este gata o comandă urgentă?”
   - Ce am găsit: Calculatorul spune doar „livrare prioritară”; specificația estimatorului de livrare are o valoare implicită de 1 zi, dar nu este publicată pe site.
27. Cât durează curierul după ce comanda pleacă din atelier? (ex.: 1-2 zile lucrătoare) (`durata-transport`)
   - Clientul întreabă: „Cât durează transportul după expediere?”
   - Ce am găsit: Site-ul dă doar termenul total (2-10 zile lucrătoare); textul vechi din ro.json spune 1-2 zile de livrare.

## Contradicții între surse

1. Adăugăm în lista aprobată „rezistente la apă, UV și zgârieturi” și „rezistă la exterior”, exact ca pe site? (da / nu / alt text) (`afirmatii-material`, Rezistența materialelor)
   - Ce am găsit: Lista aprobată din rules.json permite doar „rezistență la umezeală și ulei”, „lac UV mat” și „fără laminare”. Site-ul afirmă pe fiecare produs „rezistente la apă, UV și zgârieturi” și „rezistă în mediul exterior”, iar la Etichete Embossed și „intemperii”. Verificarea din ec-quote (guard) blochează orice text cu „rezistent” care nu este în lista aprobată.
   - Surse: config:ec-quote/config/rules.json approved_material_claims; site:/products/sticker-standard#faq; shopify:product etichete-embossed descriptionHtml
2. Finisajul este mat la toate materialele, inclusiv Gold, Chrome și Holografic? (da / nu, care sunt lucioase) (`lac-mat-vs-stralucire`, Materiale, finisaje și adeziv)
   - Ce am găsit: rules.json spune „lac UV mat”. Site-ul spune la Etichete Gold, Chrome și Holografice „protejate cu strat de lac pentru strălucire”, iar la embosate „finisaj mat și relief lucios”.
   - Surse: config:ec-quote/config/rules.json approved_material_claims; shopify:product etichete-gold descriptionHtml; shopify:product etichete-embossed descriptionHtml
3. Care este termenul de spus clienților: 2-10 zile lucrătoare în total, sau 2-4 zile producție plus 1-2 zile livrare? (`termen-productie`, Termene și urgențe)
   - Ce am găsit: Site-ul și politica de retur spun 2-10 zile lucrătoare pentru producție și livrare. Textul vechi din calculator (ro.json, faq_delivery_time_answer) spune 2-4 zile lucrătoare producție plus 1-2 zile livrare.
   - Surse: site:/products/sticker-standard#faq; shopify:shop.shopPolicies REFUND_POLICY §5; repo:extensions/calculator/locales/ro.json calculator.faq_delivery_time_answer
4. Ce număr de WhatsApp dăm clienților: 0792 772 295, 0755 094 695 sau amândouă (și pentru ce)? (`telefon-whatsapp`, Contact și program)
   - Ce am găsit: Site-ul și Shopify dau telefonul și WhatsApp-ul 0792 772 295. Regulile din ec-agency (2026-11-17) dau pentru oferta de mostre WhatsApp +40 755 094 695.
   - Surse: site:/pages/contact; repo:/home/user/ec-agency/context/owner-rules.md rândul 2026-11-17 „Campania Timișoara trece pe oferta de mostre gratuite”
5. Livrăm în afara României? (nu / da, cum se comandă și cât costă) (`livrare-europa`, Livrare)
   - Ce am găsit: Pagina „Despre noi” spune „Livrăm în toată Europa” și „27 țări deservite în UE”. În Shopify singura zonă de livrare este România, iar calculatorul afișează „Expediat în toată România!”.
   - Surse: site:/pages/despre-noi; shopify:deliveryProfiles „General profile” (doar România); shopify:shop.metafield calculator.settings translations.shippingBadge
6. Ce prag de rezoluție comunicăm clientului pe WhatsApp: 300 DPI, ca în politică, sau acceptăm fără avertisment de la 150 DPI? (`dpi-minim`, Fișiere și grafică)
   - Ce am găsit: Politica de retur și termenii cer minimum 300 DPI. rules.json din ec-quote consideră fișierul bun de la 150 DPI și slab între 100 și 150, iar Print Studio blochează abia sub 150 DPI.
   - Surse: shopify:shop.shopPolicies REFUND_POLICY §3.1; config:ec-quote/config/rules.json min_dpi_ok / min_dpi_weak; repo:features/application-architecture.md:657
7. Trimitem simulare la fiecare comandă și așteptăm aprobarea, sau doar la cerere? Pe ce canal o trimitem? (`simulare-bt`, Fișiere și grafică)
   - Ce am găsit: Site-ul promite „Simulare gratuită la fiecare comandă, înainte de producție”. Termenii spun că producția așteaptă aprobarea doar „dacă clientul solicită simulare grafică”. Politica de retur spune că furnizorul nu verifică fișierele în prealabil și că producția începe pe baza fișierelor primite.
   - Surse: site:/ bannerul de sus; shopify:shop.shopPolicies TERMS_OF_SERVICE §2; shopify:shop.shopPolicies REFUND_POLICY §3.1
8. Ce format au planșele și rolele de etichete: 50 × 120 cm sau 40-50 cm × 100/130 cm? (`format-role`, Materiale, finisaje și adeziv)
   - Ce am găsit: FAQ-ul de pe paginile de produs spune planșe sau role cu lățime 40-50 cm și lungime 100 cm / 130 cm. Descrierile produselor spun „Format role/coli: 50 × 120 cm”.
   - Surse: site:/products/etichete-premium#faq; shopify:product etichete-premium descriptionHtml
9. Spunem clienților că primim și PSD sau ZIP? (da / nu) (`formate-fisier`, Fișiere și grafică)
   - Ce am găsit: Calculatorul afișează clientului „PNG, JPG, PDF, SVG, AI”. Setările calculatorului acceptă și ZIP și PSD.
   - Surse: repo:extensions/calculator/locales/ro.json calculator.upload_hint; shopify:shop.metafield calculator.settings fileUpload.acceptedFormats
10. Confirmi: minimum 50 de bucăți la stickere și etichete și 100 pe model la service auto? (da / alte valori) (`cantitate-minima-texte`, Comandă și cantități)
   - Ce am găsit: Site-ul afișează comandă minimă de 50 de bucăți, iar setările calculatorului au minQuantity 50. Textele din ro.json spun încă „Cantitate minimă: 25 buc”. Etichetele pentru service auto au minimum 100 de bucăți pe model.
   - Surse: site:/products/sticker-standard secțiunea „Specificații tehnice”; repo:extensions/calculator/locales/ro.json calculator.min_qty_warning; shopify:collection service-auto descriptionHtml
11. Cât costă grafica făcută de noi la cărți de vizită și flyere: 70 lei sau 150 lei? (`taxa-grafica`, Fișiere și grafică)
   - Ce am găsit: Site-ul spune că grafica făcută de noi la cărți de vizită și flyere costă 70 lei. Metafieldul calculator.fixed_price_config are designFee 150.
   - Surse: site:/ secțiunea „Flyere / Cărți de vizită”; shopify:shop.metafield calculator.fixed_price_config businessCards.designFee
12. Care este adresa atelierului și o dăm clienților (pentru ridicare sau vizită)? (adresa / nu o comunicăm) (`adresa`, Contact și program)
   - Ce am găsit: Sediul din subsolul site-ului și din politici este Str. Eugen Ionesco nr. 67, Cluj-Napoca. Locația magazinului din Shopify este Strada Grigore Alexandrescu 13, Cluj-Napoca. Pagina de contact arată la locație doar „România”.
   - Surse: site:/ subsol; shopify:locations „Shop location”; site:/pages/contact
13. Sticker Sheet este rezistent și la zgârieturi, ca Sticker Standard? (da / nu) (`sticker-sheet-rezistenta`, Rezistența materialelor)
   - Ce am găsit: Ghidul din colecția Stickere spune la Sticker Sheet rezistență la „apă și raze UV”. Pagina produsului spune „rezistent la apă, UV și zgârieturi”.
   - Surse: shopify:collection stickere descriptionHtml; shopify:product sticker-sheet descriptionHtml
14. Pe ce adresă de email trimitem clienții pentru anulări și reclamații? (`email-comenzi`, Contact și program)
   - Ce am găsit: Pagina de contact dă vanzari@etichetecreative.ro pentru comenzi și oferte. Politica de retur cere anulările și reclamațiile pe hello@etichetecreative.ro sau etichetecreative@gmail.com.
   - Surse: site:/pages/contact; shopify:shop.shopPolicies REFUND_POLICY §2 și §6
15. Care este reducerea corectă la Kit service auto: 14% sau 30%? (`reducere-kit-service`, Comandă și cantități)
   - Ce am găsit: Descrierea produsului Kit service auto spune „aproximativ 14% mai puțin decât separat”. Prima pagină a site-ului afișează la același kit „−30% în pachet”.
   - Surse: shopify:product kit-service-auto descriptionHtml; site:/ secțiunea de kituri
