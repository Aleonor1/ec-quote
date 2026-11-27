""" Audit de paritate a preturilor pe 50 de configuratii din catalog.

Verifica cap-coada ca pretul din POST /api/sync/line ajunge neschimbat in:
- PriceQuote (total, total_ex_vat, unit_price, _calculator_price, fara float);
- textul ofertei (ec_quote.agent.offer);
- continutul imaginii de oferta (ec_quote.mockup.offer.build_content);
- Draft Order-ul Shopify (ec_quote.integrations.shopify.ShopifyCheckout, priceOverride);
- treptele superioare (get_price_tiers vs get_price direct).
"""
from __future__ import annotations

import copy
import json
import random
import time
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Literal
from zoneinfo import ZoneInfo

import httpx

from ec_quote.agent import offer as offer_module
from ec_quote.agent.guard import money_mentions, parse_amount
from ec_quote.contracts import Contact, LineChoices, PriceQuote, Unpriced
from ec_quote.integrations.shopify import CURRENCY, ShopifyCheckout, money as shopify_money
from ec_quote.mockup.offer import build_content
from ec_quote.pricing.client import (
    CENT,
    CONFIG_PATH,
    LINE_PATH,
    CalculatorClient,
    choices_to_body,
    ex_vat,
    find_product,
    load_vat_percent,
)

TZ = ZoneInfo("Europe/Bucharest")
PLACEHOLDER_BASE_URL = "https://calculator.example.invalid"
PLACEHOLDER_CDN_URL = "https://cdn.example.invalid"
PLACEHOLDER_SECRET = "replay-placeholder-secret"
DEFAULT_AUDIT_COUNT = 50
DEFAULT_AUDIT_SEED = 42
DEFAULT_UPSELL_TIERS = 2
HALF_CENT = Decimal("0.005")
AUDIT_PRODUCTION_TERM = "2-4 zile lucratoare"
AUDIT_VALID_UNTIL = datetime(2026, 12, 10, 18, 0, tzinfo=TZ)
AUDIT_NOW = datetime(2026, 12, 3, 12, 0, tzinfo=TZ)
AUDIT_CONTACT = Contact(channel="whatsapp", key="40700000000", phone="+40700000000", name="Client Audit")


@dataclass(frozen=True)
class AuditMismatch:
    case_id: str
    config_summary: str
    field: str
    expected: str
    found: str


@dataclass(frozen=True)
class CaseAuditResult:
    case_id: str
    choices: LineChoices
    config_summary: str
    status: Literal["priced", "unpriced"]
    consistent: bool
    total: Decimal | None = None
    total_ex_vat: Decimal | None = None
    unit_price: Decimal | None = None
    unpriced_reason: str | None = None
    tier_quantities: tuple[int, ...] = ()
    mismatches: tuple[AuditMismatch, ...] = ()


@dataclass(frozen=True)
class ParityAuditReport:
    generated_at: datetime
    mode: Literal["live", "replay", "verify"]
    total_count: int
    consistent_count: int
    priced_count: int
    unpriced_count: int
    unpriced_by_reason: dict[str, int]
    cases: tuple[CaseAuditResult, ...]

    @property
    def ok(self) -> bool:
        return self.consistent_count == self.total_count

    @property
    def mismatches(self) -> list[AuditMismatch]:
        found: list[AuditMismatch] = []
        for case in self.cases:
            found.extend(case.mismatches)
        return found


# ---------- serializare JSON exacta fara float ----------

def dumps_exact_json(value: Any, *, indent: int | None = None) -> str:
    """Serializeaza JSON emitand valorile Decimal direct ca literali numerici exacti."""
    return _encode_json(value, indent=indent, level=0)


def _encode_json(value: Any, *, indent: int | None, level: int) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError(f"Decimal nefinit nu poate fi serializat in JSON: {value!r}")
        return format(value, "f")
    if isinstance(value, float):
        return json.dumps(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, (list, tuple)):
        if not value:
            return "[]"
        if indent is None:
            return "[" + ",".join(_encode_json(item, indent=None, level=level + 1) for item in value) + "]"
        pad = " " * (indent * (level + 1))
        closing = " " * (indent * level)
        inner = (",\n" + pad).join(_encode_json(item, indent=indent, level=level + 1) for item in value)
        return "[\n" + pad + inner + "\n" + closing + "]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        if indent is None:
            parts = [
                f"{json.dumps(str(k), ensure_ascii=False)}:{_encode_json(v, indent=None, level=level + 1)}"
                for k, v in value.items()
            ]
            return "{" + ",".join(parts) + "}"
        pad = " " * (indent * (level + 1))
        closing = " " * (indent * level)
        parts = [
            f"{json.dumps(str(k), ensure_ascii=False)}: {_encode_json(v, indent=indent, level=level + 1)}"
            for k, v in value.items()
        ]
        return "{\n" + pad + (",\n" + pad).join(parts) + "\n" + closing + "}"
    raise TypeError(f"Tip nesuportat pentru JSON exact: {type(value).__name__}")


def _sort_keys(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _sort_keys(value[k]) for k in sorted(value)}
    if isinstance(value, (Decimal, float)) and not isinstance(value, bool) and Decimal(str(value)) == int(Decimal(str(value))):
        return int(Decimal(str(value)))
    return value


def _canonical_request_key(body: dict) -> str:
    return dumps_exact_json(_sort_keys(body))


def describe_configuration(choices: LineChoices) -> str:
    opts: list[str] = []
    if choices.add_ons:
        opts.extend(f"{g}={c}" for g, c in sorted(choices.add_ons.items()))
    if choices.adhesive != "standard":
        opts.append(f"adhesive={choices.adhesive}")
    if choices.white_print:
        opts.append("whitePrint=true")
    if choices.cut != "none":
        opts.append(f"cut={choices.cut}")
    if choices.urgent:
        opts.append("urgent=true")
    if choices.file_editing != "none":
        opts.append(f"fileEditing={choices.file_editing}")
    extra = f" [{', '.join(opts)}]" if opts else ""
    return (
        f"{choices.product_id} | {choices.material_name} | {choices.shape} | "
        f"{choices.width_cm}x{choices.height_cm} cm | {choices.quantity} buc{extra}"
    )


# ---------- esantionarea determinista a celor 50 de configuratii ----------

def _dec(val: Any) -> Decimal:
    return Decimal(str(val))


def _material_names(product: dict) -> list[str]:
    raw = [m.get("name") if isinstance(m, dict) else m for m in (product.get("materials") or [])]
    return [str(name) for name in raw if name]


def _preset_sizes(product: dict, shape: str) -> list[tuple[Decimal, Decimal]]:
    by_shape = (product.get("sizesByShape") or {}).get(shape) or []
    if not by_shape:
        sizes = product.get("sizes") or {}
        by_shape = sizes.get(shape) or sizes.get("equal") or []
    result = [(_dec(s["widthCm"]), _dec(s["heightCm"])) for s in by_shape if "widthCm" in s and "heightCm" in s]
    return result or [(Decimal("5"), Decimal("5"))]


def _custom_size_candidates(product: dict, shape: str) -> list[tuple[Decimal, Decimal]]:
    custom = product.get("customSize") or {}
    if not custom.get("enabled"):
        return []
    min_cm = _dec(custom["minCm"])
    max_cm = _dec(custom["maxCm"])
    presets = set(_preset_sizes(product, shape))
    presets |= {(h, w) for w, h in presets}
    offsets = (
        (Decimal("0.5"), Decimal("1.5")),
        (Decimal("1.5"), Decimal("2.5")),
        (Decimal("2.5"), Decimal("4.5")),
        (Decimal("3.5"), Decimal("6.5")),
        (Decimal("4.2"), Decimal("7.8")),
    )
    extra = [
        (min(max_cm, min_cm + w_off), min(max_cm, min_cm + h_off))
        for w_off, h_off in offsets
    ] + [(min_cm, max_cm)]
    return [(min_cm, min_cm), (max_cm, max_cm)] + [pair for pair in dict.fromkeys(extra) if pair not in presets]


def _tier_quantities(product: dict) -> list[int]:
    q_info = product.get("quantity") or {}
    q_min = int(q_info.get("min", 1))
    q_max = int(q_info.get("max", 10000))
    tiers = sorted({int(t["quantity"]) for t in q_info.get("tiers") or [] if q_min <= int(t["quantity"]) <= q_max})
    return tiers or [q_min]


def _between_tier_quantities(product: dict) -> list[int]:
    tiers = _tier_quantities(product)
    q_info = product.get("quantity") or {}
    q_min = int(q_info.get("min", 1))
    q_max = int(q_info.get("max", 10000))
    bounds = ([q_min] if q_min < tiers[0] - 1 else []) + tiers + ([q_max] if tiers[-1] + 1 < q_max else [])
    return [(left + right) // 2 for left, right in zip(bounds, bounds[1:]) if right - left > 1]


def _addon_choices(product: dict) -> list[dict[str, str]]:
    combos: list[dict[str, str]] = []
    for group in product.get("addOnGroups") or []:
        gname = group.get("name")
        valid = [c for c in (group.get("choices") or []) if isinstance(c, dict) and c.get("name")]
        if not gname or not valid:
            continue
        non_zero = [c for c in valid if _dec(c.get("modifierPercent", 0)) != 0]
        for ch in non_zero + [c for c in valid if c not in non_zero]:
            combos.append({str(gname): str(ch["name"])})
    return combos


def _file_editing_choices(settings: dict) -> list[str]:
    fe = settings.get("fileEditing") or {}
    if not fe.get("enabled", True):
        return []
    names = [
        str(opt["name"])
        for opt in fe.get("options") or []
        if isinstance(opt, dict) and opt.get("name") in ("upscale", "vectorize")
    ]
    return names or ["upscale", "vectorize"]


def sample_configurations(
    catalog: dict,
    count: int = DEFAULT_AUDIT_COUNT,
    seed: int = DEFAULT_AUDIT_SEED,
) -> list[LineChoices]:
    """Construieste determinist `count` configuratii care acopera catalogul si toate optiunile."""
    if count < 1:
        raise ValueError("count trebuie sa fie cel putin 1")
    products = [p for p in (catalog.get("products") or []) if isinstance(p, dict) and p.get("id")]
    if not products:
        raise ValueError("catalogul nu contine niciun produs")

    settings = catalog.get("settings") or {}
    urgency_cfg = settings.get("urgency") or {}
    urgency_max_qty: int | None = (
        int(urgency_cfg["maxQuantity"]) if urgency_cfg.get("maxQuantity") is not None else None
    )
    editing_modes = _file_editing_choices(settings)
    rng = random.Random(seed)

    selected: list[LineChoices] = []
    seen_keys: set[str] = set()

    def add(choice: LineChoices) -> bool:
        key = _canonical_request_key(choices_to_body(choice))
        if key in seen_keys:
            return False
        seen_keys.add(key)
        selected.append(choice)
        return True

    def make_base(
        product: dict,
        *,
        mat_idx: int = 0,
        shape_idx: int = 0,
        size: tuple[Decimal, Decimal] | None = None,
        quantity: int | None = None,
        **overrides: Any,
    ) -> LineChoices:
        materials = _material_names(product)
        shapes = [str(s) for s in (product.get("shapes") or ["circle"])]
        shape = shapes[shape_idx % len(shapes)]
        mat = materials[mat_idx % len(materials)]
        w, h = size if size is not None else _preset_sizes(product, shape)[0]
        q_info = product.get("quantity") or {}
        qty = quantity if quantity is not None else int(q_info.get("default") or q_info.get("min") or 100)
        return LineChoices(
            product_id=str(product["id"]),
            material_name=mat,
            shape=shape,
            width_cm=w,
            height_cm=h,
            quantity=qty,
            **overrides,
        )

    # 1. Fiecare kind si fiecare produs din catalog, plus toate materialele (inclusiv primele 3+).
    by_kind: dict[str, list[dict]] = {}
    for prod in products:
        by_kind.setdefault(str(prod.get("kind") or "default"), []).append(prod)
    for kind in sorted(by_kind):
        for prod in by_kind[kind]:
            tiers = _tier_quantities(prod)
            add(make_base(prod, mat_idx=0, shape_idx=0, quantity=tiers[0]))

    for prod in products:
        materials = _material_names(prod)
        shapes = [str(s) for s in (prod.get("shapes") or ["circle"])]
        tiers = _tier_quantities(prod)
        for m_idx in range(len(materials)):
            s_idx = m_idx % len(shapes)
            presets = _preset_sizes(prod, shapes[s_idx])
            sz = presets[m_idx % len(presets)]
            qty = tiers[m_idx % len(tiers)]
            add(make_base(prod, mat_idx=m_idx, shape_idx=s_idx, size=sz, quantity=qty))

    # 2. Dimensiuni custom: minim exact, maxim exact si o dimensiune intermediara zecimala.
    custom_products = [p for p in products if (p.get("customSize") or {}).get("enabled")]
    for prod in custom_products:
        custom = prod["customSize"]
        min_cm, max_cm = _dec(custom["minCm"]), _dec(custom["maxCm"])
        tiers = _tier_quantities(prod)
        for cand in _custom_size_candidates(prod, str((prod.get("shapes") or ["circle"])[0]))[:3]:
            add(make_base(prod, mat_idx=0, shape_idx=0, size=cand, quantity=tiers[0]))

    # 3. Cantitatea minima si cantitatea maxima din catalog.
    for prod in products:
        q_min_val = int((prod.get("quantity") or {}).get("min", 25))
        add(make_base(prod, mat_idx=0, shape_idx=0, quantity=q_min_val))
    max_prod = custom_products[0] if custom_products else products[0]
    q_max_val = int((max_prod.get("quantity") or {}).get("max", 10000))
    add(make_base(max_prod, mat_idx=0, shape_idx=0, quantity=q_max_val))

    # 4. Cel putin 5 cantitati pe treapta si 5 cantitati intre trepte.
    for prod in products:
        for idx, t_qty in enumerate(_tier_quantities(prod)[:3]):
            presets = _preset_sizes(prod, str((prod.get("shapes") or ["circle"])[0]))
            add(make_base(prod, mat_idx=idx % min(3, len(_material_names(prod))), size=presets[idx % len(presets)], quantity=t_qty))

    between_added = 0
    for prod in products:
        for idx, b_qty in enumerate(_between_tier_quantities(prod)):
            shapes = [str(s) for s in (prod.get("shapes") or ["circle"])]
            s_idx = idx % len(shapes)
            presets = _preset_sizes(prod, shapes[s_idx])
            if add(make_base(prod, mat_idx=idx % min(3, len(_material_names(prod))), shape_idx=s_idx, size=presets[idx % len(presets)], quantity=b_qty)):
                between_added += 1
            if between_added >= 5:
                break
        if between_added >= 5:
            break

    # 5. Fiecare optiune permisa de catalog activata in cel putin 3 configuratii.
    def add_option_cases(predicate: Callable[[dict], bool], builder: Callable[[dict, int], dict[str, Any]], target: int = 3) -> None:
        eligible = [p for p in products if predicate(p)]
        if not eligible:
            return
        made = 0
        attempt = 0
        while made < target and attempt < 30:
            prod = eligible[attempt % len(eligible)]
            shapes = [str(s) for s in (prod.get("shapes") or ["circle"])]
            s_idx = attempt % len(shapes)
            presets = _preset_sizes(prod, shapes[s_idx])
            tiers = _tier_quantities(prod)
            mat_pool = min(3, len(_material_names(prod)))
            extra = builder(prod, attempt)
            qty = extra.pop("quantity", tiers[attempt % len(tiers)])
            cand = make_base(
                prod,
                mat_idx=attempt % max(1, mat_pool),
                shape_idx=s_idx,
                size=presets[(attempt // max(1, len(shapes))) % len(presets)],
                quantity=qty,
                **extra,
            )
            if add(cand):
                made += 1
            attempt += 1

    if (settings.get("adhesive") or {}).get("enabled", True):
        add_option_cases(lambda p: bool((p.get("options") or {}).get("adhesive")), lambda _p, _i: {"adhesive": "strong"})
    if (settings.get("whitePrint") or {}).get("enabled", True):
        add_option_cases(lambda p: bool((p.get("options") or {}).get("whitePrint")), lambda _p, _i: {"white_print": True})
    if (settings.get("doubleCut") or {}).get("enabled", True):
        add_option_cases(lambda p: bool((p.get("options") or {}).get("cut")), lambda _p, _i: {"cut": "double"})
    if (settings.get("backCut") or {}).get("enabled", True):
        add_option_cases(lambda p: bool((p.get("options") or {}).get("cut")), lambda _p, _i: {"cut": "back"})
    if urgency_cfg.get("enabled", True):
        def _urgent_builder(prod: dict, idx: int) -> dict[str, Any]:
            tiers = [q for q in _tier_quantities(prod) if urgency_max_qty is None or q <= urgency_max_qty]
            q_min = int((prod.get("quantity") or {}).get("min", 25))
            safe_q = tiers[idx % len(tiers)] if tiers else min(q_min, urgency_max_qty or q_min)
            return {"urgent": True, "quantity": safe_q}

        add_option_cases(lambda p: bool((p.get("options") or {}).get("urgency")), _urgent_builder)
    if editing_modes:
        add_option_cases(
            lambda p: bool((p.get("options") or {}).get("fileEditing")),
            lambda _p, i: {"file_editing": editing_modes[i % len(editing_modes)]},
            target=max(3, len(editing_modes) + 1),
        )
    add_option_cases(
        lambda p: bool(_addon_choices(p)),
        lambda p, i: {"add_ons": _addon_choices(p)[i % len(_addon_choices(p))]},
    )

    # 6. Completare determinista pana la `count` cu combinatii variate din catalog.
    attempts = 0
    while len(selected) < count and attempts < count * 100:
        attempts += 1
        prod = products[rng.randrange(len(products))]
        materials = _material_names(prod)
        mat_pool = materials[:-1] if len(materials) > 3 and rng.random() < 0.85 else materials
        mat = mat_pool[rng.randrange(len(mat_pool))]
        shapes = [str(s) for s in (prod.get("shapes") or ["circle"])]
        shape = shapes[rng.randrange(len(shapes))]
        custom_cands = _custom_size_candidates(prod, shape)
        presets = _preset_sizes(prod, shape)
        w, h = (
            custom_cands[rng.randrange(len(custom_cands))]
            if custom_cands and rng.random() < 0.35
            else presets[rng.randrange(len(presets))]
        )
        tiers = _tier_quantities(prod)
        betweens = _between_tier_quantities(prod)
        qty = betweens[rng.randrange(len(betweens))] if betweens and rng.random() < 0.45 else tiers[rng.randrange(len(tiers))]

        opts = prod.get("options") or {}
        adhesive: Literal["standard", "strong"] = (
            "strong" if opts.get("adhesive") and rng.random() < 0.25 else "standard"
        )
        white_print = bool(opts.get("whitePrint") and rng.random() < 0.2)
        cut: Literal["none", "double", "back"] = "none"
        if opts.get("cut") and rng.random() < 0.25:
            cut = "double" if rng.random() < 0.5 else "back"
        can_urgent = bool(opts.get("urgency")) and (urgency_max_qty is None or qty <= urgency_max_qty)
        urgent = bool(can_urgent and rng.random() < 0.2)
        file_editing: Literal["none", "upscale", "vectorize"] = "none"
        if opts.get("fileEditing") and editing_modes and rng.random() < 0.25:
            file_editing = editing_modes[rng.randrange(len(editing_modes))]  # type: ignore[assignment]
        addons_list = _addon_choices(prod)
        add_ons = addons_list[rng.randrange(len(addons_list))] if addons_list and rng.random() < 0.35 else {}

        add(
            LineChoices(
                product_id=str(prod["id"]),
                material_name=mat,
                shape=shape,
                width_cm=w,
                height_cm=h,
                quantity=qty,
                add_ons=add_ons,
                adhesive=adhesive,
                white_print=white_print,
                cut=cut,
                urgent=urgent,
                file_editing=file_editing,
            )
        )

    if len(selected) > count:
        result = selected[:count]
    else:
        result = list(selected)
        while len(result) < count:
            result.append(selected[len(result) % len(selected)])
    rng.shuffle(result)
    return result


# ---------- transport cu limitare de ritm si captare bruta ----------

class RateLimitedHttp:
    """Invelis peste httpx.Client care garanteaza cel mult 1 cerere pe secunda."""

    def __init__(
        self,
        http: Any,
        *,
        min_interval_seconds: float = 1.0,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._http = http
        self._min_interval = min_interval_seconds
        self._clock = clock
        self._sleep = sleep
        self._last_request_at: float | None = None
        self.request_times: list[float] = []

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        now = self._clock()
        if self._last_request_at is not None and self._min_interval > 0:
            elapsed = now - self._last_request_at
            if elapsed < self._min_interval:
                self._sleep(self._min_interval - elapsed)
                now = self._clock()
        self._last_request_at = now
        self.request_times.append(now)
        send = self._http.request if hasattr(self._http, "request") else self._http
        return send(method, url, **kwargs)


class _RecordingHttp:
    """Capteaza raspunsul brut (status_code, text) pentru fiecare corp POST /api/sync/line."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self.catalog_text: str | None = None
        self.line_responses: dict[str, tuple[int, str]] = {}

    def request(self, method: str, url: str, **kwargs: Any) -> Any:
        send = self._inner.request if hasattr(self._inner, "request") else self._inner
        response = send(method, url, **kwargs)
        if method == "GET" and url.endswith(CONFIG_PATH) and response.status_code == 200:
            self.catalog_text = response.text
        elif method == "POST" and url.endswith(LINE_PATH) and kwargs.get("content") is not None:
            content = kwargs["content"]
            body = json.loads(content.decode("utf-8") if isinstance(content, (bytes, bytearray)) else str(content))
            self.line_responses[_canonical_request_key(body)] = (response.status_code, response.text)
        return response


# ---------- verificarea paritatii ----------

def _contains_float(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return True
    if isinstance(value, dict):
        return any(_contains_float(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return any(_contains_float(v) for v in value)
    return False


def _product_title(catalog: dict, product_id: str) -> str:
    product = find_product(catalog, product_id)
    return str((product or {}).get("title") or "Produs")


def _check_shopify_draft_override(quote: PriceQuote, product_title: str) -> tuple[Decimal | None, Decimal]:
    """Construieste Draft Order prin ShopifyCheckout (transport fals) si extrage priceOverride."""
    captured_inputs: list[dict[str, Any]] = []
    expected_cent = quote.total.quantize(CENT, rounding=ROUND_HALF_UP)

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content.decode("utf-8"))
        query = payload.get("query") or ""
        variables = payload.get("variables") or {}
        if "EcQuoteProductVariants" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "product": {
                            "id": variables["id"],
                            "title": product_title,
                            "variants": {
                                "nodes": [
                                    {
                                        "id": "gid://shopify/ProductVariant/9001",
                                        "selectedOptions": [{"name": "Title", "value": "Default Title"}],
                                    }
                                ]
                            },
                        }
                    }
                },
            )
        else:
            captured_inputs.append(variables["input"])
            return httpx.Response(
                200,
                json={
                    "data": {
                        "draftOrderCreate": {
                            "draftOrder": {
                                "id": "gid://shopify/DraftOrder/7001",
                                "name": "#D7001",
                                "invoiceUrl": "https://shop.example.invalid/7001/invoices/abc",
                                "status": "OPEN",
                                "taxesIncluded": True,
                                "totalPriceSet": {
                                    "shopMoney": {"amount": shopify_money(quote.total), "currencyCode": CURRENCY}
                                },
                            },
                            "userErrors": [],
                        }
                    }
                },
            )

    http = httpx.Client(transport=httpx.MockTransport(handler))
    checkout_port = ShopifyCheckout("shop.example.invalid", "shpat_fake_audit_token", http=http)
    created = checkout_port.create_checkout(quote, AUDIT_CONTACT, None, AUDIT_VALID_UNTIL)
    line_item = captured_inputs[0]["lineItems"][0]
    override = line_item.get("priceOverride")
    override_amount = Decimal(str(override["amount"])) if isinstance(override, dict) and "amount" in override else None
    return override_amount, created.total if override_amount is not None else expected_cent


def verify_parity(
    client_factory: Callable[[Any], CalculatorClient],
    http: Any,
    *,
    configurations: list[LineChoices] | None = None,
    count: int = DEFAULT_AUDIT_COUNT,
    seed: int = DEFAULT_AUDIT_SEED,
    vat_percent: Decimal | None = None,
    upsell_tier_count: int = DEFAULT_UPSELL_TIERS,
    recorded_expectations: dict[str, dict[str, Any]] | None = None,
    case_ids: list[str] | None = None,
    mode: Literal["live", "replay", "verify"] = "verify",
    now: datetime = AUDIT_NOW,
) -> ParityAuditReport:
    """Ruleaza configuratiile prin CalculatorClient si compara sumele pe fiecare suprafata."""
    recorder = _RecordingHttp(http)
    vat = vat_percent if vat_percent is not None else load_vat_percent()
    client = client_factory(recorder)
    catalog = client.catalog()
    chosen = configurations if configurations is not None else sample_configurations(catalog, count=count, seed=seed)

    results: list[CaseAuditResult] = []
    priced_count = 0
    unpriced_count = 0
    unpriced_by_reason: dict[str, int] = {}

    for index, choices in enumerate(chosen, start=1):
        cid = case_ids[index - 1] if case_ids and index - 1 < len(case_ids) else f"case-{index:02d}"
        summary = describe_configuration(choices)
        mismatches: list[AuditMismatch] = []

        def fail(field_name: str, expected_val: Any, found_val: Any) -> None:
            mismatches.append(
                AuditMismatch(
                    case_id=cid,
                    config_summary=summary,
                    field=field_name,
                    expected=str(expected_val),
                    found=str(found_val),
                )
            )

        body = choices_to_body(choices)
        req_key = _canonical_request_key(body)
        quote_or_unpriced = client.get_price(choices)
        raw_entry = recorder.line_responses.get(req_key)
        if raw_entry is None:
            fail("http_response", "raspuns inregistrat", "lipsa")
            results.append(
                CaseAuditResult(case_id=cid, choices=choices, config_summary=summary, status="unpriced", consistent=False, mismatches=tuple(mismatches))
            )
            continue

        raw_status, raw_text = raw_entry
        raw_payload = json.loads(raw_text, parse_float=Decimal)
        recorded = (recorded_expectations or {}).get(cid)

        # Verificarea treptelor superioare (AC4) pentru fiecare configuratie.
        tiers = client.get_price_tiers(choices, upsell_tier_count)
        product = find_product(catalog, choices.product_id) or {}
        q_info = product.get("quantity") or {}
        q_max = int(q_info["max"]) if q_info.get("max") is not None else None
        visible_tiers = {
            int(t["quantity"])
            for t in (q_info.get("tiers") or [])
            if int(t["quantity"]) > choices.quantity and (q_max is None or int(t["quantity"]) <= q_max)
        }
        for tier in tiers:
            if tier.quantity <= choices.quantity or tier.quantity not in visible_tiers:
                fail(f"tier[{tier.quantity}].quantity", f"in {sorted(visible_tiers)}", tier.quantity)
            direct = client.get_price(choices.model_copy(update={"quantity": tier.quantity}))
            if not isinstance(direct, PriceQuote):
                fail(f"tier[{tier.quantity}].status", "PriceQuote", type(direct).__name__)
            elif (tier.total, tier.total_ex_vat, tier.unit_price) != (direct.total, direct.total_ex_vat, direct.unit_price):
                fail(
                    f"tier[{tier.quantity}].amounts",
                    (direct.total, direct.total_ex_vat, direct.unit_price),
                    (tier.total, tier.total_ex_vat, tier.unit_price),
                )

        if raw_status == 422:
            raw_reason = str(raw_payload.get("reason") or "")
            if not isinstance(quote_or_unpriced, Unpriced):
                fail("status", f"Unpriced({raw_reason})", type(quote_or_unpriced).__name__)
                reason_out = raw_reason
            else:
                reason_out = quote_or_unpriced.reason
                if quote_or_unpriced.reason != raw_reason:
                    fail("reason", raw_reason, quote_or_unpriced.reason)
            if recorded is not None and (recorded.get("status") != "unpriced" or recorded.get("reason") != reason_out):
                fail("reason", recorded.get("reason") or recorded.get("status"), reason_out)
            unpriced_count += 1
            unpriced_by_reason[reason_out] = unpriced_by_reason.get(reason_out, 0) + 1
            results.append(
                CaseAuditResult(
                    case_id=cid,
                    choices=choices,
                    config_summary=summary,
                    status="unpriced",
                    consistent=not mismatches,
                    unpriced_reason=reason_out,
                    tier_quantities=tuple(t.quantity for t in tiers),
                    mismatches=tuple(mismatches),
                )
            )
            continue

        if not isinstance(quote_or_unpriced, PriceQuote):
            fail("status", "PriceQuote", type(quote_or_unpriced).__name__)
            results.append(
                CaseAuditResult(case_id=cid, choices=choices, config_summary=summary, status="priced", consistent=False, mismatches=tuple(mismatches))
            )
            continue

        quote = quote_or_unpriced
        priced_count += 1

        # AC8: niciun float in campurile de pret sau breakdown.
        if _contains_float((quote.total, quote.total_ex_vat, quote.unit_price, quote.discount_percent, quote.breakdown)):
            fail("float_leak", "Decimal", "float")

        # AC2 + AC6: total exact din JSON brut si din asteptarea inregistrata.
        raw_total = _dec(raw_payload["total"])
        if recorded is not None:
            if recorded.get("status") != "priced":
                fail("recorded.status", recorded.get("status"), "priced")
            elif "total" in recorded and _dec(recorded["total"]) != quote.total:
                fail("total", recorded["total"], quote.total)
        if quote.total != raw_total:
            fail("total", raw_total, quote.total)

        expected_ex_vat = ex_vat(quote.total, vat)
        if quote.total_ex_vat != expected_ex_vat:
            fail("total_ex_vat", expected_ex_vat, quote.total_ex_vat)

        reconstructed = (quote.total_ex_vat * (Decimal(1) + vat / Decimal(100))).quantize(CENT, rounding=ROUND_HALF_UP)
        if abs(reconstructed - quote.total) > CENT:
            fail("total_ex_vat_plus_vat", quote.total, reconstructed)

        raw_unit = _dec(raw_payload["unitPrice"])
        if quote.unit_price != raw_unit:
            fail("unit_price", raw_unit, quote.unit_price)

        calc_prop = next((p.value for p in quote.properties if p.name == "_calculator_price"), None)
        try:
            prop_dec = Decimal(calc_prop) if calc_prop is not None else None
        except InvalidOperation:
            prop_dec = None
        if prop_dec != quote.total:
            fail("properties._calculator_price", calc_prop if calc_prop is not None else "missing", quote.total)

        # AC3: textul ofertei, imaginea de oferta si ShopifyCheckout.priceOverride.
        title = _product_title(catalog, choices.product_id)
        threshold = max(Decimal("100000"), quote.total_ex_vat + Decimal("10000"))
        lines = offer_module.build_lines(quote, tiers, threshold, language="ro")
        main_line = next(line for line in lines if line.highlighted)
        if (main_line.total, main_line.total_ex_vat, main_line.unit_price) != (
            quote.total,
            quote.total_ex_vat,
            quote.unit_price,
        ):
            fail("offer_line.amounts", (quote.total, quote.total_ex_vat, quote.unit_price), (main_line.total, main_line.total_ex_vat, main_line.unit_price))

        offer_txt = offer_module.build_offer_text(
            quote, lines, title, AUDIT_PRODUCTION_TERM, AUDIT_VALID_UNTIL, None, language="ro"
        )
        main_txt_amounts = [a for a in money_mentions(offer_txt.splitlines()[1]) if a is not None]
        if len(main_txt_amounts) < 2 or main_txt_amounts[0] != quote.total_ex_vat or abs(main_txt_amounts[1] - quote.total) > HALF_CENT:
            fail("offer_text.amounts", (quote.total_ex_vat, quote.total), main_txt_amounts)

        image_content = build_content(lines, AUDIT_PRODUCTION_TERM, AUDIT_VALID_UNTIL)
        main_row = next(r for r in image_content.rows if r.highlighted)
        expected_cent_total = quote.total.quantize(CENT, rounding=ROUND_HALF_UP)
        img_ex_vat = parse_amount(main_row.total_ex_vat.removesuffix(" lei").strip())
        img_total = parse_amount(main_row.total.removesuffix(" lei").strip())
        if img_ex_vat != quote.total_ex_vat or img_total != expected_cent_total:
            fail("offer_image.amounts", (quote.total_ex_vat, expected_cent_total), (img_ex_vat, img_total))

        override_amount, checkout_total = _check_shopify_draft_override(quote, title)
        if override_amount != expected_cent_total or checkout_total != expected_cent_total:
            fail("shopify.priceOverride", expected_cent_total, (override_amount, checkout_total))

        results.append(
            CaseAuditResult(
                case_id=cid,
                choices=choices,
                config_summary=summary,
                status="priced",
                consistent=not mismatches,
                total=quote.total,
                total_ex_vat=quote.total_ex_vat,
                unit_price=quote.unit_price,
                tier_quantities=tuple(t.quantity for t in tiers),
                mismatches=tuple(mismatches),
            )
        )

    local_now = now.replace(tzinfo=TZ) if now.tzinfo is None else now.astimezone(TZ)
    consistent_count = sum(1 for r in results if r.consistent)
    return ParityAuditReport(
        generated_at=local_now,
        mode=mode,
        total_count=len(results),
        consistent_count=consistent_count,
        priced_count=priced_count,
        unpriced_count=unpriced_count,
        unpriced_by_reason=dict(sorted(unpriced_by_reason.items())),
        cases=tuple(results),
    )


# ---------- inregistrare si rulare din fixture-uri fara retea ----------

def sanitize_catalog(catalog: dict) -> dict:
    """Inlocuieste orice URL extern din catalog cu un placeholder fara date reale."""
    cleaned = copy.deepcopy(catalog)
    settings = cleaned.get("settings")
    if isinstance(settings, dict) and "uploadPublicBaseUrl" in settings:
        settings["uploadPublicBaseUrl"] = PLACEHOLDER_CDN_URL
    return cleaned


def record_parity_fixtures(
    out_dir: Path | str,
    client_factory: Callable[[Any], CalculatorClient],
    http: Any,
    *,
    count: int = DEFAULT_AUDIT_COUNT,
    seed: int = DEFAULT_AUDIT_SEED,
    vat_percent: Decimal | None = None,
    upsell_tier_count: int = DEFAULT_UPSELL_TIERS,
    forbidden_secrets: tuple[str, ...] = (),
) -> ParityAuditReport:
    """Ruleaza auditul si scrie fixture-urile curate (fara secrete, doar host placeholder)."""
    target = Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    recorder = _RecordingHttp(http)
    vat = vat_percent if vat_percent is not None else load_vat_percent()

    report = verify_parity(
        client_factory,
        recorder,
        count=count,
        seed=seed,
        vat_percent=vat,
        upsell_tier_count=upsell_tier_count,
        mode="live",
    )
    if recorder.catalog_text is None:
        raise RuntimeError("Catalogul nu a fost inregistrat in timpul auditului")
    raw_catalog = json.loads(recorder.catalog_text, parse_float=Decimal)
    clean_catalog = sanitize_catalog(raw_catalog)

    def _write_checked(path: Path, text: str) -> None:
        for secret in forbidden_secrets:
            if secret and secret in text:
                raise RuntimeError("Secret detectat in continutul pregatit pentru scriere; oprire imediata")
        path.write_text(text + "\n", encoding="utf-8")

    _write_checked(
        target / "catalog.json",
        dumps_exact_json(
            {
                "url": PLACEHOLDER_BASE_URL + CONFIG_PATH,
                "seed": seed,
                "count": count,
                "catalog": clean_catalog,
            },
            indent=2,
        ),
    )

    for existing in target.glob("case-*.json"):
        existing.unlink()

    for case in report.cases:
        req_body = choices_to_body(case.choices)
        status_code, raw_text = recorder.line_responses[_canonical_request_key(req_body)]
        parsed_resp = json.loads(raw_text, parse_float=Decimal)

        product = find_product(clean_catalog, case.choices.product_id) or {}
        q_info = product.get("quantity") or {}
        q_max = int(q_info["max"]) if q_info.get("max") is not None else None
        cand_tiers = sorted(
            {
                int(t["quantity"])
                for t in (q_info.get("tiers") or [])
                if int(t["quantity"]) > case.choices.quantity and (q_max is None or int(t["quantity"]) <= q_max)
            }
        )[:upsell_tier_count]

        tier_entries: list[dict[str, Any]] = []
        for t_qty in cand_tiers:
            t_req = choices_to_body(case.choices.model_copy(update={"quantity": t_qty}))
            t_key = _canonical_request_key(t_req)
            if t_key in recorder.line_responses:
                t_status, t_raw = recorder.line_responses[t_key]
                tier_entries.append(
                    {
                        "quantity": t_qty,
                        "url": PLACEHOLDER_BASE_URL + LINE_PATH,
                        "request": t_req,
                        "status_code": t_status,
                        "response": json.loads(t_raw, parse_float=Decimal),
                    }
                )

        if case.status == "priced":
            recorded_meta: dict[str, Any] = {
                "status": "priced",
                "total": str(case.total),
                "total_ex_vat": str(case.total_ex_vat),
                "unit_price": str(case.unit_price),
            }
        else:
            recorded_meta = {
                "status": "unpriced",
                "reason": case.unpriced_reason or "",
            }

        fixture_doc = {
            "case_id": case.case_id,
            "url": PLACEHOLDER_BASE_URL + LINE_PATH,
            "choices": json.loads(case.choices.model_dump_json(), parse_float=Decimal),
            "request": req_body,
            "status_code": status_code,
            "response": parsed_resp,
            "recorded": recorded_meta,
            "tiers": tier_entries,
        }
        _write_checked(target / f"{case.case_id}.json", dumps_exact_json(fixture_doc, indent=2))

    return report


def replay_parity_fixtures(
    fixture_dir: Path | str,
    *,
    vat_percent: Decimal | None = None,
    upsell_tier_count: int = DEFAULT_UPSELL_TIERS,
    client_builder: Callable[[str, str, Any, Decimal], CalculatorClient] | None = None,
    now: datetime = AUDIT_NOW,
) -> ParityAuditReport:
    """Ruleaza auditul complet din fixture-urile salvate pe disc, fara niciun apel de retea."""
    folder = Path(fixture_dir)
    catalog_file = folder / "catalog.json"
    if not catalog_file.is_file():
        raise FileNotFoundError(f"Lipseste catalog.json in {folder}")
    catalog_bundle = json.loads(catalog_file.read_text(encoding="utf-8"), parse_float=Decimal)
    catalog_payload = catalog_bundle["catalog"] if "catalog" in catalog_bundle else catalog_bundle
    catalog_text = dumps_exact_json(catalog_payload)

    case_files = sorted(folder.glob("case-*.json"))
    if not case_files:
        raise FileNotFoundError(f"Nu exista fisiere case-*.json in {folder}")

    line_map: dict[str, tuple[int, str]] = {}
    configurations: list[LineChoices] = []
    case_ids: list[str] = []
    recorded_expectations: dict[str, dict[str, Any]] = {}

    for path in case_files:
        doc = json.loads(path.read_text(encoding="utf-8"), parse_float=Decimal)
        cid = str(doc.get("case_id") or path.stem)
        case_ids.append(cid)
        choices = LineChoices.model_validate(doc["choices"])
        configurations.append(choices)
        req_key = _canonical_request_key(doc["request"])
        line_map[req_key] = (int(doc["status_code"]), dumps_exact_json(doc["response"]))
        if isinstance(doc.get("recorded"), dict):
            recorded_expectations[cid] = dict(doc["recorded"])
        for t_entry in doc.get("tiers") or []:
            t_key = _canonical_request_key(t_entry["request"])
            line_map[t_key] = (int(t_entry["status_code"]), dumps_exact_json(t_entry["response"]))

    def mock_handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == CONFIG_PATH:
            return httpx.Response(200, text=catalog_text, headers={"Content-Type": "application/json"})
        if request.method == "POST" and request.url.path == LINE_PATH:
            req_body = json.loads(request.content.decode("utf-8"))
            found = line_map.get(_canonical_request_key(req_body))
            if found is None:
                return httpx.Response(404, json={"error": "fixture_missing"})
            st, txt = found
            return httpx.Response(st, text=txt, headers={"Content-Type": "application/json"})
        return httpx.Response(404, json={"error": "not_found"})

    vat = vat_percent if vat_percent is not None else load_vat_percent()
    http = httpx.Client(transport=httpx.MockTransport(mock_handler))

    def factory(wrapped_http: Any) -> CalculatorClient:
        if client_builder is not None:
            return client_builder(PLACEHOLDER_BASE_URL, PLACEHOLDER_SECRET, wrapped_http, vat)
        return CalculatorClient(PLACEHOLDER_BASE_URL, PLACEHOLDER_SECRET, http=wrapped_http, vat_percent=vat)

    return verify_parity(
        factory,
        http,
        configurations=configurations,
        vat_percent=vat,
        upsell_tier_count=upsell_tier_count,
        recorded_expectations=recorded_expectations,
        case_ids=case_ids,
        mode="replay",
        now=now,
    )


# ---------- rapoarte JSON si Markdown (fara em-dash, fara emoji, fara secrete) ----------

def render_report_json(report: ParityAuditReport) -> str:
    data = {
        "generated_at": report.generated_at.isoformat(),
        "mode": report.mode,
        "ok": report.ok,
        "summary": f"{report.consistent_count}/{report.total_count} identice",
        "total_count": report.total_count,
        "consistent_count": report.consistent_count,
        "priced_count": report.priced_count,
        "unpriced_count": report.unpriced_count,
        "unpriced_by_reason": report.unpriced_by_reason,
        "mismatches": [
            {
                "case_id": m.case_id,
                "configuration": m.config_summary,
                "field": m.field,
                "expected": m.expected,
                "found": m.found,
            }
            for m in report.mismatches
        ],
        "cases": [
            {
                "case_id": c.case_id,
                "configuration": c.config_summary,
                "status": c.status,
                "consistent": c.consistent,
                "total": str(c.total) if c.total is not None else None,
                "total_ex_vat": str(c.total_ex_vat) if c.total_ex_vat is not None else None,
                "unit_price": str(c.unit_price) if c.unit_price is not None else None,
                "unpriced_reason": c.unpriced_reason,
                "tier_quantities": list(c.tier_quantities),
            }
            for c in report.cases
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def render_report_markdown(report: ParityAuditReport) -> str:
    lines = [
        "# Raport audit paritate preturi",
        "",
        f"- Data: {report.generated_at.strftime('%Y-%m-%d %H:%M %Z')}",
        f"- Mod: `{report.mode}`",
        f"- Rezultat: **{report.consistent_count}/{report.total_count} identice**",
        f"- Configuratii cu pret (200): {report.priced_count}",
        f"- Configuratii nepretuite (422): {report.unpriced_count}",
    ]
    if report.unpriced_by_reason:
        reasons = ", ".join(f"`{k}`: {v}" for k, v in report.unpriced_by_reason.items())
        lines.append(f"- Motive 422: {reasons}")
    lines.append("")

    if report.mismatches:
        lines.append("## Diferente gasite")
        lines.append("")
        for m in report.mismatches:
            lines.append(
                f"- `{m.case_id}` ({m.config_summary}) - camp `{m.field}`: "
                f"asteptat `{m.expected}`, gasit `{m.found}`"
            )
        lines.append("")

    lines.extend(
        [
            "## Configuratii verificate",
            "",
            "| Caz | Status | Total cu TVA | Total fara TVA | Motiv 422 | Paritate |",
            "| --- | --- | --- | --- | --- | --- |",
        ]
    )
    for c in report.cases:
        tot = str(c.total) if c.total is not None else "-"
        ex = str(c.total_ex_vat) if c.total_ex_vat is not None else "-"
        reason = c.unpriced_reason or "-"
        verdict = "OK" if c.consistent else "DIFERENTA"
        lines.append(f"| `{c.case_id}` | {c.status} | {tot} | {ex} | {reason} | {verdict} |")
    lines.append("")
    return "\n".join(lines)
