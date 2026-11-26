from __future__ import annotations

import io
import json
from decimal import Decimal

import httpx
import pytest
from PIL import Image

from ec_quote.agent import ApprovalError
from ec_quote.integrations import DEFAULT_API_VERSION, ShopifyCheckout

from .helpers import ANA, CHAT, LINE, build, close, customer, logo_png, script, suggest

OFFER = [("check_file", {"width_cm": 5, "height_cm": 5}), ("get_price", LINE),
         ("get_price_tiers", {"quote_id": "q1"}), ("make_mockup", {"context_hint": "borcan cu miere"}),
         ("create_checkout", {"quote_ids": ["q1"], "summary": "500 stickere rotunde 5 cm pentru borcane"})]


@pytest.fixture
def ctx(tmp_path):
    built = build(tmp_path)
    yield built
    close(built)


def upload(ctx, message_id: str = "wamid.1", name: str = "logo.png") -> str:
    response = ctx.client.post("/v1/assist/upload", headers=ANA, data={"chat_key": CHAT, "message_id": message_id},
                               files={"file": (name, logo_png(), "image/png")})
    assert response.status_code == 200, response.text
    return response.json()["upload_id"]


def test_upload_offer_image_payment_link_resend_and_knowledge(ctx):
    assert ctx.client.get("/v1/assist/ping", headers=ANA).json() == {"ok": True, "staff": "ana"}

    # 1. Logo incarcat, cerere completa, oferta din calculator cu imagine servita prin ruta semnata.
    customer(ctx, "Buna ziua, vreau 500 stickere rotunde de 5 cm pentru borcane", upload_id=upload(ctx))
    script(ctx, *OFFER)
    offer = suggest(ctx)
    assert offer["kind"] == "offer" and offer["can_create_payment_link"] is True and offer["payment_url"] is None
    quote = ctx.calculator.client().get_price(ctx.engine.store.load("whatsapp", CHAT).quotes["q1"].choices)
    assert offer["offer_lines"][0]["total"] == str(quote.total)
    assert "500 buc" in offer["text"] and "lei fără TVA" in offer["text"] and "http" not in offer["text"]
    assert [line["quantity"] for line in offer["offer_lines"]][0] == 500 and len(offer["offer_lines"]) == 3
    assert "image_path" not in offer

    image = ctx.client.get(offer["image_url"])
    assert image.status_code == 200 and image.headers["content-type"].startswith("image/")
    assert Image.open(io.BytesIO(image.content)).size[0] > 200
    state = ctx.engine.store.load("whatsapp", CHAT)
    assert state.design.path.startswith(str(ctx.data_dir)) and state.file_report.verdict.value in ("ok", "weak")
    assert state.mockup_path.startswith(str(ctx.data_dir))
    # Detaliile calculatorului trec prin JSON (stare, sugestie) fara sa piarda precizia.
    assert json.loads(state.model_dump_json())["quotes"]["q1"]["total"] == str(quote.total)

    # 2. Aceeasi conversatie, din nou: aceeasi sugestie, fara model.
    again = suggest(ctx)
    assert again["suggestion_id"] == offer["suggestion_id"] and again["text"] == offer["text"]
    assert ctx.model.replies == []

    # 3. Omul creeaza linkul de plata.
    link = ctx.client.post(f"/v1/assist/suggestions/{offer['suggestion_id']}/payment-link", headers=ANA, json={})
    assert link.status_code == 200, link.text
    linked = link.json()["suggestion"]
    assert linked["payment_url"] == "https://shop.test/invoices/1" and linked["text"].endswith(linked["payment_url"])
    sent_quote, contact, artwork_url, _ = ctx.checkout.calls[0]
    assert sent_quote.total == quote.total and contact.phone == "+40700001234"
    assert isinstance(sent_quote.total, Decimal)
    second_click = ctx.client.post(f"/v1/assist/suggestions/{offer['suggestion_id']}/payment-link", headers=ANA)
    assert second_click.json()["suggestion"]["payment_url"] == linked["payment_url"] and len(ctx.checkout.calls) == 1

    # 4. Omul trimite oferta; clientul intreaba ceva general: raspuns din baza de cunostinte reala.
    customer(ctx, linked["text"], direction="out")
    assert suggest(ctx)["kind"] == "none"
    customer(ctx, "Multumesc! Sunt rezistente la apa?")
    entry = ctx.engine.knowledge.search("sunt rezistente la apa")[0]
    script(ctx, ("search_knowledge", {"query": "sunt rezistente la apa"}), entry.answer)
    answer = suggest(ctx)
    assert answer["kind"] == "reply" and answer["text"] == entry.answer and answer["note_for_staff"] == ""
    metrics = ctx.engine.assist_metrics("whatsapp", CHAT)
    assert metrics["items"][0]["outcome"] == "exact" and metrics["links_created"] == 1


def test_error_mapping_for_unknown_and_superseded_suggestions(ctx):
    missing = ctx.client.post("/v1/assist/suggestions/nu-exista/payment-link", headers=ANA)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "suggestion_not_found"

    customer(ctx, "vreau 500 stickere rotunde de 5 cm")
    script(ctx, ("get_price", LINE), ("create_checkout", {"quote_ids": ["q1"], "summary": "500"}))
    old = suggest(ctx)
    customer(ctx, "de fapt 1000")
    script(ctx, ("get_price", {**LINE, "quantity": 1000}), ("create_checkout", {"quote_ids": ["q2"], "summary": "1000"}))
    new = suggest(ctx)
    assert new["kind"] == "offer" and "1.000 buc" in new["text"]
    assert new["image_url"] and ctx.client.get(new["image_url"]).status_code == 200  # oferta fara mockup

    stale = ctx.client.post(f"/v1/assist/suggestions/{old['suggestion_id']}/payment-link", headers=ANA)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "suggestion_not_available"
    assert ctx.checkout.calls == []
    with pytest.raises(ApprovalError) as unknown:
        ctx.engine.create_payment_link("nu-exista", "ana", ctx.clock())
    with pytest.raises(ApprovalError) as replaced:
        ctx.engine.create_payment_link(old["suggestion_id"], "ana", ctx.clock())
    assert (unknown.value.code, replaced.value.code) == ("not_found", "not_available")


def test_unpriced_and_over_threshold_through_the_real_calculator_client(ctx):
    customer(ctx, "vreau 10 stickere rotunde de 5 cm")
    script(ctx, ("get_price", {**LINE, "quantity": 10}), ("get_price", {**LINE, "quantity": 25}),
           ("send_price_comparison", {"quote_ids": ["q1"], "intro": "Comanda minimă este de 25 de bucăți."}))
    reply = suggest(ctx)
    assert reply["kind"] == "reply" and "25 buc" in reply["text"] and "lei cu TVA" in reply["text"]

    customer(ctx, "si pentru 10000 de bucati de 10 cm?")
    script(ctx, ("get_price", {**LINE, "quantity": 10000, "width_cm": 10, "height_cm": 10}))
    big = suggest(ctx)
    assert big["kind"] == "needs_human" and big["handoff_reason"] == "value_over_threshold"
    assert big["text"] == "" and "peste pragul" in big["note_for_staff"] and big["offer_lines"]


def test_payment_link_with_the_real_shopify_adapter(tmp_path):
    seen: list[dict] = []

    def shopify(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen.append(body)
        if "draftOrderCreate" in body["query"]:
            line = body["variables"]["input"]["lineItems"][0]
            amount = (line.get("priceOverride") or line.get("originalUnitPriceWithCurrency"))["amount"]
            return httpx.Response(200, json={"data": {"draftOrderCreate": {"userErrors": [], "draftOrder": {
                "id": "gid://shopify/DraftOrder/77", "invoiceUrl": "https://shop.test/invoices/77",
                "taxesIncluded": True, "totalPriceSet": {"shopMoney": {"amount": amount, "currencyCode": "RON"}}}}}})
        return httpx.Response(200, json={"data": {"product": {"title": "Stickere Personalizate", "variants": {
            "nodes": [{"id": "gid://shopify/ProductVariant/1", "selectedOptions": [{"name": "Title", "value": "Default"}]}]}}}})

    checkout = ShopifyCheckout("shop.test", "shpat_test_token", httpx.Client(transport=httpx.MockTransport(shopify)),
                               DEFAULT_API_VERSION)
    ctx = build(tmp_path, checkout=checkout)
    try:
        customer(ctx, "vreau 500 stickere rotunde de 5 cm", upload_id=upload(ctx))
        script(ctx, ("get_price", LINE), ("create_checkout", {"quote_ids": ["q1"], "summary": "500 stickere"}))
        offer = suggest(ctx)
        link = ctx.client.post(f"/v1/assist/suggestions/{offer['suggestion_id']}/payment-link", headers=ANA)
        assert link.status_code == 200, link.text
        assert link.json()["suggestion"]["payment_url"] == "https://shop.test/invoices/77"
        created = next(b for b in seen if "draftOrderCreate" in b["query"])
        line = created["variables"]["input"]["lineItems"][0]
        assert Decimal(line["priceOverride"]["amount"]) == Decimal(offer["offer_lines"][0]["total"])
        names = {a["key"] for a in line["customAttributes"]}
        assert any("calculator_price" in name for name in names)
    finally:
        close(ctx)
