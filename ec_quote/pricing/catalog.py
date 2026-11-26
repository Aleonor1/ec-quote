"""Ajutoare peste catalogul calculatorului: rezumat pentru prompt si rezolvarea alegerilor.

Modelul nu inventeaza id-uri sau nume: primeste rezumatul, iar ce spune clientul
trece prin resolve_choices, care intoarce fie LineChoices cu numele exacte din
catalog, fie lista de probleme cu optiunile valide. Verificarile de aici sunt
doar de ajutor; calculatorul ramane autoritatea (raspunsul 422).
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from typing import Any

from pydantic import BaseModel, Field

from ec_quote.contracts import LineChoices
from ec_quote.pricing.client import find_product

# Cum numeste clientul formele (fara diacritice, litere mici) -> id-ul din calculator.
SHAPE_ALIASES: dict[str, tuple[str, ...]] = {
    "circle": ("cerc", "rotund", "rotunda", "rotunde", "circular", "circulara", "round"),
    "square": ("patrat", "patrata", "patrate"),
    "rectangle": ("dreptunghi", "dreptunghiular", "dreptunghiulara", "dreptunghiulare", "rectangular"),
    "oval": ("ovala", "ovale", "elipsa"),
    "custom": ("contur", "pe contur", "forma libera", "personalizat", "personalizata", "die cut", "diecut", "orice forma"),
    "heart": ("inima", "inimioara"),
}
SHAPE_LABELS_RO = {
    "circle": "cerc",
    "square": "patrat",
    "rectangle": "dreptunghi",
    "oval": "oval",
    "custom": "pe contur",
    "heart": "inima",
}
OPTION_KEYS = ("adhesive", "whitePrint", "cut", "urgency", "fileEditing", "instructions")
MAX_SIZES_IN_SUMMARY = 10


class ChoiceProblem(BaseModel):
    """O problema la rezolvarea alegerilor. `code` e stabil (aceleasi coduri ca 422-urile calculatorului unde exista)."""

    code: str
    field: str
    given: str | None = None
    valid: list[str] = Field(default_factory=list)
    details: dict = Field(default_factory=dict)


def normalize(text: Any) -> str:
    """Litere mici, fara diacritice, doar litere si cifre separate de un spatiu."""
    decomposed = unicodedata.normalize("NFD", str(text or ""))
    plain = "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return re.sub(r"[^a-z0-9]+", " ", plain).strip()


def _dec(value: Any) -> Decimal | None:
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _num(value: Any) -> str:
    number = _dec(value)
    if number is None:
        return str(value)
    text = format(number.normalize(), "f")
    return text


def match_name(given: str | None, options: list[str]) -> tuple[str | None, list[str]]:
    """Potriveste tolerant un nume. Intoarce (numele exact, []) sau (None, candidatii ambigui)."""
    wanted = normalize(given)
    if not wanted:
        return None, []
    exact = [o for o in options if normalize(o) == wanted]
    if exact:
        return exact[0], []
    wanted_tokens = set(wanted.split())
    partial = [
        o
        for o in options
        if wanted in normalize(o) or normalize(o) in wanted or wanted_tokens <= set(normalize(o).split())
    ]
    if len(partial) == 1:
        return partial[0], []
    return None, partial


def match_shape(given: str | None, shapes: list[str]) -> str | None:
    """Potriveste forma dupa id sau dupa numele romanesc (rotund -> circle)."""
    wanted = normalize(given)
    if not wanted:
        return None
    for shape in shapes:
        if normalize(shape) == wanted or wanted in SHAPE_ALIASES.get(shape, ()):
            return shape
    hits = [s for s in shapes if any(alias in wanted.split() or alias == wanted for alias in (s, *SHAPE_ALIASES.get(s, ())))]
    return hits[0] if len(hits) == 1 else None


def find_products(catalog: dict, query: str, limit: int = 5) -> list[dict]:
    """Produsele care se potrivesc cu textul (titlu, handle, id), cele mai bune primele. Text gol: toate."""
    products = list(catalog.get("products") or [])
    wanted = normalize(query)
    if not wanted:
        return products[:limit]
    tokens = wanted.split()
    scored: list[tuple[int, int, dict]] = []
    for index, product in enumerate(products):
        if product.get("id") == query.strip():
            return [product]
        title = normalize(product.get("title"))
        words = set(title.split()) | set(normalize(product.get("handle")).split())
        score = sum(2 for t in tokens if t in words)
        # prefix comun: "stickere" se potriveste cu "sticker", "etichete" cu "eticheta"
        score += sum(1 for t in tokens if t not in words and len(t) >= 4 and any(w[:5] == t[:5] for w in words))
        if wanted == title:
            score += 10
        if score:
            scored.append((-score, index, product))
    return [product for _, _, product in sorted(scored, key=lambda item: item[:2])[:limit]]


# ---------- rezumat pentru prompt ----------

def _sizes_text(product: dict) -> str:
    by_shape = product.get("sizesByShape") or {}

    def labels(sizes: list[dict]) -> str:
        shown = [f"{_num(s.get('widthCm'))}x{_num(s.get('heightCm'))}" for s in sizes[:MAX_SIZES_IN_SUMMARY]]
        return ", ".join(shown) + (", ..." if len(sizes) > MAX_SIZES_IN_SUMMARY else "")

    groups: dict[str, list[str]] = {}
    for shape in product.get("shapes") or []:
        text = labels(by_shape.get(shape) or [])
        if text:
            groups.setdefault(text, []).append(shape)
    if not groups:
        return "-"
    if len(groups) == 1:
        return next(iter(groups))
    return "; ".join(f"{'/'.join(shapes)}: {text}" for text, shapes in groups.items())


def _tiers_text(product: dict) -> str:
    tiers = sorted((product.get("quantity") or {}).get("tiers") or [], key=lambda t: t.get("quantity", 0))
    parts = []
    for tier in tiers:
        discount = _dec(tier.get("discountPercent")) or Decimal(0)
        parts.append(f"{tier.get('quantity')}" + (f" (-{_num(discount)}%)" if discount > 0 else ""))
    return ", ".join(parts) or "-"


def _product_summary(product: dict) -> str:
    quantity = product.get("quantity") or {}
    custom = product.get("customSize") or {}
    custom_text = (
        f"{_num(custom.get('minCm'))}-{_num(custom.get('maxCm'))} cm pe latura" if custom.get("enabled") else "nu"
    )
    options = [key for key in OPTION_KEYS if (product.get("options") or {}).get(key)]
    lines = [
        f"- {product.get('title')} | id: {product.get('id')} | tip: {product.get('kind', '?')}",
        f"  forme: {', '.join(product.get('shapes') or []) or '-'}",
        f"  materiale: {'; '.join(m.get('name', '') for m in product.get('materials') or []) or '-'}",
        f"  marimi presetate (cm): {_sizes_text(product)}",
        f"  marime personalizata: {custom_text}",
        f"  cantitate: min {quantity.get('min')}, max {quantity.get('max')}; trepte: {_tiers_text(product)}",
    ]
    if options:
        lines.append(f"  optiuni: {', '.join(options)}")
    for group in product.get("addOnGroups") or []:
        names = ", ".join(c.get("name", "") for c in group.get("choices") or [])
        if names:
            lines.append(f"  add-on {group.get('name')}: {names}")
    return "\n".join(lines)


def catalog_summary(catalog: dict) -> str:
    """Rezumat compact al catalogului pentru promptul modelului. Fara preturi: acelea vin numai din get_price."""
    products = catalog.get("products") or []
    lines = ["Produse in calculator (foloseste exact id-urile si numele de mai jos):"]
    lines.extend(_product_summary(p) for p in products)
    if not products:
        lines.append("(niciun produs)")
    urgency = (catalog.get("settings") or {}).get("urgency") or {}
    if urgency.get("enabled") and urgency.get("maxQuantity"):
        lines.append(f"Urgenta: cel mult {urgency['maxQuantity']} buc.")
    return "\n".join(lines)


# ---------- rezolvarea alegerilor ----------

def _is_preset(product: dict, shape: str, width: Decimal, height: Decimal) -> bool:
    for size in (product.get("sizesByShape") or {}).get(shape) or []:
        w, h = _dec(size.get("widthCm")), _dec(size.get("heightCm"))
        if (w == width and h == height) or (w == height and h == width):
            return True
    return False


def _size_problem(product: dict, shape: str, width: Decimal, height: Decimal) -> ChoiceProblem | None:
    if _is_preset(product, shape, width, height):
        return None
    custom = product.get("customSize") or {}
    given = f"{_num(width)} x {_num(height)}"
    presets = [s.get("label") or f"{_num(s.get('widthCm'))} x {_num(s.get('heightCm'))}"
               for s in (product.get("sizesByShape") or {}).get(shape) or []]
    if not custom.get("enabled"):
        return ChoiceProblem(code="custom_size_disabled", field="size", given=given, valid=presets)
    minimum, maximum = _dec(custom.get("minCm")), _dec(custom.get("maxCm"))
    if maximum is not None and (width > maximum or height > maximum):
        return ChoiceProblem(code="size_above_maximum", field="size", given=given, details={"maxCm": _num(maximum)})
    if minimum is not None and (width < minimum or height < minimum):
        return ChoiceProblem(code="size_below_minimum", field="size", given=given, details={"minCm": _num(minimum)})
    return None


def _quantity_problem(product: dict, quantity: int) -> ChoiceProblem | None:
    info = product.get("quantity") or {}
    minimum, maximum = info.get("min"), info.get("max")
    if minimum is not None and quantity < minimum:
        return ChoiceProblem(code="quantity_below_minimum", field="quantity", given=str(quantity),
                             details={"minQuantity": minimum})
    if maximum is not None and quantity > maximum:
        return ChoiceProblem(code="quantity_above_maximum", field="quantity", given=str(quantity),
                             details={"maxQuantity": maximum})
    return None


def _option_problems(catalog: dict, product: dict, *, quantity: int, adhesive: str, white_print: bool, cut: str,
                     urgent: bool, file_editing: str, instructions: str) -> list[ChoiceProblem]:
    options = product.get("options") or {}
    settings = catalog.get("settings") or {}
    problems: list[ChoiceProblem] = []

    def unavailable(option: str, given: str) -> None:
        problems.append(ChoiceProblem(code="option_unavailable", field=option, given=given, details={"option": option}))

    if adhesive == "strong" and not options.get("adhesive"):
        unavailable("adhesive", adhesive)
    if white_print and not options.get("whitePrint"):
        unavailable("whitePrint", "true")
    cut_setting = {"double": "doubleCut", "back": "backCut"}.get(cut)
    if cut != "none" and not (options.get("cut") and (settings.get(cut_setting) or {}).get("enabled", True)):
        unavailable("cut", cut)
    if urgent and not options.get("urgency"):
        unavailable("urgency", "true")
    elif urgent:
        maximum = (settings.get("urgency") or {}).get("maxQuantity")
        if maximum is not None and quantity > maximum:
            problems.append(ChoiceProblem(code="urgency_quantity_exceeded", field="urgency", given=str(quantity),
                                          details={"maxQuantity": maximum}))
    if file_editing != "none":
        names = [o.get("name") for o in (settings.get("fileEditing") or {}).get("options") or []]
        if not options.get("fileEditing") or file_editing not in names:
            unavailable("fileEditing", file_editing)
    if instructions.strip() and not options.get("instructions"):
        unavailable("instructions", instructions[:40])
    return problems


def _resolve_add_ons(product: dict, add_ons: dict[str, str]) -> tuple[dict[str, str], list[ChoiceProblem]]:
    groups = {g.get("name"): [c.get("name") for c in g.get("choices") or []]
              for g in product.get("addOnGroups") or [] if g.get("choices")}
    resolved: dict[str, str] = {}
    problems: list[ChoiceProblem] = []
    for group_given, choice_given in add_ons.items():
        group, _ = match_name(group_given, list(groups))
        if group is None:
            problems.append(ChoiceProblem(code="unknown_add_on", field="add_ons", given=group_given,
                                          valid=list(groups), details={"option": group_given}))
            continue
        choice, _ = match_name(choice_given, groups[group])
        if choice is None:
            problems.append(ChoiceProblem(code="unknown_add_on", field="add_ons", given=f"{group}: {choice_given}",
                                          valid=groups[group], details={"option": group}))
            continue
        resolved[group] = choice
    return resolved, problems


def resolve_choices(
    catalog: dict,
    product_id: str,
    material: str | None,
    shape: str | None,
    width_cm: Decimal | int | str,
    height_cm: Decimal | int | str,
    quantity: int,
    *,
    add_ons: dict[str, str] | None = None,
    adhesive: str = "standard",
    white_print: bool = False,
    cut: str = "none",
    urgent: bool = False,
    file_editing: str = "none",
    instructions: str = "",
) -> LineChoices | list[ChoiceProblem]:
    """Alegerile clientului in LineChoices cu numele exacte din catalog, sau lista de probleme.

    Materialul si forma se potrivesc fara majuscule si diacritice; lipsa lor e acceptata
    doar cand produsul are o singura varianta.
    """
    product = find_product(catalog, product_id)
    if product is None:
        return [ChoiceProblem(code="unknown_product", field="product_id", given=product_id,
                              valid=[p.get("id", "") for p in catalog.get("products") or []])]
    problems: list[ChoiceProblem] = []

    materials = [m.get("name", "") for m in product.get("materials") or []]
    material_name, candidates = match_name(material, materials)
    if material_name is None and not normalize(material) and len(materials) == 1:
        material_name = materials[0]
    if material_name is None:
        code = "ambiguous_material" if candidates else ("missing_material" if not normalize(material) else "unknown_material")
        problems.append(ChoiceProblem(code=code, field="material", given=material, valid=candidates or materials))

    shapes = list(product.get("shapes") or [])
    shape_id = match_shape(shape, shapes)
    if shape_id is None and not normalize(shape) and len(shapes) == 1:
        shape_id = shapes[0]
    if shape_id is None:
        problems.append(ChoiceProblem(code="unknown_shape" if normalize(shape) else "missing_shape", field="shape",
                                      given=shape, valid=shapes,
                                      details={"labels": {s: SHAPE_LABELS_RO.get(s, s) for s in shapes}}))

    width, height = _dec(width_cm), _dec(height_cm)
    if width is None or height is None or width <= 0 or height <= 0:
        problems.append(ChoiceProblem(code="invalid_size", field="size", given=f"{width_cm} x {height_cm}"))
    elif shape_id is not None:
        size_problem = _size_problem(product, shape_id, width, height)
        if size_problem:
            problems.append(size_problem)

    if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
        problems.append(ChoiceProblem(code="invalid_quantity", field="quantity", given=str(quantity)))
    else:
        quantity_problem = _quantity_problem(product, quantity)
        if quantity_problem:
            problems.append(quantity_problem)
        problems.extend(_option_problems(catalog, product, quantity=quantity, adhesive=adhesive,
                                         white_print=white_print, cut=cut, urgent=urgent,
                                         file_editing=file_editing, instructions=instructions))

    for name, value, allowed in (("adhesive", adhesive, ("standard", "strong")), ("cut", cut, ("none", "double", "back")),
                                 ("file_editing", file_editing, ("none", "upscale", "vectorize"))):
        if value not in allowed:
            problems.append(ChoiceProblem(code="invalid_option", field=name, given=str(value), valid=list(allowed)))

    resolved_add_ons, add_on_problems = _resolve_add_ons(product, add_ons or {})
    problems.extend(add_on_problems)
    if problems:
        return problems
    return LineChoices(
        product_id=product_id,
        material_name=material_name,
        shape=shape_id,
        width_cm=width,
        height_cm=height,
        quantity=quantity,
        add_ons=resolved_add_ons,
        adhesive=adhesive,
        white_print=white_print,
        cut=cut,
        urgent=urgent,
        file_editing=file_editing,
        instructions=instructions,
    )
