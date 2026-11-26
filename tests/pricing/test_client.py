"""CalculatorClient: corpul cererii, Decimal, statusuri, reincercare, trepte, cache."""
from __future__ import annotations

import json
from decimal import Decimal

import httpx
import pytest

from ec_quote.contracts import LineChoices, PriceQuote, PricingPort, Unpriced
from ec_quote.pricing import (
    CalculatorClient,
    PricingBadRequest,
    PricingProtocolError,
    PricingUnauthorized,
    PricingUnavailable,
    choices_to_body,
    ex_vat,
    load_vat_percent,
)
from ec_quote.pricing.client import CONFIG_PATH, LINE_PATH
from ec_quote.pricing.fake import FAKE_SECRET, FIXED_SIZE_ID, LABEL_ID, STICKER_ID, FakeCalculator


def choices(**overrides) -> LineChoices:
    base = dict(product_id=STICKER_ID, material_name="Vinil Alb Mat", shape="circle",
                width_cm=Decimal("5"), height_cm=Decimal("5"), quantity=100)
    return LineChoices(**{**base, **overrides})


def scripted(*responses):
    """Client cu raspunsuri fixe (status, text) sau exceptii; intoarce si cererile vazute."""
    queue, seen = list(responses), []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, text = item
        return httpx.Response(status, text=text, headers={"Content-Type": "application/json"})

    client = CalculatorClient("https://calc.test/", "s3cret", http=httpx.Client(transport=httpx.MockTransport(handler)),
                              vat_percent=Decimal("21"))
    return client, seen


PRICED = ('{"status":"priced","total":1234.565,"base":1100.1,"unitPrice":0.1,"capQuantity":500,"pricingPath":"B",'
          '"flatBaselinePct":0,"breakdown":{"discountPercent":12.5,"tablePrice":0.3,"fullPrice":1500},'
          '"properties":[{"name":"Dimensiune","value":"5 x 5 CM"},{"name":"_calculator_price","value":"1234.565"}]}')


# ---------- corpul cererii ----------

def test_body_is_camel_case_with_json_numbers():
    body = choices_to_body(choices(width_cm=Decimal("7.5"), height_cm=Decimal("5.0"), quantity=300,
                                   add_ons={"Finisaj": "Laminare mată"}, adhesive="strong", white_print=True,
                                   cut="double", urgent=True, file_editing="vectorize", instructions="fara margine"))
    assert body == {
        "productId": STICKER_ID, "materialName": "Vinil Alb Mat", "shape": "circle",
        "widthCm": 7.5, "heightCm": 5, "quantity": 300, "addOns": {"Finisaj": "Laminare mată"},
        "adhesive": "strong", "whitePrint": True, "cut": "double", "urgent": True,
        "fileEditing": "vectorize", "instructions": "fara margine",
    }
    assert isinstance(body["heightCm"], int) and isinstance(body["widthCm"], float)


def test_post_sends_secret_and_json_body():
    client, seen = scripted((200, PRICED))
    client.get_price(choices(material_name="Hârtie Kraft"))
    request = seen[0]
    assert request.method == "POST" and str(request.url) == "https://calc.test" + LINE_PATH
    assert request.headers["X-Sync-Secret"] == "s3cret"
    assert request.headers["Content-Type"] == "application/json"
    sent = json.loads(request.content.decode("utf-8"))
    assert sent["materialName"] == "Hârtie Kraft" and sent["widthCm"] == 5 and "freeSample" not in sent
    assert set(sent) == set(choices_to_body(choices()))


def test_implements_pricing_port():
    port: PricingPort = FakeCalculator().client()
    assert all(callable(getattr(port, name)) for name in ("catalog", "get_price", "get_price_tiers"))


# ---------- Decimal ----------

def test_priced_response_is_parsed_into_exact_decimals():
    client, _ = scripted((200, PRICED))
    quote = client.get_price(choices())
    assert isinstance(quote, PriceQuote)
    assert quote.total == Decimal("1234.565") and str(quote.total) == "1234.565"
    assert str(quote.unit_price) == "0.1"
    assert quote.discount_percent == Decimal("12.5")
    assert quote.cap_quantity == 500
    assert quote.total_ex_vat == Decimal("1020.30")  # 1234.565 / 1.21 = 1020.3016...
    assert isinstance(quote.breakdown["tablePrice"], Decimal) and str(quote.breakdown["tablePrice"]) == "0.3"
    assert [(p.name, p.value) for p in quote.properties] == [("Dimensiune", "5 x 5 CM"), ("_calculator_price", "1234.565")]
    assert quote.choices == choices()
    json.loads(quote.model_dump_json())  # se poate serializa


def test_ex_vat_rounds_half_up_and_uses_rules_json():
    assert load_vat_percent() == Decimal("21")
    assert ex_vat(Decimal("121"), Decimal("21")) == Decimal("100.00")
    assert ex_vat(Decimal("100"), Decimal("21")) == Decimal("82.64")
    assert ex_vat(Decimal("0.03"), Decimal("100")) == Decimal("0.02")  # 0.015 -> 0.02, nu 0.01
    assert ex_vat(Decimal("0"), Decimal("21")) == Decimal("0.00")


def test_vat_percent_comes_from_rules_file(tmp_path):
    rules = tmp_path / "rules.json"
    rules.write_text('{"vat_percent": "19"}', encoding="utf-8")
    assert load_vat_percent(rules) == Decimal("19")


def test_null_cap_quantity_and_integer_total():
    client, _ = scripted((200, PRICED.replace('"capQuantity":500', '"capQuantity":null').replace("1234.565,", "242,")))
    quote = client.get_price(choices())
    assert quote.cap_quantity is None and quote.total == Decimal("242") and quote.total_ex_vat == Decimal("200.00")


# ---------- statusuri ----------

def test_422_becomes_unpriced_with_details():
    client, _ = scripted((422, '{"status":"unpriced","reason":"size_below_minimum","minCm":2}'))
    result = client.get_price(choices())
    assert result == Unpriced(reason="size_below_minimum", details={"minCm": 2})


def test_422_without_fields_has_empty_details():
    client, _ = scripted((422, '{"status":"unpriced","reason":"no_price"}'))
    assert client.get_price(choices()) == Unpriced(reason="no_price", details={})


def test_400_raises_bad_request_with_fields_and_is_not_retried():
    client, seen = scripted((400, '{"error":"invalid_body","fields":["widthCm","quantity"]}'))
    with pytest.raises(PricingBadRequest) as caught:
        client.get_price(choices())
    assert caught.value.fields == ["widthCm", "quantity"] and len(seen) == 1


def test_401_raises_unauthorized_and_is_not_retried():
    client, seen = scripted((401, '{"error":"Unauthorized"}'))
    with pytest.raises(PricingUnauthorized):
        client.get_price(choices())
    assert len(seen) == 1
    client, _ = scripted((401, '{"error":"Unauthorized"}'))
    with pytest.raises(PricingUnauthorized):
        client.catalog()


@pytest.mark.parametrize("response", [(405, '{"error":"method_not_allowed"}'), (200, "<html>"), (200, '{"status":"other"}'),
                                      (422, '{"status":"unpriced"}'), (200, '{"status":"priced","total":1}')])
def test_unexpected_answers_raise_protocol_error(response):
    client, _ = scripted(response)
    with pytest.raises(PricingProtocolError):
        client.get_price(choices())


# ---------- reincercare ----------

UNAVAILABLE = (503, '{"error":"admin_unavailable","retryable":true}')


def test_503_is_retried_once_then_succeeds():
    client, seen = scripted(UNAVAILABLE, (200, PRICED))
    assert isinstance(client.get_price(choices()), PriceQuote) and len(seen) == 2


def test_timeout_is_retried_once_then_succeeds():
    client, seen = scripted(httpx.ReadTimeout("slow"), (200, PRICED))
    assert isinstance(client.get_price(choices()), PriceQuote) and len(seen) == 2


@pytest.mark.parametrize("failures", [(UNAVAILABLE, UNAVAILABLE), (httpx.ConnectTimeout("t"), httpx.ConnectError("down")),
                                      (httpx.ReadTimeout("t"), UNAVAILABLE)])
def test_second_failure_raises_pricing_unavailable(failures):
    client, seen = scripted(*failures, (200, PRICED))
    with pytest.raises(PricingUnavailable):
        client.get_price(choices())
    assert len(seen) == 2  # o singura reincercare


def test_callable_transport_is_accepted():
    calls = []

    class Reply:
        status_code = 200
        text = PRICED

    def send(method, url, *, headers, content, timeout):
        calls.append((method, url, headers, json.loads(content), timeout))
        return Reply()

    client = CalculatorClient("https://calc.test", "s", http=send, timeout_seconds=3)
    assert client.get_price(choices()).total == Decimal("1234.565")
    assert calls[0][0] == "POST" and calls[0][2]["X-Sync-Secret"] == "s" and calls[0][4] == 3


# ---------- cache-ul catalogului ----------

class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_catalog_is_cached_for_ttl():
    fake, clock = FakeCalculator(), Clock()
    client = fake.client(clock=clock)
    first = client.catalog()
    clock.now += 299
    assert client.catalog() is first and fake.calls(CONFIG_PATH) == 1
    clock.now += 1  # 300 s: expirat
    fake.catalog["products"][0]["title"] = "Titlu nou"
    assert client.catalog()["products"][0]["title"] == "Titlu nou" and fake.calls(CONFIG_PATH) == 2
    assert fake.requests[0][0] == "GET"


def test_catalog_ttl_is_configurable_and_can_be_invalidated():
    fake, clock = FakeCalculator(), Clock()
    client = fake.client(clock=clock, catalog_ttl_seconds=10)
    client.catalog()
    clock.now += 11
    client.catalog()
    client.invalidate_catalog()
    client.catalog()
    assert fake.calls(CONFIG_PATH) == 3


def test_stale_catalog_is_served_when_refresh_fails():
    fake, clock = FakeCalculator(), Clock()
    client = fake.client(clock=clock)
    first = client.catalog()
    clock.now += 301
    fake.fail_next(503, 503)
    assert client.catalog() is first
    assert client.catalog() is not first  # calculatorul si-a revenit


def test_catalog_unavailable_without_cache_raises():
    fake = FakeCalculator()
    fake.fail_next(503, httpx.ReadTimeout("slow"))
    with pytest.raises(PricingUnavailable):
        fake.client().catalog()
    assert fake.calls(CONFIG_PATH) == 2


def test_catalog_with_wrong_shape_raises_protocol_error():
    client, _ = scripted((200, '{"error":"x"}'))
    with pytest.raises(PricingProtocolError):
        client.catalog()


# ---------- trepte ----------

def test_tiers_are_the_next_ones_strictly_above_and_priced_by_the_calculator():
    fake = FakeCalculator()
    client = fake.client()
    offers = client.get_price_tiers(choices(quantity=100), 2)  # 100 e chiar o treapta: nu se repeta
    assert [o.quantity for o in offers] == [200, 300]
    assert [b["quantity"] for b in fake.line_bodies] == [200, 300]
    for offer in offers:
        direct = client.get_price(choices(quantity=offer.quantity))
        assert (offer.total, offer.total_ex_vat, offer.unit_price) == (direct.total, direct.total_ex_vat, direct.unit_price)
    assert offers[1].unit_price < offers[0].unit_price


def test_tiers_between_tiers_and_other_choices_are_kept():
    fake = FakeCalculator()
    offers = fake.client().get_price_tiers(choices(quantity=120, adhesive="strong"), 3)
    assert [o.quantity for o in offers] == [200, 300, 500]
    assert all(b["adhesive"] == "strong" and b["materialName"] == "Vinil Alb Mat" for b in fake.line_bodies)


def test_tiers_respect_quantity_max_and_end_of_list():
    fake = FakeCalculator()
    fake.catalog["products"][0]["quantity"]["max"] = 1000
    client = fake.client()
    assert [o.quantity for o in client.get_price_tiers(choices(quantity=500), 3)] == [1000]
    assert client.get_price_tiers(choices(quantity=1000), 2) == []
    assert client.get_price_tiers(choices(quantity=100), 0) == []


def test_unpriced_tiers_are_skipped():
    fake = FakeCalculator()
    # urgenta: cel mult 500 buc, deci treapta 1000 vine 422
    offers = fake.client().get_price_tiers(choices(quantity=300, urgent=True), 2)
    assert [o.quantity for o in offers] == [500]
    assert [b["quantity"] for b in fake.line_bodies] == [500, 1000]


def test_tiers_for_unknown_product_are_empty_and_unavailable_propagates():
    fake = FakeCalculator()
    client = fake.client()
    assert client.get_price_tiers(choices(product_id="gid://shopify/Product/9"), 2) == []
    assert fake.calls(LINE_PATH) == 0
    fake.fail_next(503, 503)
    with pytest.raises(PricingUnavailable):
        client.get_price_tiers(choices(), 2)


# ---------- dublura ----------

def test_fake_prices_are_deterministic_and_discounted():
    one, two = FakeCalculator().client().get_price(choices()), FakeCalculator().client().get_price(choices())
    assert one == two and isinstance(one, PriceQuote)
    assert one.total == Decimal("205") and one.total_ex_vat == Decimal("169.42") and one.discount_percent == Decimal("10")
    assert one.breakdown["fullPrice"] > one.total
    assert {p.name for p in one.properties} >= {"Material", "Dimensiune", "_calculator_price"}


@pytest.mark.parametrize("overrides, reason, details", [
    ({"product_id": "gid://shopify/Product/9"}, "unknown_product", {}),
    ({"material_name": "vinil alb mat"}, "unknown_material", {}),
    ({"shape": "heart"}, "unknown_shape", {}),
    ({"product_id": FIXED_SIZE_ID, "material_name": "Vinil Holografic", "width_cm": Decimal("4"),
      "height_cm": Decimal("4")}, "custom_size_disabled", {}),
    ({"width_cm": Decimal("1.5"), "height_cm": Decimal("8")}, "size_below_minimum", {"minCm": 2}),
    ({"width_cm": Decimal("120"), "height_cm": Decimal("8")}, "size_above_maximum", {"maxCm": 100}),
    ({"quantity": 10}, "quantity_below_minimum", {"minQuantity": 25}),
    ({"quantity": 20000}, "quantity_above_maximum", {"maxQuantity": 10000}),
    ({"product_id": LABEL_ID, "material_name": "Polipropilenă Albă", "white_print": True},
     "option_unavailable", {"option": "whitePrint"}),
    ({"quantity": 1000, "urgent": True}, "urgency_quantity_exceeded", {"maxQuantity": 500}),
    ({"add_ons": {"Finisaj": "Aurire"}}, "unknown_add_on", {"option": "Finisaj"}),
    ({"material_name": "Hârtie Kraft"}, "no_price", {}),
])
def test_fake_returns_the_calculator_reason_codes(overrides, reason, details):
    assert FakeCalculator().client().get_price(choices(**overrides)) == Unpriced(reason=reason, details=details)


def test_fake_checks_secret_and_body():
    fake = FakeCalculator()
    wrong = CalculatorClient("https://calculator.test", "gresit", http=fake.http())
    with pytest.raises(PricingUnauthorized):
        wrong.catalog()
    assert fake.secret == FAKE_SECRET
    assert fake.price({"productId": STICKER_ID})[0] == 400
    assert fake.price({**choices_to_body(choices()), "widthCm": "5"}) == (400, {"error": "invalid_body", "fields": ["widthCm"]})
    fake.fail_next(400)
    with pytest.raises(PricingBadRequest):
        fake.client().get_price(choices())


def test_fake_options_change_the_price():
    client = FakeCalculator().client()
    plain = client.get_price(choices()).total
    assert client.get_price(choices(adhesive="strong")).total > plain
    assert client.get_price(choices(urgent=True)).total == plain + 125
    assert client.get_price(choices(add_ons={"Finisaj": "Laminare mată"})).total > plain
    assert client.get_price(choices(width_cm=Decimal("9"), height_cm=Decimal("4"), shape="rectangle")).total > plain
