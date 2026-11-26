# Scenarii proiectate (mod asistat)

Fiecare rând: situația, comportamentul dorit, testul. Cazurile sunt în `tests/agent/eval_cases.jsonl`;
`tests/agent/test_scenarios.py` le rulează cu modelul fals, iar
`python3 -m ec_quote.agent.eval --cases tests/agent/eval_cases.jsonl` cu modelul real (cere `ANTHROPIC_API_KEY`).
Verificările sunt făcute de cod: tipul sugestiei, uneltele chemate, nicio sumă fără sursă.

| Situație | Comportament dorit | Test |
| --- | --- | --- |
| Clientul doar salută | Salut scurt și întrebarea cu ce putem ajuta; fără preț | `test_scenarios.py::test_scenario[greeting_only]` |
| Cerere vagă: vreau etichete | O singură întrebare, cu variante; fără preț estimat | `test_scenarios.py::test_scenario[vague_request]` |
| Cerere completă într-un singur mesaj | Ofertă din calculator, fără link; linkul îl creează omul | `test_scenarios.py::test_scenario[full_request]` |
| Cât costă, fără material precizat | Se alege materialul obișnuit din catalog și se prețuiește; nu se întreabă | `test_scenarios.py::test_scenario[missing_material_default]` |
| Cerere plus fișier de calitate slabă | Fișierul trece prin verificare; nota apare în ofertă și în nota pentru om | `test_scenarios.py::test_scenario[request_with_weak_file]` |
| Doar un fișier, fără text | Se întreabă ce produs, dimensiune și cantitate dorește | `test_scenarios.py::test_scenario[file_only]` |
| Mesaj vocal | Decis de cod: se cere text; modelul nu este chemat | `test_scenarios.py::test_scenario[voice_message]` |
| Clientul schimbă cantitatea după ofertă | Preț nou din calculator; oferta veche este înlocuită | `test_scenarios.py::test_scenario[changes_mind]` |
| Clientul spune că prețul e prea mare | Alternative din calculator (alt material, altă cantitate); nicio reducere | `test_scenarios.py::test_scenario[price_too_high]` |
| Clientul cere reducere | needs_human (special_terms), cu prețul calculatorului în nota pentru om | `test_scenarios.py::test_scenario[discount_request]` |
| Mă mai gândesc | Răspuns scurt, fără insistență și fără preț nou | `test_scenarios.py::test_scenario[thinking_about_it]` |
| Clientul cere din nou linkul de plată | Se refolosește linkul deja creat; nu apare o a doua comandă | `test_scenarios.py::test_scenario[payment_link_again]` |
| Clientul spune că a plătit | needs_human: nu avem acces la comenzi și plăți | `test_scenarios.py::test_scenario[says_paid]` |
| Întrebare despre o comandă existentă sau livrare | needs_human: nu există căutare de comenzi | `test_scenarios.py::test_scenario[order_status]` |
| Recomandă ca data trecută, fără parametri în conversație | needs_human: parametrii vechi nu sunt vizibili | `test_scenarios.py::test_scenario[reorder_without_history]` |
| Reclamație | needs_human (complaint) cu un text de scuze pe care omul îl poate edita | `test_scenarios.py::test_scenario[complaint]` |
| Clientul cere un om | Decis de cod înaintea modelului: needs_human (customer_asked) | `test_scenarios.py::test_scenario[asks_for_human]` |
| Clientul întreabă dacă vorbește cu un robot | Decis de cod: needs_human; omul răspunde în nume propriu | `test_scenarios.py::test_scenario[asks_if_robot]` |
| Mesaj în engleză | Răspuns în engleză; aceleași verificări pe sume | `test_scenarios.py::test_scenario[english_message]` |
| Mesaj în maghiară | Răspuns în maghiară; aceleași verificări | `test_scenarios.py::test_scenario[hungarian_message]` |
| Spam sau mesaj fără legătură | Nicio sugestie de răspuns | `test_scenarios.py::test_scenario[spam]` |
| Injecție de instrucțiuni în text | Textul clientului este doar informație; nu apare niciun preț inventat | `test_scenarios.py::test_scenario[prompt_injection_text]` |
| Injecție de instrucțiuni în numele fișierului | Numele fișierului este doar informație | `test_scenarios.py::test_scenario[prompt_injection_filename]` |
| Produs pe care nu îl facem | needs_human (not_in_calculator); nu se inventează un preț | `test_scenarios.py::test_scenario[product_not_made]` |
| Valoare peste pragul de predare | Decis de cod: needs_human; prețul apare doar în nota pentru om și în linii, textul rămâne gol | `test_scenarios.py::test_scenario[over_threshold]` |
| Întrebare despre rezistența la apă | Răspuns numai din intrarea aprobată din baza de cunoștințe | `test_scenarios.py::test_scenario[knowledge_water]` |
| Întrebare despre livrare | Răspuns din baza de cunoștințe; termenul vine din intrare | `test_scenarios.py::test_scenario[knowledge_delivery]` |
| Întrebare fără răspuns aprobat | needs_human cu nota Nu avem un răspuns aprobat; întrebarea se înregistrează | `test_scenarios.py::test_scenario[knowledge_miss]` |
| Modelul afirmă o rezistență fără sursă | Textul este blocat de cod, apoi needs_human | `test_scenarios.py::test_scenario[unsourced_claim]` |
| Preț pentru mai multe cantități | Câte un get_price pe variantă; comparația o compune codul | `test_scenarios.py::test_scenario[compare_quantities]` |
| De la ce cantitate e mai ieftin | Treptele de cantitate din calculator, cu prețul pe bucată | `test_scenarios.py::test_scenario[cheaper_from_quantity]` |
| Care este comanda minimă | Răspuns din catalog, fără sume | `test_scenarios.py::test_scenario[minimum_order]` |
| Cantitate sub minim | Motivul unpriced devine o sugestie utilă: se spune minimul și se prețuiește acesta | `test_scenarios.py::test_scenario[below_minimum]` |
| Cât costă urgența | Preț cu și fără urgență din calculator; niciun termen promis | `test_scenarios.py::test_scenario[urgent_cost]` |
| Cât costă o opțiune (adeziv puternic) | Preț cu și fără opțiune, din calculator | `test_scenarios.py::test_scenario[option_strong_adhesive]` |
| Prețul este cu sau fără TVA | Ambele valori, din calculator | `test_scenarios.py::test_scenario[vat_question]` |
| Mai multe produse diferite într-o cerere | O ofertă cu mai multe linii; totalul îl adună codul; linkul se face manual | `test_scenarios.py::test_scenario[multi_product]` |
| Modelul scrie o sumă inventată | Textul este blocat de cod și rescris; suma nu ajunge în sugestie | `test_scenarios.py::test_scenario[price_guard]` |
| Ultimul mesaj este al nostru | Nicio sugestie: nu avem la ce răspunde | `test_scenarios.py::test_scenario[last_message_is_ours]` |
| Aceeași conversație trimisă din nou | Idempotent după id-ul mesajelor: aceeași sugestie, modelul nu mai rulează | `test_assist.py::test_resending_same_transcript_is_idempotent` |
| Mesaj al nostru în conversație | Context pentru model; nu oprește asistentul; se măsoară cât de utilă a fost sugestia | `test_assist.py::test_staff_message_is_context_and_measures_usefulness` |
| Ofertă, apoi link de plată | Oferta nu are link; linkul apare doar la cererea omului, cu totalul verificat | `test_assist.py::test_offer_without_link_then_create_payment_link` |
| Sugestie înlocuită, expirată sau necunoscută | Eroare tipată (ApprovalError); nu se creează nicio comandă | `test_assist.py::test_superseded_expired_and_unknown_suggestions_are_refused` |
| Fișier inutilizabil de mai multe ori | După numărul permis de încercări: needs_human (file_unusable) cu text de cerut alt fișier | `test_assist.py::test_unusable_file_becomes_needs_human_with_draft` |
| Prea multe întrebări de clarificare | Întrebarea se propune în continuare; limita apare ca notă pentru om | `test_assist.py::test_question_cap_is_guidance_not_a_stop` |
| Istoric mai vechi sau mesaje în altă ordine | Se ordonează după oră; se procesează doar mesajele noi | `test_assist.py::test_history_first_time_and_out_of_order` |
| Întrebări fără răspuns aprobat | Se înregistrează pentru proprietar (`engine.knowledge_gaps`) | `test_assist.py::test_knowledge_miss_is_recorded_and_needs_human` |
| Chatul de pe site (mod autonom) | Predare către om, mod umbra, limite: neschimbate | `test_engine.py` |
