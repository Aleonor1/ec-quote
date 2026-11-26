from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal

import httpx
import pytest

from ec_quote.contracts import CheckoutPort
from ec_quote.integrations import (
    DraftOrderNotFound,
    ShopifyCheckout,
    ShopifyInvalidQuote,
    ShopifyPriceMismatch,
    ShopifyProductNotFound,
    ShopifyProtocolError,
    ShopifyThrottled,
    ShopifyUnauthorized,
    ShopifyUnavailable,
    ShopifyUserError,
)
from ec_quote.integrations.shopify import e164, mask_key, product_gid
from tests.integrations.helpers import (
    DRAFT_GID,
    INVOICE_URL,
    PERMANENT_VARIANT,
    PRODUCT_GID,
    Recorder,
    body_of,
    make_contact,
    make_quote,
)

TOKEN = "shpat_secret_token"
VALID_UNTIL = datetime(2026, 12, 3, 18, 0)


def ok(data: dict, **extra) -> httpx.Response:
    return httpx.Response(200, json={"data": data, **extra})


def variants(*nodes) -> httpx.Response:
    return ok({"product": {"id": PRODUCT_GID, "title": "Sticker Premium", "variants": {"nodes": list(nodes)}}})


def variant(gid: str, title: str) -> dict:
    return {"id": gid, "selectedOptions": [{"name": "Title", "value": title}]}


DEFAULT_VARIANTS = variants(
    variant("gid://shopify/ProductVariant/1", "calc-6x6-300buc-430.00"),
    variant(PERMANENT_VARIANT, "opc-Default Title"),
)


def created(total: str = "217.0", taxes_included: bool = True) -> httpx.Response:
    return ok({"draftOrderCreate": {
        "draftOrder": {
            "id": DRAFT_GID, "name": "#D12", "invoiceUrl": INVOICE_URL, "status": "OPEN",
            "taxesIncluded": taxes_included,
            "totalPriceSet": {"shopMoney": {"amount": total, "currencyCode": "RON"}},
        },
        "userErrors": [],
    }})


THROTTLED = httpx.Response(200, json={
    "errors": [{"message": "Throttled", "extensions": {"code": "THROTTLED"}}],
    "extensions": {"cost": {
        "requestedQueryCost": 20,
        "throttleStatus": {"maximumAvailable": 2000, "currentlyAvailable": 5, "restoreRate": 10},
    }},
})


def make(responses, sleeps=None):
    recorder = Recorder(responses)
    sleeps = sleeps if sleeps is not None else []
    checkout = ShopifyCheckout("x1pdy3-ic.myshopify.com", TOKEN, recorder.client(), sleep=sleeps.append)
    return checkout, recorder


def test_implements_the_port():
    checkout, _ = make([])
    port: CheckoutPort = checkout
    assert port is checkout


def test_create_checkout_uses_permanent_variant_and_exact_total():
    checkout, rec = make([DEFAULT_VARIANTS, created()])
    result = checkout.create_checkout(make_quote(), make_contact(), "https://cdn.test/a/logo.pdf?x=1", VALID_UNTIL)

    assert result.draft_order_id == DRAFT_GID
    assert result.invoice_url == INVOICE_URL
    assert result.total == Decimal("217.00")

    lookup, create = rec.requests
    assert str(lookup.url) == "https://x1pdy3-ic.myshopify.com/admin/api/2026-04/graphql.json"
    assert lookup.headers["X-Shopify-Access-Token"] == TOKEN
    assert body_of(lookup)["variables"] == {"id": PRODUCT_GID}

    sent = body_of(create)
    assert "draftOrderCreate(input: $input)" in sent["query"]
    draft = sent["variables"]["input"]
    (line,) = draft["lineItems"]
    assert line["variantId"] == PERMANENT_VARIANT
    assert line["quantity"] == 1
    assert line["priceOverride"] == {"amount": "217.00", "currencyCode": "RON"}
    assert "originalUnitPriceWithCurrency" not in line
    # aceleasi nume, aceeasi ordine, fisierul la sfarsit
    assert [a["key"] for a in line["customAttributes"]] == [
        "_Sticker Quantity", "Forma Taiere", "Dimensiune", "_calculator_price", "_product_gid",
        "_Quantity", "_Upload Artwork", "_Upload Artwork1",
    ]
    assert line["customAttributes"][-2]["value"] == "application/pdf"
    assert line["customAttributes"][-1]["value"] == "https://cdn.test/a/logo.pdf?x=1"
    assert draft["tags"] == ["ec-quote", "ec-quote-whatsapp", "ad-meta-ads-vara"]
    assert "whatsapp:40722123456" in draft["note"]
    assert "2026-12-03 18:00" in draft["note"]
    assert {"key": "ec_quote_key", "value": "40722123456"} in draft["customAttributes"]
    assert {"key": "ec_quote_ad_source", "value": "meta ads, vara"} in draft["customAttributes"]
    assert draft["phone"] == "+40722123456"
    assert "email" not in draft
    assert "sourceName" not in draft and "taxExempt" not in draft


def test_no_artwork_and_site_contact_without_phone():
    checkout, rec = make([DEFAULT_VARIANTS, created()])
    contact = make_contact(channel="site", key="sess-1", phone=None, email="ana@test.ro", ad_source=None)
    checkout.create_checkout(make_quote(), contact, None, VALID_UNTIL)
    draft = body_of(rec.requests[1])["variables"]["input"]
    assert [a["key"] for a in draft["lineItems"][0]["customAttributes"]][-1] == "_Quantity"
    assert draft["tags"] == ["ec-quote", "ec-quote-site"]
    assert draft["email"] == "ana@test.ro"
    assert "phone" not in draft
    assert all(a["key"] != "ec_quote_ad_source" for a in draft["customAttributes"])


def test_existing_artwork_property_is_not_duplicated():
    quote = make_quote()
    quote.properties.append(type(quote.properties[0])(name="_Upload Artwork1", value="https://cdn.test/old.png"))
    checkout, rec = make([DEFAULT_VARIANTS, created()])
    checkout.create_checkout(quote, make_contact(), "https://cdn.test/new.png", VALID_UNTIL)
    keys = [a["key"] for a in body_of(rec.requests[1])["variables"]["input"]["lineItems"][0]["customAttributes"]]
    assert keys.count("_Upload Artwork1") == 1 and "_Upload Artwork" not in keys


def test_variant_lookup_is_cached_and_numeric_product_id_becomes_gid():
    checkout, rec = make([DEFAULT_VARIANTS, created(), created()])
    quote = make_quote(product_id="15382742597956")
    checkout.create_checkout(quote, make_contact(), None, VALID_UNTIL)
    checkout.create_checkout(quote, make_contact(), None, VALID_UNTIL)
    assert len(rec.requests) == 3
    assert body_of(rec.requests[0])["variables"] == {"id": PRODUCT_GID}


def test_product_without_permanent_variant_falls_back_to_custom_line():
    only_temp = variants(variant("gid://shopify/ProductVariant/1", "calc-6x6-300buc-430.00"))
    checkout, rec = make([only_temp, created()])
    checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    line = body_of(rec.requests[1])["variables"]["input"]["lineItems"][0]
    assert "variantId" not in line and "priceOverride" not in line
    assert line["title"] == "Sticker Premium"
    assert line["originalUnitPriceWithCurrency"] == {"amount": "217.00", "currencyCode": "RON"}
    assert line["taxable"] is True and line["requiresShipping"] is True


def test_vat_added_on_top_deletes_the_draft_and_raises():
    deleted = ok({"draftOrderDelete": {"deletedId": DRAFT_GID, "userErrors": []}})
    checkout, rec = make([DEFAULT_VARIANTS, created(total="262.57", taxes_included=False), deleted])
    with pytest.raises(ShopifyPriceMismatch) as info:
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert info.value.expected == Decimal("217.00")
    assert info.value.actual == Decimal("262.57")
    assert info.value.deleted is True
    assert body_of(rec.requests[2])["variables"] == {"input": {"id": DRAFT_GID}}


def test_price_mismatch_reports_failed_delete():
    checkout, _ = make([DEFAULT_VARIANTS, created(total="300.00"), httpx.Response(500)])
    with pytest.raises(ShopifyPriceMismatch) as info:
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert info.value.deleted is False


def test_user_errors_are_typed():
    failed = ok({"draftOrderCreate": {"draftOrder": None, "userErrors": [
        {"field": ["input", "phone"], "message": "Phone is invalid"}]}})
    checkout, _ = make([DEFAULT_VARIANTS, failed])
    with pytest.raises(ShopifyUserError) as info:
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert info.value.errors == [{"field": ["input", "phone"], "message": "Phone is invalid"}]
    assert "Phone is invalid" in str(info.value)


def test_throttled_retries_once_honoring_cost():
    sleeps: list[float] = []
    checkout, rec = make([DEFAULT_VARIANTS, THROTTLED, created()], sleeps)
    result = checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert result.draft_order_id == DRAFT_GID
    assert sleeps == [1.5]  # (20 - 5) / 10
    assert len(rec.requests) == 3


def test_throttled_twice_raises():
    sleeps: list[float] = []
    checkout, rec = make([DEFAULT_VARIANTS, THROTTLED, THROTTLED], sleeps)
    with pytest.raises(ShopifyThrottled):
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert len(rec.requests) == 3 and len(sleeps) == 1


def test_http_429_uses_retry_after_and_bad_cost_defaults():
    sleeps: list[float] = []
    no_cost = httpx.Response(200, json={"errors": [{"extensions": {"code": "THROTTLED"}}]})
    checkout, _ = make([httpx.Response(429, headers={"Retry-After": "2.0"}), DEFAULT_VARIANTS, no_cost, created()], sleeps)
    checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert sleeps == [2.0, 1.0]


def test_bad_retry_after_defaults_to_one_second():
    sleeps: list[float] = []
    checkout, _ = make([httpx.Response(429, headers={"Retry-After": "soon"}), DEFAULT_VARIANTS], sleeps)
    checkout._permanent_variant(PRODUCT_GID)
    assert sleeps == [1.0]


def test_create_is_not_retried_on_network_error():
    checkout, rec = make([DEFAULT_VARIANTS, httpx.ReadTimeout("slow")])
    with pytest.raises(ShopifyUnavailable):
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert len(rec.requests) == 2


@pytest.mark.parametrize("response, error", [
    (httpx.Response(401), ShopifyUnauthorized),
    (httpx.Response(403), ShopifyUnauthorized),
    (httpx.Response(502), ShopifyUnavailable),
    (httpx.Response(404), ShopifyProtocolError),
    (httpx.Response(200, text="<html>"), ShopifyProtocolError),
    (httpx.Response(200, json=[1]), ShopifyProtocolError),
    (httpx.Response(200, json={"errors": [{"message": "Field 'x' doesn't exist"}, "boom"]}), ShopifyProtocolError),
    (httpx.Response(200, json={"errors": "bad"}), ShopifyProtocolError),
    (httpx.Response(200, json={"data": None}), ShopifyProtocolError),
    (ok({"product": None}), ShopifyProductNotFound),
])
def test_lookup_failures_are_typed(response, error):
    checkout, _ = make([response])
    with pytest.raises(error):
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)


@pytest.mark.parametrize("payload", [
    {"draftOrderCreate": {"draftOrder": None, "userErrors": []}},
    {"draftOrderCreate": {"draftOrder": {"id": DRAFT_GID, "invoiceUrl": None}, "userErrors": []}},
    {"draftOrderCreate": {"draftOrder": {"id": DRAFT_GID, "invoiceUrl": INVOICE_URL}, "userErrors": []}},
    {"draftOrderCreate": {"draftOrder": {"id": DRAFT_GID, "invoiceUrl": INVOICE_URL,
                                         "totalPriceSet": {"shopMoney": {"amount": "abc"}}}, "userErrors": []}},
])
def test_malformed_create_payload(payload):
    checkout, _ = make([DEFAULT_VARIANTS, ok(payload)])
    with pytest.raises(ShopifyProtocolError):
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)


def test_zero_total_and_missing_product_are_rejected_before_any_call():
    checkout, rec = make([])
    with pytest.raises(ShopifyInvalidQuote):
        checkout.create_checkout(make_quote(total="0"), make_contact(), None, VALID_UNTIL)
    quote = make_quote(product_id="")
    quote.properties = [p for p in quote.properties if p.name != "_product_gid"]
    with pytest.raises(ShopifyInvalidQuote):
        checkout.create_checkout(quote, make_contact(), None, VALID_UNTIL)
    assert rec.requests == []


def test_product_id_falls_back_to_the_property():
    checkout, rec = make([DEFAULT_VARIANTS, created()])
    checkout.create_checkout(make_quote(product_id=""), make_contact(), None, VALID_UNTIL)
    assert body_of(rec.requests[0])["variables"] == {"id": PRODUCT_GID}


def test_get_status_open_and_completed():
    open_draft = ok({"draftOrder": {"id": DRAFT_GID, "status": "INVOICE_SENT", "invoiceUrl": INVOICE_URL,
                                    "completedAt": None, "order": None}})
    paid = ok({"draftOrder": {"id": DRAFT_GID, "status": "COMPLETED", "invoiceUrl": INVOICE_URL,
                              "completedAt": "2026-11-27T10:00:00Z",
                              "order": {"id": "gid://shopify/Order/7", "name": "#1700",
                                        "displayFinancialStatus": "PAID"}}})
    checkout, _ = make([open_draft, paid])
    first = checkout.get_status(DRAFT_GID)
    assert (first.state, first.shopify_status, first.order_id, first.paid) == ("open", "INVOICE_SENT", None, False)
    second = checkout.get_status(DRAFT_GID)
    assert second.state == "completed"
    assert second.order_id == "gid://shopify/Order/7"
    assert second.order_name == "#1700"
    assert second.paid is True


def test_get_status_missing_draft():
    checkout, _ = make([ok({"draftOrder": None})])
    with pytest.raises(DraftOrderNotFound):
        checkout.get_status(DRAFT_GID)


def test_delete_draft_order_user_errors():
    checkout, _ = make([ok({"draftOrderDelete": {"deletedId": None, "userErrors": [{"field": None, "message": "nope"}]}})])
    with pytest.raises(ShopifyUserError):
        checkout.delete_draft_order(DRAFT_GID)


def test_token_and_phone_never_reach_the_log(caplog):
    checkout, _ = make([DEFAULT_VARIANTS, created()])
    with caplog.at_level(logging.DEBUG):
        checkout.create_checkout(make_quote(), make_contact(), None, VALID_UNTIL)
    assert TOKEN not in caplog.text and TOKEN not in repr(checkout)
    assert "40722123456" not in caplog.text
    assert "***456" in caplog.text


def test_constructor_validates_and_normalizes():
    with pytest.raises(ValueError):
        ShopifyCheckout("", TOKEN, httpx.Client())
    checkout = ShopifyCheckout("https://shop.test/", TOKEN, httpx.Client(), "2026-07")
    assert "https://shop.test/admin/api/2026-07/graphql.json" in repr(checkout)


def test_helpers():
    assert e164("0722 123 456") == "+40722123456"
    assert e164("0040722123456") == "+40722123456"
    assert e164("40722123456") == "+40722123456"
    assert e164("123") is None and e164(None) is None
    assert mask_key(None) == "?" and mask_key("ab") == "***"
    assert product_gid(" gid://shopify/Product/1 ") == "gid://shopify/Product/1"
