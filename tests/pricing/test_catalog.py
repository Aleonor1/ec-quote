"""Rezumatul catalogului si rezolvarea toleranta a alegerilor."""
from __future__ import annotations

from decimal import Decimal

import pytest

from ec_quote.contracts import LineChoices, PriceQuote
from ec_quote.pricing import (
    ChoiceProblem,
    catalog_summary,
    find_products,
    match_name,
    match_shape,
    normalize,
    resolve_choices,
)
from ec_quote.pricing.fake import FAKE_CATALOG, FIXED_SIZE_ID, LABEL_ID, STICKER_ID, FakeCalculator


def codes(result) -> list[str]:
    assert isinstance(result, list), result
    return [p.code for p in result]


def problem(result, code: str) -> ChoiceProblem:
    return next(p for p in result if p.code == code)


def test_normalize_drops_case_diacritics_and_punctuation():
    assert normalize("  Hârtie  Albă-Lucioasă ") == "hartie alba lucioasa"
    assert normalize("ȘȚĂÎÂ șțăîâ") == "staia staia"
    assert normalize(None) == ""


@pytest.mark.parametrize("given, expected", [
    ("Vinil Alb Mat", "Vinil Alb Mat"), ("vinil alb mat", "Vinil Alb Mat"), ("VINIL  transparent", "Vinil Transparent"),
    ("transparent", "Vinil Transparent"), ("hartie kraft", "Hârtie Kraft"), ("kraft", "Hârtie Kraft"),
    ("mat alb", "Vinil Alb Mat"), ("vinil alb mat premium", "Vinil Alb Mat"),
])
def test_material_names_match_tolerantly(given, expected):
    names = [m["name"] for m in FAKE_CATALOG["products"][0]["materials"]]
    assert match_name(given, names) == (expected, [])


def test_ambiguous_and_unknown_material_names():
    names = [m["name"] for m in FAKE_CATALOG["products"][0]["materials"]]
    assert match_name("vinil alb", names) == (None, ["Vinil Alb Lucios", "Vinil Alb Mat"])
    assert match_name("carton", names) == (None, [])
    assert match_name("", names) == (None, [])


@pytest.mark.parametrize("given, expected", [
    ("circle", "circle"), ("Rotund", "circle"), ("rotundă", "circle"), ("cerc", "circle"), ("pătrat", "square"),
    ("dreptunghiulara", "rectangle"), ("OVAL", "oval"), ("pe contur", "custom"), ("forma rotunda", "circle"),
    ("stea", None), ("", None),
])
def test_shape_names_match_ids_and_romanian_words(given, expected):
    assert match_shape(given, ["custom", "circle", "oval", "square", "rectangle"]) == expected


def test_shape_not_offered_by_the_product_does_not_match():
    assert match_shape("patrat", ["circle", "rectangle"]) is None


def test_find_products_by_words_without_diacritics():
    assert [p["id"] for p in find_products(FAKE_CATALOG, "etichete pe rola")] == [LABEL_ID]
    assert find_products(FAKE_CATALOG, "STICKERE holografice")[0]["id"] == FIXED_SIZE_ID
    assert {p["id"] for p in find_products(FAKE_CATALOG, "sticker")} == {STICKER_ID, FIXED_SIZE_ID}
    assert find_products(FAKE_CATALOG, STICKER_ID) == [FAKE_CATALOG["products"][0]]
    assert find_products(FAKE_CATALOG, "bannere") == []
    assert len(find_products(FAKE_CATALOG, "")) == 3 and len(find_products(FAKE_CATALOG, "", limit=1)) == 1


def test_summary_lists_ids_names_limits_and_no_prices():
    text = catalog_summary(FAKE_CATALOG)
    for expected in ("Stickere Personalizate", STICKER_ID, "custom, circle, oval, square, rectangle",
                     "Vinil Alb Lucios; Vinil Alb Mat", "2-100 cm", "min 25, max 10000", "100 (-10%)", "7.5x5",
                     "marime personalizata: nu", "add-on Finisaj: Fără laminare, Laminare mată",
                     "Urgenta: cel mult 500 buc."):
        assert expected in text
    assert "pricingTableId" not in text and "Metaobject" not in text and "lei" not in text.lower()
    assert len(text) < 2500
    assert "(niciun produs)" in catalog_summary({"products": []})


def test_summary_caps_long_size_lists():
    catalog = {"products": [{"id": "x", "title": "T", "shapes": ["square"], "materials": [],
                             "sizesByShape": {"square": [{"widthCm": n, "heightCm": n} for n in range(1, 30)]},
                             "customSize": {"enabled": False}, "quantity": {"tiers": [], "min": 1, "max": 9}}]}
    assert "10x10, ..." in catalog_summary(catalog) and "11x11" not in catalog_summary(catalog)


def test_resolve_returns_exact_catalog_names():
    result = resolve_choices(FAKE_CATALOG, STICKER_ID, "vinil TRANSPARENT", "rotund", "5", 5, 100,
                             add_ons={"finisaj": "laminare mata"}, adhesive="strong", urgent=True)
    assert result == LineChoices(product_id=STICKER_ID, material_name="Vinil Transparent", shape="circle",
                                 width_cm=Decimal("5"), height_cm=Decimal("5"), quantity=100,
                                 add_ons={"Finisaj": "Laminare mată"}, adhesive="strong", urgent=True)


def test_resolved_choices_are_priced_by_the_calculator():
    client = FakeCalculator().client()
    resolved = resolve_choices(client.catalog(), LABEL_ID, "polipropilena", "dreptunghi", Decimal("7.5"), 5, 250)
    assert isinstance(resolved, LineChoices)
    assert isinstance(client.get_price(resolved), PriceQuote)


def test_single_material_and_shape_are_implied():
    result = resolve_choices(FAKE_CATALOG, FIXED_SIZE_ID, None, "", 5, 5, 50)
    assert isinstance(result, LineChoices) and (result.material_name, result.shape) == ("Vinil Holografic", "circle")


def test_missing_material_and_shape_list_the_valid_options():
    result = resolve_choices(FAKE_CATALOG, LABEL_ID, None, None, 5, 5, 100)
    assert codes(result) == ["missing_material", "missing_shape"]
    assert problem(result, "missing_material").valid == ["Hârtie Albă Lucioasă", "Polipropilenă Albă"]
    shape = problem(result, "missing_shape")
    assert shape.valid == ["circle", "rectangle"] and shape.details["labels"]["circle"] == "cerc"


def test_unknown_product_material_and_shape():
    assert codes(resolve_choices(FAKE_CATALOG, "gid://shopify/Product/9", "x", "y", 5, 5, 100)) == ["unknown_product"]
    result = resolve_choices(FAKE_CATALOG, STICKER_ID, "carton", "stea", 5, 5, 100)
    assert codes(result) == ["unknown_material", "unknown_shape"]
    assert "Vinil Alb Mat" in problem(result, "unknown_material").valid
    ambiguous = resolve_choices(FAKE_CATALOG, STICKER_ID, "vinil alb", "cerc", 5, 5, 100)
    assert codes(ambiguous) == ["ambiguous_material"]
    assert problem(ambiguous, "ambiguous_material").valid == ["Vinil Alb Lucios", "Vinil Alb Mat"]


def test_size_rules_follow_the_calculator():
    def size(product, shape, w, h, material=None):
        return resolve_choices(FAKE_CATALOG, product, material, shape, w, h, 100)

    assert isinstance(size(STICKER_ID, "dreptunghi", 4, 9, "kraft"), LineChoices)  # preset intors
    below = size(STICKER_ID, "cerc", "1.5", 8, "kraft")
    assert codes(below) == ["size_below_minimum"] and below[0].details == {"minCm": "2"}
    above = size(STICKER_ID, "cerc", 120, 8, "kraft")
    assert codes(above) == ["size_above_maximum"] and above[0].details == {"maxCm": "100"}
    fixed = size(FIXED_SIZE_ID, "cerc", 4, 4)
    assert codes(fixed) == ["custom_size_disabled"] and fixed[0].valid == ["3 x 3", "5 x 5", "7 x 7", "10 x 10"]
    assert isinstance(size(FIXED_SIZE_ID, "cerc", 7, 7), LineChoices)
    assert codes(size(STICKER_ID, "cerc", "abc", 0, "kraft")) == ["invalid_size"]


def test_quantity_and_option_rules():
    def resolve(**kwargs):
        args = dict(product_id=LABEL_ID, material="polipropilena", shape="cerc", width_cm=5, height_cm=5, quantity=250)
        return resolve_choices(FAKE_CATALOG, **{**args, **kwargs})

    low = resolve(quantity=50)
    assert codes(low) == ["quantity_below_minimum"] and low[0].details == {"minQuantity": 100}
    assert resolve(quantity=6000)[0].details == {"maxQuantity": 5000}
    assert codes(resolve(quantity=0)) == ["invalid_quantity"]
    unavailable = resolve(white_print=True, cut="double", instructions="fara margine")
    assert [(p.code, p.details["option"]) for p in unavailable] == [
        ("option_unavailable", "whitePrint"), ("option_unavailable", "cut"), ("option_unavailable", "instructions")]
    urgent = resolve(quantity=1000, urgent=True)
    assert codes(urgent) == ["urgency_quantity_exceeded"] and urgent[0].details == {"maxQuantity": 500}
    assert codes(resolve(adhesive="tare")) == ["invalid_option"]
    assert isinstance(resolve(adhesive="strong", urgent=True, file_editing="vectorize"), LineChoices)


def test_unknown_add_on_group_and_choice():
    def resolve(add_ons):
        return resolve_choices(FAKE_CATALOG, STICKER_ID, "kraft", "cerc", 5, 5, 100, add_ons=add_ons)

    group = resolve({"Culoare": "rosu"})
    assert codes(group) == ["unknown_add_on"] and group[0].valid == ["Finisaj"]
    choice = resolve({"Finisaj": "aurire"})
    assert choice[0].valid == ["Fără laminare", "Laminare mată"] and choice[0].details == {"option": "Finisaj"}
