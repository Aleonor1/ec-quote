"""Link de plata Shopify: un Draft Order cu pretul exact al calculatorului (CheckoutPort).

Cum taxeaza site-ul o linie de calculator: 1 bucata dintr-o varianta a produsului, cu pretul
variantei egal cu totalul calculat (TVA inclus) si cu alegerile in proprietatile liniei
(calculator-app: api.storefront.create-variant + calculator.js). Aici facem acelasi lucru fara
sa cream variante: linia foloseste varianta permanenta a produsului (prima care nu e `calc-*`,
acelea sunt temporare si se sterg) si `priceOverride` = PriceQuote.total.

De ce varianta + priceOverride si nu linie custom: comanda pastreaza product_id si titlul
produsului, deci CRM-ul, productia si rapoartele o citesc ca pe o comanda de pe site. Linia
custom (`originalUnitPriceWithCurrency`) ramane doar plasa de siguranta cand produsul nu are
nicio varianta permanenta.

TVA: magazinul are `taxesIncluded = true`, deci pretul unui draft include TVA, ca pe site.
Nu ne bazam pe asta orbeste: dupa creare comparam totalul draftului cu PriceQuote.total si,
daca difera, stergem draftul si ridicam ShopifyPriceMismatch.

`sourceName` ramane nesetat: comanda rezultata are sursa `shopify_draft_order`, pe care
auditul de pret din calculator-app o sare (order-price-audit.server.ts).
"""
from __future__ import annotations

import logging
import mimetypes
import re
import time
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Callable, Literal

import httpx
from pydantic import BaseModel

from ec_quote.contracts import Checkout, Contact, PriceQuote
from ec_quote.integrations.errors import (
    DraftOrderNotFound,
    ShopifyInvalidQuote,
    ShopifyPriceMismatch,
    ShopifyProductNotFound,
    ShopifyProtocolError,
    ShopifyThrottled,
    ShopifyUnauthorized,
    ShopifyUnavailable,
    ShopifyUserError,
)

log = logging.getLogger(__name__)

DEFAULT_API_VERSION = "2026-04"  # ApiVersion.April26 din calculator-app
DEFAULT_TIMEOUT_SECONDS = 15.0
CURRENCY = "RON"
CENT = Decimal("0.01")
TOKEN_HEADER = "X-Shopify-Access-Token"

BASE_TAG = "ec-quote"
ARTWORK_TYPE_PROP = "_Upload Artwork"   # tipul fisierului (MIME), ca pe site
ARTWORK_URL_PROP = "_Upload Artwork1"   # URL-ul fisierului
PRODUCT_GID_PROP = "_product_gid"
TEMP_VARIANT_PREFIX = "calc-"
ATTR_CHANNEL = "ec_quote_channel"
ATTR_KEY = "ec_quote_key"
ATTR_VALID_UNTIL = "ec_quote_valid_until"
ATTR_AD_SOURCE = "ec_quote_ad_source"

THROTTLED_CODE = "THROTTLED"
MIN_THROTTLE_WAIT_SECONDS = 0.5
MAX_THROTTLE_WAIT_SECONDS = 10.0
ATTEMPTS = 2  # o singura reincercare, numai la throttling
MAX_TAG_LENGTH = 40
PHONE_E164 = re.compile(r"^\+[1-9]\d{7,14}$")

VARIANTS_QUERY = """
query EcQuoteProductVariants($id: ID!) {
  product(id: $id) {
    id
    title
    variants(first: 100) {
      nodes { id selectedOptions { name value } }
    }
  }
}
"""

CREATE_MUTATION = """
mutation EcQuoteDraftOrderCreate($input: DraftOrderInput!) {
  draftOrderCreate(input: $input) {
    draftOrder {
      id
      name
      invoiceUrl
      status
      taxesIncluded
      totalPriceSet { shopMoney { amount currencyCode } }
    }
    userErrors { field message }
  }
}
"""

DELETE_MUTATION = """
mutation EcQuoteDraftOrderDelete($input: DraftOrderDeleteInput!) {
  draftOrderDelete(input: $input) {
    deletedId
    userErrors { field message }
  }
}
"""

STATUS_QUERY = """
query EcQuoteDraftOrderStatus($id: ID!) {
  draftOrder(id: $id) {
    id
    status
    invoiceUrl
    completedAt
    order { id name displayFinancialStatus }
  }
}
"""


class DraftOrderStatus(BaseModel):
    """Starea unui draft, pentru urmarirea platii."""

    draft_order_id: str
    state: Literal["open", "completed"]
    shopify_status: str                 # OPEN, INVOICE_SENT, COMPLETED
    invoice_url: str | None = None
    order_id: str | None = None         # gid-ul comenzii, cand draftul e completat
    order_name: str | None = None
    financial_status: str | None = None  # PAID, PENDING, ...
    paid: bool = False


def mask_key(value: str | None) -> str:
    """Cheia conversatiei sau telefonul, pentru log: numai ultimele 3 caractere."""
    if not value:
        return "?"
    return "***" + value[-3:] if len(value) > 3 else "***"


def product_gid(product_id: str) -> str:
    value = (product_id or "").strip()
    if value.isdigit():
        return f"gid://shopify/Product/{value}"
    return value


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def e164(phone: str | None) -> str | None:
    """Telefonul in forma pe care o accepta Shopify, sau None (un telefon dubios nu blocheaza oferta)."""
    if not phone:
        return None
    digits = re.sub(r"[^\d+]", "", phone)
    if digits.startswith("00"):
        digits = "+" + digits[2:]
    elif digits.startswith("0") and len(digits) == 10:
        digits = "+4" + digits  # numar national romanesc
    elif not digits.startswith("+"):
        digits = "+" + digits
    return digits if PHONE_E164.match(digits) else None


def _tag(value: str) -> str:
    """Eticheta Shopify: fara virgule, cel mult 40 de caractere."""
    return re.sub(r"[,\s]+", "-", value.strip())[:MAX_TAG_LENGTH].strip("-")


def build_tags(contact: Contact) -> list[str]:
    tags = [BASE_TAG, f"{BASE_TAG}-{contact.channel}"]
    if contact.ad_source and contact.ad_source.strip():
        tags.append(_tag(f"ad-{contact.ad_source}"))
    return tags


def line_attributes(quote: PriceQuote, artwork_url: str | None) -> list[dict[str, str]]:
    """Proprietatile liniei, in ordinea calculatorului; fisierul la sfarsit, ca in calculator.js."""
    attributes = [{"key": p.name, "value": p.value} for p in quote.properties]
    if artwork_url:
        names = {p.name for p in quote.properties}
        if ARTWORK_URL_PROP not in names:
            path = artwork_url.split("?", 1)[0]
            file_type = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if ARTWORK_TYPE_PROP not in names:
                attributes.append({"key": ARTWORK_TYPE_PROP, "value": file_type})
            attributes.append({"key": ARTWORK_URL_PROP, "value": artwork_url})
    return attributes


def build_note(contact: Contact, valid_until: datetime) -> str:
    return (
        f"Oferta instant ec-quote. Conversatie: {contact.channel}:{contact.key}. "
        f"Valabila pana la {valid_until.strftime('%Y-%m-%d %H:%M')}."
    )


class ShopifyCheckout:
    """CheckoutPort peste Admin GraphQL. `http` este injectat (teste cu httpx.MockTransport)."""

    def __init__(
        self,
        shop_domain: str,
        admin_token: str,
        http: httpx.Client,
        api_version: str = DEFAULT_API_VERSION,
        *,
        sleep: Callable[[float], None] = time.sleep,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        domain = shop_domain.strip().removeprefix("https://").removeprefix("http://").strip("/")
        if not domain or not admin_token:
            raise ValueError("shop_domain si admin_token sunt obligatorii")
        self._url = f"https://{domain}/admin/api/{api_version}/graphql.json"
        self._token = admin_token
        self._http = http
        self._sleep = sleep
        self._timeout = timeout
        self._variant_cache: dict[str, str | None] = {}
        self._title_cache: dict[str, str] = {}

    def __repr__(self) -> str:  # tokenul nu ajunge in log prin repr
        return f"ShopifyCheckout(url={self._url!r})"

    # ---------- CheckoutPort ----------

    def create_checkout(
        self, quote: PriceQuote, contact: Contact, artwork_url: str | None, valid_until: datetime,
    ) -> Checkout:
        total = quote.total.quantize(CENT, rounding=ROUND_HALF_UP)
        if total <= 0:
            raise ShopifyInvalidQuote("totalul ofertei trebuie sa fie pozitiv")
        product_id = self._product_id(quote)
        variant_id = self._permanent_variant(product_id)

        line: dict[str, Any] = {
            "quantity": 1,  # ca pe site: o linie, cantitatea de stickere e in proprietati
            "customAttributes": line_attributes(quote, artwork_url),
        }
        price = {"amount": money(total), "currencyCode": CURRENCY}
        if variant_id:
            line["variantId"] = variant_id
            line["priceOverride"] = price
        else:
            line["title"] = self._title_cache.get(product_id) or quote.choices.material_name
            line["originalUnitPriceWithCurrency"] = price
            line["taxable"] = True
            line["requiresShipping"] = True

        order_attributes = [
            {"key": ATTR_CHANNEL, "value": contact.channel},
            {"key": ATTR_KEY, "value": contact.key},
            {"key": ATTR_VALID_UNTIL, "value": valid_until.isoformat()},
        ]
        if contact.ad_source:
            order_attributes.append({"key": ATTR_AD_SOURCE, "value": contact.ad_source})
        draft_input: dict[str, Any] = {
            "lineItems": [line],
            "tags": build_tags(contact),
            "note": build_note(contact, valid_until),
            "customAttributes": order_attributes,
        }
        phone = e164(contact.phone)
        if phone:
            draft_input["phone"] = phone
        if contact.email and "@" in contact.email:
            draft_input["email"] = contact.email.strip()

        data = self._graphql(CREATE_MUTATION, {"input": draft_input})
        payload = data.get("draftOrderCreate") or {}
        if payload.get("userErrors"):
            raise ShopifyUserError("draftOrderCreate", payload["userErrors"])
        draft = payload.get("draftOrder")
        if not isinstance(draft, dict) or not draft.get("id") or not draft.get("invoiceUrl"):
            raise ShopifyProtocolError("draftOrderCreate: lipsesc id sau invoiceUrl")

        actual = self._draft_total(draft)
        if actual != total:
            deleted = self._try_delete(draft["id"])
            log.error(
                "draft %s: total %s in loc de %s (taxesIncluded=%s)",
                draft["id"], actual, total, draft.get("taxesIncluded"),
            )
            raise ShopifyPriceMismatch(total, actual, draft["id"], deleted)

        log.info(
            "draft %s creat: %s %s, canal %s, conversatie %s",
            draft["id"], total, CURRENCY, contact.channel, mask_key(contact.key),
        )
        return Checkout(draft_order_id=draft["id"], invoice_url=draft["invoiceUrl"], total=total)

    # ---------- urmarirea platii ----------

    def get_status(self, draft_order_id: str) -> DraftOrderStatus:
        data = self._graphql(STATUS_QUERY, {"id": draft_order_id})
        draft = data.get("draftOrder")
        if not isinstance(draft, dict):
            raise DraftOrderNotFound(draft_order_id)
        shopify_status = str(draft.get("status") or "")
        order = draft.get("order") if isinstance(draft.get("order"), dict) else None
        financial = order.get("displayFinancialStatus") if order else None
        return DraftOrderStatus(
            draft_order_id=draft.get("id") or draft_order_id,
            state="completed" if shopify_status == "COMPLETED" else "open",
            shopify_status=shopify_status,
            invoice_url=draft.get("invoiceUrl"),
            order_id=order.get("id") if order else None,
            order_name=order.get("name") if order else None,
            financial_status=financial,
            paid=financial == "PAID",
        )

    def delete_draft_order(self, draft_order_id: str) -> None:
        """Sterge un draft deschis (oferta expirata sau inlocuita)."""
        data = self._graphql(DELETE_MUTATION, {"input": {"id": draft_order_id}})
        payload = data.get("draftOrderDelete") or {}
        if payload.get("userErrors"):
            raise ShopifyUserError("draftOrderDelete", payload["userErrors"])

    # ---------- interne ----------

    @staticmethod
    def _product_id(quote: PriceQuote) -> str:
        raw = quote.choices.product_id
        if not raw:
            raw = next((p.value for p in quote.properties if p.name == PRODUCT_GID_PROP), "")
        gid = product_gid(raw)
        if not gid:
            raise ShopifyInvalidQuote("oferta nu are produs")
        return gid

    def _permanent_variant(self, product_id: str) -> str | None:
        if product_id in self._variant_cache:
            return self._variant_cache[product_id]
        data = self._graphql(VARIANTS_QUERY, {"id": product_id})
        product = data.get("product")
        if not isinstance(product, dict):
            raise ShopifyProductNotFound(product_id)
        self._title_cache[product_id] = str(product.get("title") or "")
        nodes = ((product.get("variants") or {}).get("nodes")) or []
        chosen: str | None = None
        for node in nodes:
            values = [str(o.get("value") or "") for o in (node.get("selectedOptions") or [])]
            if not any(v.startswith(TEMP_VARIANT_PREFIX) for v in values):
                chosen = node.get("id")
                break
        if chosen is None:
            log.warning("produsul %s nu are varianta permanenta; linie custom", product_id)
        self._variant_cache[product_id] = chosen
        return chosen

    @staticmethod
    def _draft_total(draft: dict) -> Decimal:
        try:
            amount = draft["totalPriceSet"]["shopMoney"]["amount"]
            return Decimal(str(amount)).quantize(CENT, rounding=ROUND_HALF_UP)
        except (KeyError, TypeError, InvalidOperation) as err:
            raise ShopifyProtocolError("draftOrderCreate: lipseste totalPriceSet") from err

    def _try_delete(self, draft_order_id: str) -> bool:
        try:
            self.delete_draft_order(draft_order_id)
            return True
        except Exception:  # eroarea de pret e cea care conteaza; stergerea esuata se raporteaza in ea
            log.exception("draftul %s nu a putut fi sters", draft_order_id)
            return False

    def _graphql(self, query: str, variables: dict) -> dict:
        """Un apel GraphQL. Reincearca o singura data, numai cand Shopify spune THROTTLED sau 429
        (cererea nu a fost executata, deci nici mutatia de creare nu se dubleaza)."""
        wait = 0.0
        for attempt in range(ATTEMPTS):
            if wait:
                self._sleep(wait)
            try:
                response = self._http.post(
                    self._url,
                    json={"query": query, "variables": variables},
                    headers={TOKEN_HEADER: self._token, "Content-Type": "application/json"},
                    timeout=self._timeout,
                )
            except httpx.HTTPError as err:
                raise ShopifyUnavailable(f"retea: {type(err).__name__}") from err

            status = response.status_code
            if status in (401, 403):
                raise ShopifyUnauthorized(f"HTTP {status}")
            if status == 429:
                wait = self._retry_after(response)
                continue
            if status >= 500:
                raise ShopifyUnavailable(f"HTTP {status}")
            if status != 200:
                raise ShopifyProtocolError(f"HTTP {status}")
            try:
                body = response.json()
            except ValueError as err:
                raise ShopifyProtocolError("raspuns care nu e JSON") from err
            if not isinstance(body, dict):
                raise ShopifyProtocolError("raspuns JSON neasteptat")

            errors = body.get("errors")
            if errors:
                if self._is_throttled(errors):
                    wait = self._throttle_wait(body)
                    continue
                raise ShopifyProtocolError(self._error_text(errors))
            data = body.get("data")
            if not isinstance(data, dict):
                raise ShopifyProtocolError("raspuns fara data")
            return data
        raise ShopifyThrottled("limita de cost depasita si dupa reincercare")

    @staticmethod
    def _is_throttled(errors: Any) -> bool:
        if not isinstance(errors, list):
            return False
        return any(
            isinstance(e, dict) and (e.get("extensions") or {}).get("code") == THROTTLED_CODE
            for e in errors
        )

    @staticmethod
    def _error_text(errors: Any) -> str:
        if isinstance(errors, list):
            return "; ".join(str(e.get("message", e)) if isinstance(e, dict) else str(e) for e in errors)
        return str(errors)

    @staticmethod
    def _clamp(seconds: float) -> float:
        return max(MIN_THROTTLE_WAIT_SECONDS, min(MAX_THROTTLE_WAIT_SECONDS, seconds))

    def _throttle_wait(self, body: dict) -> float:
        """Cat asteptam: (cost cerut - disponibil) / rata de refacere, din extensions.cost."""
        try:
            cost = body["extensions"]["cost"]
            throttle = cost["throttleStatus"]
            missing = float(cost["requestedQueryCost"]) - float(throttle["currentlyAvailable"])
            return self._clamp(missing / float(throttle["restoreRate"]))
        except (KeyError, TypeError, ValueError, ZeroDivisionError):
            return 1.0

    def _retry_after(self, response: httpx.Response) -> float:
        try:
            return self._clamp(float(response.headers.get("Retry-After", "1")))
        except ValueError:
            return 1.0
