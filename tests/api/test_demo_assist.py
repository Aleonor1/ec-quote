"""Motorul demonstrativ in modul asistat: preturi exclusiv din FakeCalculator, fara chei de productie."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from ec_quote.agent import ApprovalError
from ec_quote.api.demo_engine import DemoEngine, build_engine
from ec_quote.contracts import (
    AssistEngine,
    AssistMessage,
    Attachment,
    Contact,
    Engine,
    HandoffReason,
    LineChoices,
    PendingAttachment,
)
from ec_quote.pricing.fake import LABEL_ID, STICKER_ID, FakeCalculator
from tests.api.conftest import ANA, PNG, WA_KEY, build

NOW = datetime(2026, 11, 26, 10, 0, tzinfo=ZoneInfo("Europe/Bucharest"))
CONTACT = Contact(channel="whatsapp", key=WA_KEY, name="Client Demo", phone="+40700001234")


def _msg(mid: str, text: str = "", *, direction: str = "in", attachments=None, unuploaded=None) -> AssistMessage:
    return AssistMessage(
        id=mid,
        direction=direction,
        text=text,
        sent_at=NOW,
        attachments=attachments or [],
        unuploaded_attachments=unuploaded or [],
    )


def test_demo_engine_implements_engine_and_assist_protocols(tmp_path):
    engine = DemoEngine(tmp_path)
    for protocol in (Engine, AssistEngine):
        assert all(callable(getattr(engine, name)) for name in vars(protocol) if not name.startswith("_"))


def test_demo_assist_none_and_question_and_idempotency(tmp_path):
    engine = DemoEngine(tmp_path)
    assert engine.suggest(CONTACT, [], NOW).kind == "none"
    assert engine.suggest(CONTACT, [_msg("m1", "Salut"), _msg("m2", "Bună ziua!", direction="out")], NOW).kind == "none"

    question = engine.suggest(CONTACT, [_msg("m1", "Bună, vreau etichete")], NOW)
    assert question.kind == "question"
    assert question.options == ["Rotundă, 5 cm, 500 buc", "Dreptunghiulară, 9 x 4 cm, 1000 buc", "Pe rolă, 500 buc"]
    assert chr(0x2014) not in question.text and chr(0x2014) not in question.note_for_staff

    again = engine.suggest(CONTACT, [_msg("m1", "Bună, vreau etichete")], NOW)
    assert again == question

    # Atasament neincarcat adauga indrumarea pentru panou.
    pending = engine.suggest(
        CONTACT,
        [_msg("m2", "", unuploaded=[PendingAttachment(kind="image", filename="logo.png")])],
        NOW,
    )
    assert pending.kind == "question"
    assert "Trimite fișierul la verificare" in pending.note_for_staff

    # Incarcarea atasamentului pe acelasi mesaj m2 recalculeaza sugestia.
    file_path = tmp_path / "logo.png"
    file_path.write_bytes(PNG)
    uploaded = engine.suggest(
        CONTACT,
        [_msg("m2", "", attachments=[Attachment(path=str(file_path), mime="image/png", filename="logo.png")])],
        NOW,
    )
    assert uploaded.suggestion_id != pending.suggestion_id
    assert "Trimite fișierul la verificare" not in uploaded.note_for_staff


@pytest.mark.parametrize("text, expected_reason", [
    ("Îmi faceți un discount la 1000 buc?", HandoffReason.SPECIAL_TERMS),
    ("Vreau să discut cu un coleg", HandoffReason.CUSTOMER_ASKED),
    ("Am o reclamație, comanda a ajuns greșit", HandoffReason.COMPLAINT),
])
def test_demo_assist_handoffs(tmp_path, text, expected_reason):
    engine = DemoEngine(tmp_path)
    result = engine.suggest(CONTACT, [_msg("m1", text)], NOW)
    assert result.kind == "needs_human"
    assert result.handoff_reason == expected_reason
    assert "demonstrativ" in result.note_for_staff.lower()
    assert chr(0x2014) not in result.text and chr(0x2014) not in result.note_for_staff


@pytest.mark.parametrize("text, expected_choices", [
    (
        "Rotundă, 5 cm, 500 buc",
        LineChoices(product_id=STICKER_ID, material_name="Vinil Alb Lucios", shape="circle",
                    width_cm=Decimal("5"), height_cm=Decimal("5"), quantity=500),
    ),
    (
        "Dreptunghiulară, 9 x 4 cm, 1000 buc",
        LineChoices(product_id=STICKER_ID, material_name="Vinil Alb Lucios", shape="rectangle",
                    width_cm=Decimal("9"), height_cm=Decimal("4"), quantity=1000),
    ),
    (
        "Pe rolă, 500 buc",
        LineChoices(product_id=LABEL_ID, material_name="Polipropilenă Albă", shape="circle",
                    width_cm=Decimal("5"), height_cm=Decimal("5"), quantity=500),
    ),
    (
        "Vreau o ofertă rapidă",
        LineChoices(product_id=STICKER_ID, material_name="Vinil Alb Lucios", shape="circle",
                    width_cm=Decimal("5"), height_cm=Decimal("5"), quantity=100),
    ),
    (
        "Vreau etichete dreptunghiulare, 500 buc",
        LineChoices(product_id=STICKER_ID, material_name="Vinil Alb Lucios", shape="rectangle",
                    width_cm=Decimal("9"), height_cm=Decimal("4"), quantity=500),
    ),
])
def test_demo_assist_offer_prices_come_strictly_from_fake_calculator(tmp_path, text, expected_choices):
    calc = FakeCalculator().client()
    expected_quote = calc.get_price(expected_choices)
    expected_tiers = calc.get_price_tiers(expected_choices, 2)

    engine = DemoEngine(tmp_path)
    offer = engine.suggest(CONTACT, [_msg("m1", text)], NOW)
    assert offer.kind == "offer"
    assert offer.can_create_payment_link is True
    assert offer.payment_url is None
    assert "Mod demonstrativ (prețuri din FakeCalculator, fără chei de producție)." in offer.note_for_staff
    assert chr(0x2014) not in offer.text and chr(0x2014) not in offer.note_for_staff

    main_line = offer.offer_lines[0]
    assert main_line.highlighted is True
    assert isinstance(main_line.total, Decimal) and isinstance(main_line.total_ex_vat, Decimal)
    assert main_line.quantity == expected_quote.choices.quantity
    assert main_line.total == expected_quote.total
    assert main_line.total_ex_vat == expected_quote.total_ex_vat
    assert main_line.unit_price == expected_quote.unit_price
    assert [line.total for line in offer.offer_lines[1:]] == [t.total for t in expected_tiers]


def test_demo_assist_payment_link_and_api_wiring(tmp_path):
    from ec_quote.config import load_settings
    from tests.api.conftest import base_env

    settings = load_settings(base_env(tmp_path, EC_QUOTE_DEMO="1"), require_integrations=False)
    demo = build_engine(settings)
    api = build(tmp_path, engine=demo, env={"EC_QUOTE_DEMO": "1"})

    # 1. Oferta si imagine prin API.
    res = api.client.post("/v1/assist/suggest", headers=ANA, json={
        "chat": {"key": WA_KEY, "name": "Client Demo"},
        "messages": [{"id": "m1", "direction": "in", "text": "Rotundă, 5 cm, 500 buc"}],
    })
    assert res.status_code == 200, res.text
    first = res.json()["suggestion"]
    assert first["kind"] == "offer" and first["can_create_payment_link"] is True
    assert api.client.get(first["image_url"]).headers["content-type"] == "image/png"

    # 2. Link de plata: valid, editabil si idempotent la al doilea clic.
    sid = first["suggestion_id"]
    linked_res = api.client.post(f"/v1/assist/suggestions/{sid}/payment-link", headers=ANA,
                                 json={"edited_text": "Oferta pregătită pentru dvs."})
    assert linked_res.status_code == 200, linked_res.text
    linked = linked_res.json()["suggestion"]
    expected_url = f"https://etichetecreative.ro/plata/demo-{sid}"
    assert linked["payment_url"] == expected_url
    assert linked["can_create_payment_link"] is False
    assert linked["text"].startswith("Oferta pregătită pentru dvs.")
    assert linked["text"].endswith(expected_url)

    second_click = api.client.post(f"/v1/assist/suggestions/{sid}/payment-link", headers=ANA, json={})
    assert second_click.status_code == 200
    assert second_click.json()["suggestion"] == linked

    # 3. O sugestie noua o inlocuieste pe cea veche nelegata -> 409; id necunoscut -> 404.
    second_offer = api.client.post("/v1/assist/suggest", headers=ANA, json={
        "chat": {"key": WA_KEY, "name": "Client Demo"},
        "messages": [{"id": "m2", "direction": "in", "text": "Pe rolă, 500 buc"}],
    }).json()["suggestion"]
    api.client.post("/v1/assist/suggest", headers=ANA, json={
        "chat": {"key": WA_KEY, "name": "Client Demo"},
        "messages": [{"id": "m3", "direction": "in", "text": "Bună"}],
    })

    stale = api.client.post(f"/v1/assist/suggestions/{second_offer['suggestion_id']}/payment-link", headers=ANA)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "suggestion_not_available"

    missing = api.client.post("/v1/assist/suggestions/nu-exista/payment-link", headers=ANA)
    assert missing.status_code == 404 and missing.json()["error"]["code"] == "suggestion_not_found"

    with pytest.raises(LookupError):
        demo.create_payment_link("nu-exista", "ana", NOW)
    with pytest.raises(ApprovalError):
        demo.create_payment_link(second_offer["suggestion_id"], "ana", NOW)
