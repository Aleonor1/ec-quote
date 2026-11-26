# ec-quote pe VPS

Două containere: aplicația (`app`, un singur proces) și Caddy (TLS automat). Datele stau în volumul `ecquote_data`.

## Ce trebuie setat

1. DNS: un subdomeniu (de exemplu `oferta.etichetecreative.ro`) cu înregistrare A către VPS. Porturile 80 și 443 deschise.
2. Fișierul `.env` din rădăcina `ec-quote` (copiat din `.env.example`), cu valorile reale. Pe lângă cele din exemplu:

| Variabilă | Rol |
| --- | --- |
| `EC_QUOTE_INBOUND_SECRET` | Minim 24 de caractere. Aceeași valoare se pune în CRM și în calculator. Generare: `openssl rand -hex 32` |
| `EC_QUOTE_PUBLIC_BASE_URL` | `https://oferta.etichetecreative.ro`. Baza linkurilor de imagini trimise către CRM și chat |
| `EC_QUOTE_ATTACHMENT_HOSTS` | Gazdele de la care se descarcă atașamentele trimise de CRM, separate prin virgulă. Goală: niciun atașament nu se descarcă |
| `EC_QUOTE_CORS_ORIGINS` | Originile magazinului, dacă widgetul cheamă direct ec-quote: `https://etichetecreative.ro,https://www.etichetecreative.ro`. Goală dacă chatul trece doar prin App Proxy |
| `EC_QUOTE_CHAT_REQUIRE_SECRET` | `1` dacă chatul trece doar prin App Proxy-ul calculatorului (rutele `/v1/chat/*` cer atunci secretul) |
| `EC_QUOTE_SIGNING_SECRET` | Opțional. Cheia pentru sesiuni și linkuri de imagini; fără ea se derivă din secretul de intrare |

Limitele (mărimi, ritm, durate) au valori implicite; lista completă este în `ec_quote/config.py`. Nu setați `EC_QUOTE_DEMO` în producție.

3. Domeniul pentru Caddy, în `deploy/.env`:

```bash
echo "EC_QUOTE_DOMAIN=oferta.etichetecreative.ro" > deploy/.env
```

## Pornire

```bash
cd deploy
GIT_COMMIT=$(git rev-parse HEAD) docker compose up -d --build
docker compose ps                      # app trebuie să fie "healthy"
curl https://oferta.etichetecreative.ro/health
```

Dacă lipsește o variabilă, aplicația nu pornește și scrie în log numele ei: `docker compose logs app`.

## Actualizare

```bash
git pull
cd deploy
GIT_COMMIT=$(git rev-parse HEAD) docker compose up -d --build app
curl https://oferta.etichetecreative.ro/health   # "commit" trebuie să fie cel nou
```

Repornirea durează câteva secunde. Mesajele retrimise de CRM în acest timp nu se dublează (id-ul mesajului este ținut minte în baza de date).

## Copie de siguranță

Volumul `ecquote_data` conține bazele SQLite, fișierele primite de la clienți și imaginile de ofertă. Copia se face cu aplicația oprită, ca fișierele SQLite să fie consistente:

```bash
cd deploy
mkdir -p ../backup
docker compose stop app
docker run --rm -v ecquote_data:/data:ro -v "$PWD/../backup":/backup alpine \
  tar czf /backup/ecquote-$(date +%F).tgz -C /data .
docker compose start app
```

Mutați arhiva de pe VPS (conține date personale). Programare zilnică: aceleași comenzi într-un script rulat din `cron`, noaptea.

Restaurare:

```bash
docker compose stop app
docker run --rm -v ecquote_data:/data -v "$PWD/../backup":/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/ecquote-AAAA-LL-ZZ.tgz -C /data"
docker compose start app
```

## De știut

- Un singur worker: limitele de ritm și ordinea mesajelor pe conversație sunt ținute în memoria procesului. Nu porniți mai multe instanțe.
- Motorul poate răspunde în zeci de secunde; puntea din CRM trebuie să aștepte răspunsul la `POST /v1/inbound` cel puțin 120 de secunde.
- Pagina de probă a widgetului (`/demo/`) există doar cu `EC_QUOTE_DEMO=1`, pentru lucru local.
