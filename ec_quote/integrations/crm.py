"""Clientul CRM-ului (CrmPort + HandoffPort) peste puntea `/api/ec-quote/*`.

Contractul este in specs/todo/crm-ec-quote-bridge.md. CRM-ul nu are azi niciun endpoint
masina la masina pentru lead-uri sau conversatii (formularul public `/api/leads/form-submit`
nu intoarce id, respinge duplicatele in tacere si are limita de 5 pe ora), deci toate rutele
de aici sunt cele cerute in spec. Autentificarea urmeaza tiparul existent in CRM pentru
apelanti de serviciu (HARVESTER_INGEST_TOKEN, PRODUCTION_AGENT_TOKEN): `Authorization: Bearer`.

Fiecare scriere poarta `Idempotency-Key`, deci o reincercare dupa timeout nu dubleaza nimic.
"""
from __future__ import annotations

import hashlib
import json
import logging
import mimetypes
import time
from datetime import datetime, time as dtime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

from ec_quote.contracts import Checkout, Contact, HandoffReason, OutboundAction, PriceQuote
from ec_quote.integrations.errors import (
    CrmNotConfigured,
    CrmProtocolError,
    CrmRejected,
    CrmUnauthorized,
    CrmUnavailable,
)

log = logging.getLogger(__name__)

BRIDGE_PREFIX = "/api/ec-quote"
LEADS_PATH = f"{BRIDGE_PREFIX}/leads"
HANDOFFS_PATH = f"{BRIDGE_PREFIX}/handoffs"
MESSAGES_PATH = f"{BRIDGE_PREFIX}/messages"
APPROVALS_PATH = f"{BRIDGE_PREFIX}/approvals"
MEDIA_PATH = f"{BRIDGE_PREFIX}/media"
HEALTH_PATH = "/api/health"  # exista deja in CRM, fara autentificare

IDEMPOTENCY_HEADER = "Idempotency-Key"
DEFAULT_TIMEOUT_SECONDS = 10.0
ATTEMPTS = 2  # o singura reincercare; sigura datorita cheii de idempotenta
RETRY_WAIT_SECONDS = 0.5
MAX_SUMMARY_CHARS = 2000
CURRENCY = "RON"
BUCHAREST = ZoneInfo("Europe/Bucharest")
RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"

# Starile pe care CRM-ul le intelege (spec, sectiunea "Stari"). Alta valoare se pastreaza ca text.
LEAD_STATUSES = ("new", "quoted", "awaiting_approval", "link_sent", "paid", "handed_off", "lost")


def load_business_hours(rules_path: Path | str = RULES_PATH) -> dict:
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    return dict(rules["business_hours"])


def is_business_hours(now: datetime, hours: dict) -> bool:
    """`now` cu fus se trece in Europe/Bucharest; fara fus se considera deja ora Romaniei."""
    local = now.astimezone(BUCHAREST) if now.tzinfo else now
    if local.isoweekday() not in hours["days"]:
        return False
    start = dtime.fromisoformat(hours["start"])
    end = dtime.fromisoformat(hours["end"])
    return start <= local.time().replace(tzinfo=None) < end


def mask(value: str | None) -> str:
    """Telefon sau cheie de conversatie pentru log: numai ultimele 3 caractere."""
    if not value:
        return "?"
    return "***" + value[-3:] if len(value) > 3 else "***"


def idempotency_key(*parts: Any) -> str:
    raw = "\x1f".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def contact_body(contact: Contact) -> dict:
    return {
        "channel": contact.channel,
        "key": contact.key,
        "phone": contact.phone,
        "name": contact.name,
        "email": contact.email,
        "ad_source": contact.ad_source,
    }


def offer_body(quote: PriceQuote | None, checkout: Checkout | None) -> dict | None:
    """Oferta asa cum o vede CRM-ul. Banii pleaca text, ca sa ramana exacti."""
    if quote is None and checkout is None:
        return None
    body: dict[str, Any] = {"currency": CURRENCY}
    if quote is not None:
        c = quote.choices
        body.update({
            "total": str(quote.total),
            "total_ex_vat": str(quote.total_ex_vat),
            "unit_price": str(quote.unit_price),
            "discount_percent": str(quote.discount_percent),
            "quantity": c.quantity,
            "product_id": c.product_id,
            "material": c.material_name,
            "shape": c.shape,
            "width_cm": str(c.width_cm),
            "height_cm": str(c.height_cm),
            "urgent": c.urgent,
            "properties": [{"name": p.name, "value": p.value} for p in quote.properties],
        })
    if checkout is not None:
        body.update({
            "draft_order_id": checkout.draft_order_id,
            "invoice_url": checkout.invoice_url,
            "checkout_total": str(checkout.total),
        })
    return body


class CrmClient:
    """CrmPort + HandoffPort. `http` este injectat (teste cu httpx.MockTransport)."""

    def __init__(
        self,
        base_url: str,
        api_secret: str,
        http: httpx.Client,
        *,
        business_hours: dict | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        if not base_url or not api_secret:
            raise ValueError("base_url si api_secret sunt obligatorii")
        self._base = base_url.rstrip("/")
        self._secret = api_secret
        self._http = http
        self._hours = business_hours if business_hours is not None else load_business_hours()
        self._sleep = sleep
        self._timeout = timeout

    def __repr__(self) -> str:  # secretul nu ajunge in log prin repr
        return f"CrmClient(base={self._base!r})"

    # ---------- CrmPort ----------

    def upsert_lead(
        self, contact: Contact, summary: str, quote: PriceQuote | None,
        checkout: Checkout | None, status: str,
    ) -> str:
        """Creeaza sau actualizeaza lead-ul dupa telefon / wa_id. Intoarce id-ul lead-ului din CRM.

        Regula clientului existent o aplica CRM-ul: lead-ul nou se leaga de client, nu il dubleaza.
        """
        body = {
            "contact": contact_body(contact),
            "status": status,
            "summary": summary[:MAX_SUMMARY_CHARS],
            "offer": offer_body(quote, checkout),
        }
        key = idempotency_key(
            "lead", contact.channel, contact.key, status, body["summary"],
            quote.total if quote else None, checkout.draft_order_id if checkout else None,
        )
        data = self._request("PUT", LEADS_PATH, body, key)
        lead_id = data.get("lead_id")
        if lead_id is None or isinstance(lead_id, bool) or str(lead_id) == "":
            raise CrmProtocolError("raspuns fara lead_id")
        log.info(
            "lead %s %s: stare %s, conversatie %s, client existent %s",
            lead_id, "creat" if data.get("created") else "actualizat", status,
            mask(contact.key), bool(data.get("existing_customer")),
        )
        return str(lead_id)

    # ---------- HandoffPort ----------

    def handoff(self, contact: Contact, reason: HandoffReason, summary: str, now: datetime) -> None:
        """Marcheaza conversatia ca predata. In program CRM-ul anunta echipa; in afara lui doar marcheaza."""
        notify = is_business_hours(now, self._hours)
        body = {
            "contact": contact_body(contact),
            "reason": reason.value,
            "summary": summary[:MAX_SUMMARY_CHARS],
            "notify": notify,
            "occurred_at": now.isoformat(),
        }
        key = idempotency_key("handoff", contact.channel, contact.key, reason.value, now.isoformat())
        self._request("POST", HANDOFFS_PATH, body, key)
        log.info(
            "predare %s pentru conversatia %s (%s)",
            reason.value, mask(contact.key), "cu notificare" if notify else "fara notificare",
        )

    # ---------- canalul WhatsApp prin CRM (in afara porturilor) ----------

    def deliver(
        self, contact: Contact, action: OutboundAction, message_key: str,
        image_url: str | None = None,
    ) -> dict:
        """Trimite o actiune prin calea de trimitere a CRM-ului (plafoane, kill switch, inbox).

        `message_key` este cheia de idempotenta a mesajului, stabila la reincercari.
        O imagine fara URL public se incarca multipart din `action.image_path`.
        Refuzurile CRM-ului (outreach_disabled, service_cap_reached, window_closed,
        manual_mode) vin ca CrmRejected.
        """
        if action.kind not in ("text", "buttons", "image"):
            raise ValueError(f"actiunea {action.kind} nu se livreaza ca mesaj")
        body: dict[str, Any] = {
            "contact": contact_body(contact),
            "kind": action.kind,
            "text": action.text,
            "buttons": [{"id": b.id, "title": b.title} for b in action.buttons],
            "image_url": image_url,
        }
        key = idempotency_key("message", contact.channel, contact.key, message_key)
        if action.kind == "image" and not image_url:
            if not action.image_path:
                raise ValueError("actiune imagine fara image_path si fara image_url")
            path = Path(action.image_path)
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            files = {"image": (path.name, path.read_bytes(), mime)}
            return self._request("POST", MESSAGES_PATH, body, key, files=files)
        return self._request("POST", MESSAGES_PATH, body, key)

    def request_approval(
        self, contact: Contact, approval_id: str, preview_text: str,
        quote: PriceQuote | None = None, image_url: str | None = None,
    ) -> dict:
        """Mod umbra: cardul de aprobare din inbox. Decizia vine inapoi la ec-quote prin CRM."""
        body = {
            "contact": contact_body(contact),
            "approval_id": approval_id,
            "preview_text": preview_text[:MAX_SUMMARY_CHARS],
            "image_url": image_url,
            "offer": offer_body(quote, None),
        }
        return self._request("POST", APPROVALS_PATH, body, idempotency_key("approval", approval_id))

    def fetch_media(self, media_ref: str, dest_dir: str, filename: str | None = None) -> str:
        """Descarca un fisier primit de la client (media_ref din mesajul redirectionat). Intoarce calea locala."""
        safe_ref = "".join(ch for ch in str(media_ref) if ch.isalnum() or ch in "-_")
        if not safe_ref:
            raise ValueError("media_ref invalid")
        response = self._send("GET", f"{MEDIA_PATH}/{safe_ref}", None, None, None)
        self._raise_for_status(response)
        name = f"{safe_ref}-{Path(filename).name}" if filename else safe_ref
        target = Path(dest_dir) / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(response.content)
        return str(target)

    def ping(self) -> bool:
        """CRM-ul raspunde (GET /api/health, ruta existenta)."""
        try:
            return self._http.get(self._base + HEALTH_PATH, timeout=self._timeout).status_code == 200
        except httpx.HTTPError:
            return False

    # ---------- interne ----------

    def _request(self, method: str, path: str, body: dict, key: str, files: dict | None = None) -> dict:
        response = self._send(method, path, body, key, files)
        self._raise_for_status(response)
        if response.status_code == 204 or not response.content:
            return {}
        try:
            data = response.json()
        except ValueError as err:
            raise CrmProtocolError("raspuns care nu e JSON") from err
        if not isinstance(data, dict):
            raise CrmProtocolError("raspuns JSON neasteptat")
        return data

    def _send(
        self, method: str, path: str, body: dict | None, key: str | None, files: dict | None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._secret}"}
        if key:
            headers[IDEMPOTENCY_HEADER] = key
        kwargs: dict[str, Any] = {"headers": headers, "timeout": self._timeout}
        if files is not None:
            kwargs["data"] = {"payload": json.dumps(body, ensure_ascii=False)}
            kwargs["files"] = files
        elif body is not None:
            kwargs["json"] = body
        last: Exception | None = None
        for attempt in range(ATTEMPTS):
            if attempt:
                self._sleep(RETRY_WAIT_SECONDS)
            try:
                response = self._http.request(method, self._base + path, **kwargs)
            except httpx.HTTPError as err:
                last = CrmUnavailable(f"retea: {type(err).__name__}")
                last.__cause__ = err
                continue
            if response.status_code in (500, 502, 504):
                last = CrmUnavailable(f"HTTP {response.status_code}")
                continue
            return response
        assert last is not None
        raise last

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        status = response.status_code
        if 200 <= status < 300:
            return
        if status in (401, 403):
            raise CrmUnauthorized(f"HTTP {status}")
        if status == 503:
            raise CrmNotConfigured("HTTP 503")
        if 400 <= status < 500:
            code, details = "error", {}
            try:
                data = response.json()
                if isinstance(data, dict):
                    code = str(data.get("error") or code)
                    details = {k: v for k, v in data.items() if k != "error"}
            except ValueError:
                pass
            raise CrmRejected(status, code, details)
        raise CrmProtocolError(f"HTTP {status}")
