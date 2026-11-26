# ec-quote

Ofertare instant pentru Etichete Creative: clientul scrie liber (WhatsApp sau chatul de pe site) si primeste pret, mockup si link de plata. Planul: "Plan implementare: Ofertare instant pe site si WhatsApp".

Stare: schelet parcat temporar in ramura de lucru a calculator-app, pana exista depozitul propriu. Nu se imbina in `master`.

- Pretul vine numai din calculatorul site-ului (`POST /api/sync/line`, `GET /api/sync/calculator-config`, antet `X-Sync-Secret`). Modelul nu calculeaza nimic.
- WhatsApp-ul (Cloud API, Coexistence, inbox) este deja in CRM. ec-quote nu primeste webhook-ul Meta: CRM-ul ii trimite mesajele si livreaza raspunsurile.
- Contractele dintre module: `ec_quote/contracts.py`. Numerele de politica: `config/rules.json`.

```bash
python3 -m pip install -e ".[dev]"
python3 -m pytest -q
```
