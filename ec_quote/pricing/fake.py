"""Dublura de test a calculatorului: catalog mic si preturi deterministe, prin acelasi CalculatorClient.

Folosire in testele altor module:
    fake = FakeCalculator()
    pricing = fake.client()          # un CalculatorClient adevarat, fara retea
    fake.fail_next(503)              # urmatorul raspuns e 503
Preturile NU sunt cele reale ale site-ului; sunt doar stabile si plauzibile.
"""
from __future__ import annotations

import copy
import json
import math
from decimal import ROUND_CEILING, Decimal
from typing import Any, Callable

import httpx

from ec_quote.pricing.client import CONFIG_PATH, LINE_PATH, SECRET_HEADER, CalculatorClient

FAKE_BASE_URL = "https://calculator.test"
FAKE_SECRET = "test-secret"
STICKER_ID = "gid://shopify/Product/1001"
LABEL_ID = "gid://shopify/Product/1002"
FIXED_SIZE_ID = "gid://shopify/Product/1003"

_EQUAL = [{"label": f"{n} x {n}", "widthCm": n, "heightCm": n} for n in (3, 5, 7, 10)]
_RECT = [{"label": "9 x 4", "widthCm": 9, "heightCm": 4}, {"label": "10 x 5", "widthCm": 10, "heightCm": 5},
         {"label": "7.5 x 5", "widthCm": 7.5, "heightCm": 5}]
_OVAL = [{"label": "6 x 4", "widthCm": 6, "heightCm": 4}, {"label": "9 x 6", "widthCm": 9, "heightCm": 6}]
_TIERS = [{"quantity": q, "discountPercent": d}
          for q, d in ((50, 0), (100, 10), (200, 20), (300, 28), (500, 36), (1000, 45), (2000, 52))]

FAKE_CATALOG: dict = {
    "version": 1,
    "generatedAt": "2026-11-26T08:00:00.000Z",
    "settings": {
        "setupFee": 25,
        "minQuantity": 25,
        "maxOrderQuantity": 10000,
        "urgency": {"enabled": True, "flatFeeRON": 125, "percent": 50, "maxQuantity": 500},
        "adhesive": {"enabled": True, "strongPercent": 25},
        "whitePrint": {"enabled": True, "percent": 30},
        "doubleCut": {"enabled": True, "percent": 15},
        "backCut": {"enabled": True, "percent": 35},
        "fileEditing": {"enabled": True, "options": [
            {"name": "none", "label": "Fara editare", "flatFeeRON": 0},
            {"name": "upscale", "label": "Imbunatatire calitate", "flatFeeRON": 25},
            {"name": "vectorize", "label": "Vectorizare", "flatFeeRON": 50},
        ]},
        "conturStudioEnabled": True,
        "uploadPublicBaseUrl": "https://cdn.test",
    },
    "products": [
        {
            "id": STICKER_ID, "title": "Stickere Personalizate", "handle": "stickere-personalizate",
            "kind": "sticker", "emboss": False, "studio": True, "sample": False,
            "shapes": ["custom", "circle", "oval", "square", "rectangle"],
            "materials": [
                {"name": "Vinil Alb Lucios", "pricingTableId": "gid://shopify/Metaobject/11"},
                {"name": "Vinil Alb Mat", "pricingTableId": "gid://shopify/Metaobject/12"},
                {"name": "Vinil Transparent", "pricingTableId": "gid://shopify/Metaobject/13"},
                {"name": "Hârtie Kraft", "pricingTableId": "gid://shopify/Metaobject/14"},
            ],
            "sizes": {"equal": _EQUAL, "oval": _OVAL, "rectangle": _RECT},
            "sizesByShape": {"custom": _EQUAL, "circle": _EQUAL, "square": _EQUAL, "oval": _OVAL, "rectangle": _RECT},
            "customSize": {"enabled": True, "minCm": 2, "maxCm": 100},
            "addOnGroups": [{"name": "Finisaj", "choices": [
                {"name": "Fără laminare", "modifierPercent": 0}, {"name": "Laminare mată", "modifierPercent": 20}]}],
            "options": {"adhesive": True, "whitePrint": True, "cut": True, "urgency": True,
                        "fileEditing": True, "instructions": True},
            "quantity": {"tiers": _TIERS, "min": 25, "default": 100, "max": 10000},
        },
        {
            "id": LABEL_ID, "title": "Etichete Autocolante pe Rolă", "handle": "etichete-autocolante-rola",
            "kind": "label", "emboss": False, "studio": False, "sample": False,
            "shapes": ["circle", "rectangle"],
            "materials": [
                {"name": "Hârtie Albă Lucioasă", "pricingTableId": "gid://shopify/Metaobject/21"},
                {"name": "Polipropilenă Albă", "pricingTableId": "gid://shopify/Metaobject/22"},
            ],
            "sizes": {"equal": _EQUAL, "oval": _OVAL, "rectangle": _RECT},
            "sizesByShape": {"circle": _EQUAL, "rectangle": _RECT},
            "customSize": {"enabled": True, "minCm": 1, "maxCm": 30},
            "addOnGroups": [],
            "options": {"adhesive": True, "whitePrint": False, "cut": False, "urgency": True,
                        "fileEditing": True, "instructions": False},
            "quantity": {"tiers": [{"quantity": q, "discountPercent": d}
                                   for q, d in ((100, 0), (250, 12), (500, 25), (1000, 38), (5000, 55))],
                         "min": 100, "default": 250, "max": 5000},
        },
        {
            "id": FIXED_SIZE_ID, "title": "Stickere Rotunde Holografice", "handle": "stickere-rotunde-holografice",
            "kind": "sticker", "emboss": False, "studio": False, "sample": False,
            "shapes": ["circle"],
            "materials": [{"name": "Vinil Holografic", "pricingTableId": "gid://shopify/Metaobject/31"}],
            "sizes": {"equal": _EQUAL, "oval": [], "rectangle": []},
            "sizesByShape": {"circle": _EQUAL},
            "customSize": {"enabled": False, "minCm": 1, "maxCm": 100},
            "addOnGroups": [],
            "options": {"adhesive": False, "whitePrint": False, "cut": True, "urgency": False,
                        "fileEditing": False, "instructions": False},
            "quantity": {"tiers": _TIERS[:5], "min": 50, "default": 100, "max": 10000},
        },
    ],
}

# lei / cm2 / bucata, cu TVA. "Hârtie Kraft" lipseste intentionat: da 422 no_price.
_RATES = {
    "Vinil Alb Lucios": Decimal("0.062"), "Vinil Alb Mat": Decimal("0.066"), "Vinil Transparent": Decimal("0.078"),
    "Hârtie Albă Lucioasă": Decimal("0.021"), "Polipropilenă Albă": Decimal("0.027"),
    "Vinil Holografic": Decimal("0.095"),
}
_BODY_TYPES: dict[str, Callable[[Any], bool]] = {
    "productId": lambda v: isinstance(v, str) and v.startswith("gid://shopify/Product/"),
    "materialName": lambda v: isinstance(v, str) and bool(v.strip()),
    "shape": lambda v: isinstance(v, str) and bool(v.strip()),
    "widthCm": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "heightCm": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "quantity": lambda v: isinstance(v, int) and not isinstance(v, bool) and v >= 1,
}
_OPTIONAL_TYPES: dict[str, tuple[Callable[[Any], bool], Any]] = {
    "addOns": (lambda v: isinstance(v, dict) and all(isinstance(c, str) for c in v.values()), {}),
    "adhesive": (lambda v: v in ("standard", "strong"), "standard"),
    "whitePrint": (lambda v: isinstance(v, bool), False),
    "cut": (lambda v: v in ("none", "double", "back"), "none"),
    "urgent": (lambda v: isinstance(v, bool), False),
    "fileEditing": (lambda v: v in ("none", "upscale", "vectorize"), "none"),
    "instructions": (lambda v: isinstance(v, str) and len(v) <= 500, ""),
}


def _d(value: Any) -> Decimal:
    return Decimal(str(value))


def _money(value: Decimal) -> int | float:
    """Numar JSON, ca serverul JS (doar la granita de serializare a dublurii)."""
    cents = value.quantize(Decimal("0.01"))
    return int(cents) if cents == cents.to_integral_value() else float(cents)


class FakeCalculator:
    """Serveste GET calculator-config si POST line ca aplicatia reala (aceleasi statusuri si coduri 422)."""

    def __init__(self, catalog: dict | None = None, secret: str = FAKE_SECRET):
        self.catalog = copy.deepcopy(catalog if catalog is not None else FAKE_CATALOG)
        self.secret = secret
        self.requests: list[tuple[str, str, dict | None]] = []  # (metoda, cale, corp)
        self._failures: list[int | Exception] = []

    # ---------- unelte pentru teste ----------

    def fail_next(self, *failures: int | Exception) -> None:
        """Urmatoarele raspunsuri: un status (ex. 503) sau o exceptie (ex. httpx.ReadTimeout('x'))."""
        self._failures.extend(failures)

    def calls(self, path: str) -> int:
        return sum(1 for _, p, _ in self.requests if p == path)

    @property
    def line_bodies(self) -> list[dict]:
        return [body for _, path, body in self.requests if path == LINE_PATH and body is not None]

    def http(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self.handle))

    def client(self, **kwargs: Any) -> CalculatorClient:
        """Un CalculatorClient adevarat legat de dublura. kwargs merg la constructor (clock, ttl...)."""
        return CalculatorClient(FAKE_BASE_URL, self.secret, http=self.http(), **kwargs)

    # ---------- serverul ----------

    def handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        body = None
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = None
        self.requests.append((request.method, path, body if isinstance(body, dict) else None))
        if self._failures:
            failure = self._failures.pop(0)
            if isinstance(failure, Exception):
                raise failure
            if failure == 503:
                return httpx.Response(503, json={"error": "admin_unavailable", "retryable": True})
            if failure == 400:
                return httpx.Response(400, json={"error": "invalid_body", "fields": ["body"]})
            return httpx.Response(failure, json={"error": "Unauthorized" if failure == 401 else "error"})
        if request.headers.get(SECRET_HEADER) != self.secret:
            return httpx.Response(401, json={"error": "Unauthorized"})
        if path == CONFIG_PATH and request.method == "GET":
            return httpx.Response(200, json=self.catalog)
        if path == LINE_PATH and request.method == "POST":
            status, payload = self.price(body)
            return httpx.Response(status, json=payload)
        if path == LINE_PATH:
            return httpx.Response(405, json={"error": "method_not_allowed"}, headers={"Allow": "POST"})
        return httpx.Response(404, json={"error": "not_found"})

    def price(self, body: Any) -> tuple[int, dict]:
        """(status, raspuns) pentru un corp CalculatorChoices."""
        if not isinstance(body, dict):
            return 400, {"error": "invalid_body", "fields": ["body"]}
        fields = [name for name, valid in _BODY_TYPES.items() if not valid(body.get(name))]
        choices = {name: body.get(name) for name in _BODY_TYPES}
        for name, (valid, fallback) in _OPTIONAL_TYPES.items():
            value = body.get(name, fallback)
            if not valid(value):
                fields.append(name)
            choices[name] = value
        if fields:
            return 400, {"error": "invalid_body", "fields": fields}
        reason = self._unpriced(choices)
        if reason:
            return 422, {"status": "unpriced", **reason}
        return 200, self._priced(choices)

    def _product(self, product_id: str) -> dict | None:
        return next((p for p in self.catalog["products"] if p["id"] == product_id), None)

    def _unpriced(self, c: dict) -> dict | None:
        product = self._product(c["productId"])
        if product is None:
            return {"reason": "unknown_product"}
        settings = self.catalog["settings"]
        if not any(m["name"] == c["materialName"] for m in product["materials"]):
            return {"reason": "unknown_material"}
        if c["shape"] not in product["shapes"]:
            return {"reason": "unknown_shape"}
        w, h = _d(c["widthCm"]), _d(c["heightCm"])
        presets = [(_d(s["widthCm"]), _d(s["heightCm"])) for s in product["sizesByShape"].get(c["shape"], [])]
        if (w, h) not in presets and (h, w) not in presets:
            custom = product["customSize"]
            if not custom["enabled"]:
                return {"reason": "custom_size_disabled"}
            if w > custom["maxCm"] or h > custom["maxCm"]:
                return {"reason": "size_above_maximum", "maxCm": custom["maxCm"]}
            if w < custom["minCm"] or h < custom["minCm"]:
                return {"reason": "size_below_minimum", "minCm": custom["minCm"]}
        quantity = product["quantity"]
        if c["quantity"] < quantity["min"]:
            return {"reason": "quantity_below_minimum", "minQuantity": quantity["min"]}
        if c["quantity"] > quantity["max"]:
            return {"reason": "quantity_above_maximum", "maxQuantity": quantity["max"]}
        options = product["options"]
        chosen = (("adhesive", c["adhesive"] == "strong"), ("whitePrint", c["whitePrint"]), ("cut", c["cut"] != "none"),
                  ("urgency", c["urgent"]), ("fileEditing", c["fileEditing"] != "none"),
                  ("instructions", bool(c["instructions"].strip())))
        for option, wanted in chosen:
            if wanted and not options[option]:
                return {"reason": "option_unavailable", "option": option}
        if c["urgent"] and c["quantity"] > settings["urgency"]["maxQuantity"]:
            return {"reason": "urgency_quantity_exceeded", "maxQuantity": settings["urgency"]["maxQuantity"]}
        groups = {g["name"]: [ch["name"] for ch in g["choices"]] for g in product["addOnGroups"]}
        for group, choice in c["addOns"].items():
            if choice not in groups.get(group, []):
                return {"reason": "unknown_add_on", "option": group}
        if c["materialName"] not in _RATES:
            return {"reason": "no_price"}
        return None

    def _priced(self, c: dict) -> dict:
        product = self._product(c["productId"])
        settings = self.catalog["settings"]
        qty = c["quantity"]
        area = Decimal(math.floor(_d(c["widthCm"]) * _d(c["heightCm"]) + Decimal("0.5")))
        table_price = (_RATES[c["materialName"]] * area + Decimal("0.35")).quantize(Decimal("0.01"))
        discount = max((_d(t["discountPercent"]) for t in product["quantity"]["tiers"] if t["quantity"] <= qty),
                       default=Decimal(0))
        add_on = Decimal(0)
        for group in product["addOnGroups"]:
            if not group["choices"]:
                continue
            chosen = c["addOns"].get(group["name"], group["choices"][0]["name"])
            add_on += next(_d(ch["modifierPercent"]) for ch in group["choices"] if ch["name"] == chosen)
        adhesive = _d(settings["adhesive"]["strongPercent"]) if c["adhesive"] == "strong" else Decimal(0)
        white = _d(settings["whitePrint"]["percent"]) if c["whitePrint"] else Decimal(0)
        cut = {"none": Decimal(0), "double": _d(settings["doubleCut"]["percent"]),
               "back": _d(settings["backCut"]["percent"])}[c["cut"]]
        option_factor = 1 + (add_on + adhesive + white + cut) / 100
        setup = _d(settings["setupFee"])
        urgency = _d(settings["urgency"]["flatFeeRON"]) if c["urgent"] else Decimal(0)
        editing = next((_d(o["flatFeeRON"]) for o in settings["fileEditing"]["options"] if o["name"] == c["fileEditing"]),
                       Decimal(0))
        plain = table_price * qty
        goods = plain * (1 - discount / 100)
        with_options = goods * option_factor

        def ceil(value: Decimal) -> Decimal:
            return value.to_integral_value(rounding=ROUND_CEILING)

        total = ceil(with_options + setup + urgency + editing)
        full = ceil(plain * option_factor + setup + urgency + editing)
        unit = (total / qty).quantize(Decimal("0.01"))
        size = f"{c['widthCm']} x {c['heightCm']} CM"
        return {
            "status": "priced",
            "total": _money(total),
            "base": _money(goods),
            "unitPrice": _money(unit),
            "capQuantity": None,
            "pricingPath": "A",
            "flatBaselinePct": 0,
            "breakdown": {
                "tablePrice": _money(table_price), "fullPrice": _money(full), "discount": _money(full - total),
                "options": _money(with_options - goods), "urgency": _money(urgency), "fileEditing": _money(editing),
                "setupFee": _money(setup), "discountPercent": _money(discount),
                "quantityDiscountPercent": _money(discount), "promoPercent": 0, "promoMode": "replace",
                "flatPercent": 0, "addOnPercent": _money(add_on), "adhesivePercent": _money(adhesive),
                "whitePrintPercent": _money(white), "cutPercent": _money(cut), "freeSample": False,
            },
            "properties": [
                {"name": "_Sticker Quantity", "value": str(qty)},
                {"name": "Forma Taiere", "value": c["shape"]},
                {"name": "Dimensiune", "value": size},
                {"name": "Material", "value": c["materialName"]},
                {"name": "Cantitate", "value": f"{qty} buc"},
                {"name": "_calculator_price", "value": str(_money(total))},
                {"name": "_calculator_area", "value": str(area)},
                {"name": "_price_per_unit", "value": str(_money(unit))},
                {"name": "_product_gid", "value": c["productId"]},
            ],
        }
