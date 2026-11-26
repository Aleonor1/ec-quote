"""Clientul calculatorului: singura sursa de pret (GET calculator-config, POST line)."""
from __future__ import annotations

import json
import threading
import time
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Callable

import httpx

from ec_quote.contracts import LineChoices, LineProperty, PriceQuote, TierOffer, Unpriced
from ec_quote.pricing.errors import (
    PricingBadRequest,
    PricingProtocolError,
    PricingUnauthorized,
    PricingUnavailable,
)

CONFIG_PATH = "/api/sync/calculator-config"
LINE_PATH = "/api/sync/line"
SECRET_HEADER = "X-Sync-Secret"
DEFAULT_CATALOG_TTL_SECONDS = 300.0
DEFAULT_TIMEOUT_SECONDS = 10.0
ATTEMPTS = 2  # o singura reincercare
RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"
CENT = Decimal("0.01")


def load_vat_percent(rules_path: Path | str = RULES_PATH) -> Decimal:
    """TVA-ul din config/rules.json (text, ca sa ramana Decimal exact)."""
    rules = json.loads(Path(rules_path).read_text(encoding="utf-8"))
    return Decimal(str(rules["vat_percent"]))


def ex_vat(total: Decimal, vat_percent: Decimal) -> Decimal:
    """Totalul fara TVA, la 2 zecimale, ROUND_HALF_UP."""
    return (total / (1 + vat_percent / Decimal(100))).quantize(CENT, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise PricingProtocolError(f"numar asteptat, primit {value!r}")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except ArithmeticError as err:
        raise PricingProtocolError(f"numar asteptat, primit {value!r}") from err


def _json_number(value: Decimal) -> int | float:
    """Dimensiune (nu bani) ca numar JSON: calculatorul respinge textul. 5 ramane 5, 5.5 ramane 5.5."""
    if value == value.to_integral_value():
        return int(value)
    return float(value)


def choices_to_body(choices: LineChoices) -> dict:
    """LineChoices (snake_case) in corpul camelCase CalculatorChoices."""
    return {
        "productId": choices.product_id,
        "materialName": choices.material_name,
        "shape": choices.shape,
        "widthCm": _json_number(choices.width_cm),
        "heightCm": _json_number(choices.height_cm),
        "quantity": choices.quantity,
        "addOns": dict(choices.add_ons),
        "adhesive": choices.adhesive,
        "whitePrint": choices.white_print,
        "cut": choices.cut,
        "urgent": choices.urgent,
        "fileEditing": choices.file_editing,
        "instructions": choices.instructions,
    }


def find_product(catalog: dict, product_id: str) -> dict | None:
    for product in catalog.get("products") or []:
        if product.get("id") == product_id:
            return product
    return None


def next_tier_quantities(product: dict, quantity: int, count: int) -> list[int]:
    """Urmatoarele `count` trepte strict peste `quantity`, cel mult quantity.max."""
    info = product.get("quantity") or {}
    maximum = info.get("max")
    found = sorted(
        {
            int(tier["quantity"])
            for tier in info.get("tiers") or []
            if int(tier["quantity"]) > quantity and (maximum is None or int(tier["quantity"]) <= int(maximum))
        }
    )
    return found[: max(count, 0)]


class CalculatorClient:
    """Implementeaza PricingPort peste calculator-app.

    `http` este un httpx.Client sau un apelabil cu semnatura lui `httpx.Client.request`
    (method, url, headers=, content=, timeout=) care intoarce ceva cu `status_code` si `text`.
    """

    def __init__(
        self,
        base_url: str,
        secret: str,
        http: Any = None,
        *,
        catalog_ttl_seconds: float = DEFAULT_CATALOG_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        vat_percent: Decimal | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._secret = secret
        self._http = http if http is not None else httpx.Client()
        self._ttl = catalog_ttl_seconds
        self._clock = clock
        self._timeout = timeout_seconds
        self._vat_percent = vat_percent if vat_percent is not None else load_vat_percent()
        self._catalog: dict | None = None
        self._catalog_at = 0.0
        self._lock = threading.Lock()

    # ---------- PricingPort ----------

    def catalog(self) -> dict:
        """Configuratia calculatorului, tinuta in cache `catalog_ttl_seconds`.

        Daca reimprospatarea esueaza si exista o copie veche, o servim pe aceea:
        catalogul ajuta doar la potrivirea numelor, pretul vine tot din calculator.
        """
        with self._lock:
            now = self._clock()
            if self._catalog is not None and now - self._catalog_at < self._ttl:
                return self._catalog
            try:
                status, payload = self._call("GET", CONFIG_PATH)
            except PricingUnavailable:
                if self._catalog is not None:
                    return self._catalog
                raise
            if status != 200 or not isinstance(payload, dict) or not isinstance(payload.get("products"), list):
                raise PricingProtocolError(f"calculator-config: raspuns neasteptat ({status})")
            self._catalog = payload
            self._catalog_at = now
            return payload

    def invalidate_catalog(self) -> None:
        with self._lock:
            self._catalog = None

    def get_price(self, choices: LineChoices) -> PriceQuote | Unpriced:
        status, payload = self._call("POST", LINE_PATH, choices_to_body(choices), exact_numbers=True)
        if not isinstance(payload, dict):
            raise PricingProtocolError(f"line: raspuns neasteptat ({status})")
        if status == 422:
            reason = payload.get("reason")
            if not isinstance(reason, str) or not reason:
                raise PricingProtocolError("line: 422 fara reason")
            details = {k: v for k, v in payload.items() if k not in ("status", "reason")}
            return Unpriced(reason=reason, details=details)
        if status != 200 or payload.get("status") != "priced":
            raise PricingProtocolError(f"line: raspuns neasteptat ({status})")
        return self._quote(choices, payload)

    def get_price_tiers(self, choices: LineChoices, count: int) -> list[TierOffer]:
        """Urmatoarele `count` trepte din catalog peste cantitatea ceruta, fiecare pretuita de calculator.

        Treptele nepretuite (422) sunt sarite; lista poate fi mai scurta decat `count`.
        """
        product = find_product(self.catalog(), choices.product_id)
        if product is None:
            return []
        offers: list[TierOffer] = []
        for quantity in next_tier_quantities(product, choices.quantity, count):
            result = self.get_price(choices.model_copy(update={"quantity": quantity}))
            if isinstance(result, Unpriced):
                continue
            offers.append(
                TierOffer(
                    quantity=quantity,
                    total=result.total,
                    total_ex_vat=result.total_ex_vat,
                    unit_price=result.unit_price,
                )
            )
        return offers

    # ---------- intern ----------

    def _quote(self, choices: LineChoices, payload: dict) -> PriceQuote:
        breakdown = payload.get("breakdown")
        properties = payload.get("properties")
        if not isinstance(breakdown, dict) or not isinstance(properties, list):
            raise PricingProtocolError("line: lipsesc breakdown sau properties")
        try:
            total = _to_decimal(payload["total"])
            unit_price = _to_decimal(payload["unitPrice"])
            discount = _to_decimal(breakdown.get("discountPercent", 0))
            cap = payload.get("capQuantity")
            return PriceQuote(
                choices=choices,
                total=total,
                total_ex_vat=ex_vat(total, self._vat_percent),
                unit_price=unit_price,
                discount_percent=discount,
                cap_quantity=int(cap) if cap is not None else None,
                breakdown=breakdown,
                properties=[LineProperty(name=str(p["name"]), value=str(p["value"])) for p in properties],
            )
        except (KeyError, TypeError, ValueError) as err:
            raise PricingProtocolError(f"line: raspuns priced incomplet ({err})") from err

    def _call(self, method: str, path: str, body: dict | None = None, *, exact_numbers: bool = False) -> tuple[int, Any]:
        """Trimite cererea; o reincercare la 503 / timeout / retea. Intoarce (status, json)."""
        headers = {SECRET_HEADER: self._secret, "Accept": "application/json"}
        content = None
        if body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(body, ensure_ascii=False).encode("utf-8")
        send = self._http.request if hasattr(self._http, "request") else self._http
        last = "necunoscut"
        for _ in range(ATTEMPTS):
            try:
                response = send(method, self._base_url + path, headers=headers, content=content, timeout=self._timeout)
            except (httpx.TransportError, TimeoutError, ConnectionError) as err:
                last = type(err).__name__
                continue
            status = response.status_code
            if status == 503 or status in (502, 504):
                last = f"HTTP {status}"
                continue
            payload = self._parse(response.text, exact_numbers)
            if status == 401:
                raise PricingUnauthorized("calculatorul a respins X-Sync-Secret")
            if status == 400:
                fields = payload.get("fields") if isinstance(payload, dict) else None
                raise PricingBadRequest([str(f) for f in fields] if isinstance(fields, list) else [])
            return status, payload
        raise PricingUnavailable(f"calculator indisponibil: {method} {path} ({last})")

    @staticmethod
    def _parse(text: str, exact_numbers: bool) -> Any:
        try:
            # parse_float=Decimal: sumele nu trec niciodata prin float
            return json.loads(text, parse_float=Decimal) if exact_numbers else json.loads(text)
        except ValueError:
            return None
