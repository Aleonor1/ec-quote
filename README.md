# ec-quote

Asistent de ofertare pentru Etichete Creative. O extensie Chrome citeste conversatia deschisa in WhatsApp Web si propune un raspuns: pret exact, imagine de oferta, link de plata, raspunsuri la intrebarile obisnuite. Omul insereaza textul si apasa el Trimite; nimic nu pleaca automat.

Stare: parcat temporar in ramura de lucru a calculator-app, pana exista depozitul propriu. Nu se imbina in `master`.

- Pretul vine numai din calculatorul site-ului (`POST /api/sync/line`, `GET /api/sync/calculator-config`, antet `X-Sync-Secret`). Modelul nu calculeaza nimic.
- Raspunsurile despre materiale, livrare, plata vin numai din baza de cunostinte aprobata (`knowledge/`).
- Extensia: `extension/`. Backend: `ec_quote/`. Contracte: `ec_quote/contracts.py`. Politica: `config/rules.json`.
- Plan si intrebari pentru owner: `docs/plan.md`. Story-uri: `specs/todo/`.

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```
