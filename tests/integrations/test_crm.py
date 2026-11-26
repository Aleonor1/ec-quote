from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal

import httpx
import pytest

from ec_quote.contracts import Button, Checkout, CrmPort, HandoffPort, HandoffReason, OutboundAction
from ec_quote.integrations import (
    CrmClient,
    CrmNotConfigured,
    CrmProtocolError,
    CrmRejected,
    CrmUnauthorized,
    CrmUnavailable,
    is_business_hours,
    load_business_hours,
)
from ec_quote.integrations.crm import idempotency_key, mask
from tests.integrations.helpers import DRAFT_GID, INVOICE_URL, Recorder, body_of, make_contact, make_quote

SECRET = "bridge-secret-value"
HOURS = {"start": "09:00", "end": "18:00", "days": [1, 2, 3, 4, 5]}
THURSDAY_NOON = datetime(2026, 11, 26, 12, 0)
THURSDAY_NIGHT = datetime(2026, 11, 26, 21, 30)
SATURDAY_NOON = datetime(2026, 11, 28, 12, 0)


def make(responses, sleeps=None):
    recorder = Recorder(responses)
    sleeps = sleeps if sleeps is not None else []
    client = CrmClient("https://crm.test/", SECRET, recorder.client(), business_hours=HOURS, sleep=sleeps.append)
    return client, recorder


def lead_ok(**extra) -> httpx.Response:
    return httpx.Response(200, json={"lead_id": 812, "created": True, "existing_customer": False, **extra})


def test_implements_both_ports():
    client, _ = make([])
    crm: CrmPort = client
    handoff: HandoffPort = client
    assert crm is handoff


def test_upsert_lead_sends_contact_offer_and_status():
    client, rec = make([lead_ok()])
    checkout = Checkout(draft_order_id=DRAFT_GID, invoice_url=INVOICE_URL, total=Decimal("217.00"))
    lead_id = client.upsert_lead(make_contact(), "100 stickere 6x6", make_quote(), checkout, "link_sent")

    assert lead_id == "812"
    (request,) = rec.requests
    assert request.method == "PUT"
    assert str(request.url) == "https://crm.test/api/ec-quote/leads"
    assert request.headers["Authorization"] == f"Bearer {SECRET}"
    assert len(request.headers["Idempotency-Key"]) == 64
    body = body_of(request)
    assert body["contact"] == {"channel": "whatsapp", "key": "40722123456", "phone": "+40722123456",
                               "name": "Ana", "email": None, "ad_source": "meta ads, vara"}
    assert body["status"] == "link_sent"
    assert body["summary"] == "100 stickere 6x6"
    offer = body["offer"]
    assert offer["total"] == "217.00" and offer["total_ex_vat"] == "179.34"  # bani ca text
    assert offer["quantity"] == 100 and offer["width_cm"] == "6"
    assert offer["draft_order_id"] == DRAFT_GID and offer["invoice_url"] == INVOICE_URL
    assert offer["properties"][0] == {"name": "_Sticker Quantity", "value": "100"}


def test_upsert_lead_without_offer_and_idempotency_is_stable():
    client, rec = make([lead_ok(created=False), lead_ok(created=False), lead_ok()])
    client.upsert_lead(make_contact(), "intrebare", None, None, "new")
    client.upsert_lead(make_contact(), "intrebare", None, None, "new")
    client.upsert_lead(make_contact(), "intrebare", None, None, "quoted")
    assert body_of(rec.requests[0])["offer"] is None
    keys = [r.headers["Idempotency-Key"] for r in rec.requests]
    assert keys[0] == keys[1] != keys[2]


def test_upsert_lead_checkout_only_offer_and_long_summary():
    client, rec = make([lead_ok()])
    checkout = Checkout(draft_order_id=DRAFT_GID, invoice_url=INVOICE_URL, total=Decimal("10"))
    client.upsert_lead(make_contact(), "x" * 5000, None, checkout, "link_sent")
    body = body_of(rec.requests[0])
    assert len(body["summary"]) == 2000
    assert body["offer"] == {"currency": "RON", "draft_order_id": DRAFT_GID,
                             "invoice_url": INVOICE_URL, "checkout_total": "10"}


@pytest.mark.parametrize("payload", [{}, {"lead_id": None}, {"lead_id": ""}, {"lead_id": True}])
def test_upsert_lead_without_id_is_a_protocol_error(payload):
    client, _ = make([httpx.Response(200, json=payload)])
    with pytest.raises(CrmProtocolError):
        client.upsert_lead(make_contact(), "s", None, None, "new")


def test_retry_once_on_network_error_with_the_same_key():
    sleeps: list[float] = []
    client, rec = make([httpx.ConnectError("down"), lead_ok()], sleeps)
    assert client.upsert_lead(make_contact(), "s", None, None, "new") == "812"
    assert len(rec.requests) == 2 and sleeps == [0.5]
    assert rec.requests[0].headers["Idempotency-Key"] == rec.requests[1].headers["Idempotency-Key"]


def test_unavailable_after_two_attempts():
    client, rec = make([httpx.Response(502), httpx.ReadTimeout("slow")])
    with pytest.raises(CrmUnavailable):
        client.upsert_lead(make_contact(), "s", None, None, "new")
    assert len(rec.requests) == 2
    client, _ = make([httpx.Response(500), httpx.Response(500)])
    with pytest.raises(CrmUnavailable):
        client.upsert_lead(make_contact(), "s", None, None, "new")


@pytest.mark.parametrize("response, error", [
    (httpx.Response(401, json={"error": "Token"}), CrmUnauthorized),
    (httpx.Response(403), CrmUnauthorized),
    (httpx.Response(503, json={"error": "not configured"}), CrmNotConfigured),
    (httpx.Response(302), CrmProtocolError),
    (httpx.Response(200, text="<html>"), CrmProtocolError),
    (httpx.Response(200, json=[1]), CrmProtocolError),
])
def test_error_mapping(response, error):
    client, rec = make([response])
    with pytest.raises(error):
        client.upsert_lead(make_contact(), "s", None, None, "new")
    assert len(rec.requests) == 1  # fara reincercare pe erori definitive


def test_business_rejection_keeps_code_and_details():
    client, _ = make([httpx.Response(409, json={"error": "do_not_contact", "lead_id": 5}),
                      httpx.Response(400, text="bad")])
    with pytest.raises(CrmRejected) as info:
        client.upsert_lead(make_contact(), "s", None, None, "new")
    assert (info.value.status_code, info.value.code, info.value.details) == (409, "do_not_contact", {"lead_id": 5})
    with pytest.raises(CrmRejected) as info:
        client.upsert_lead(make_contact(), "s", None, None, "new")
    assert info.value.code == "error"


def test_handoff_in_business_hours_notifies():
    client, rec = make([httpx.Response(204)])
    client.handoff(make_contact(), HandoffReason.VALUE_OVER_THRESHOLD, "peste prag", THURSDAY_NOON)
    (request,) = rec.requests
    assert request.method == "POST" and request.url.path == "/api/ec-quote/handoffs"
    body = body_of(request)
    assert body["reason"] == "value_over_threshold"
    assert body["notify"] is True
    assert body["summary"] == "peste prag"
    assert body["occurred_at"] == "2026-11-26T12:00:00"
    assert body["contact"]["key"] == "40722123456"


@pytest.mark.parametrize("now", [THURSDAY_NIGHT, SATURDAY_NOON])
def test_handoff_outside_business_hours_only_marks(now):
    client, rec = make([httpx.Response(200, json={"notified": False})])
    client.handoff(make_contact(), HandoffReason.CUSTOMER_ASKED, "vrea om", now)
    assert body_of(rec.requests[0])["notify"] is False


def test_business_hours_boundaries_and_timezone():
    assert is_business_hours(datetime(2026, 11, 26, 9, 0), HOURS)
    assert not is_business_hours(datetime(2026, 11, 26, 18, 0), HOURS)
    assert not is_business_hours(datetime(2026, 11, 26, 8, 59), HOURS)
    # 08:30 UTC = 10:30 la Bucuresti (iarna); 16:30 UTC = 18:30
    assert is_business_hours(datetime(2026, 11, 26, 8, 30, tzinfo=timezone.utc), HOURS)
    assert not is_business_hours(datetime(2026, 11, 26, 16, 30, tzinfo=timezone.utc), HOURS)


def test_business_hours_default_from_rules():
    hours = load_business_hours()
    assert set(hours) == {"start", "end", "days"}
    client = CrmClient("https://crm.test", SECRET, httpx.Client())
    assert client._hours == hours


def test_deliver_text_and_buttons():
    client, rec = make([httpx.Response(200, json={"message_id": 9, "over_cap": False})] * 2)
    text = OutboundAction(kind="text", text="Buna ziua")
    assert client.deliver(make_contact(), text, "m1") == {"message_id": 9, "over_cap": False}
    buttons = OutboundAction(kind="buttons", text="Alegeti", buttons=[Button(id="ok", title="Da")])
    client.deliver(make_contact(), buttons, "m2")
    first, second = (body_of(r) for r in rec.requests)
    assert rec.requests[0].url.path == "/api/ec-quote/messages"
    assert first["kind"] == "text" and first["text"] == "Buna ziua" and first["buttons"] == []
    assert second["buttons"] == [{"id": "ok", "title": "Da"}]
    assert rec.requests[0].headers["Idempotency-Key"] != rec.requests[1].headers["Idempotency-Key"]


def test_deliver_image_by_url_and_by_upload(tmp_path):
    image = tmp_path / "oferta.png"
    image.write_bytes(b"\x89PNG-fake")
    client, rec = make([httpx.Response(200, json={})] * 2)
    client.deliver(make_contact(), OutboundAction(kind="image", text="Oferta", image_path=str(image)), "m1",
                   image_url="https://cdn.test/oferta.png")
    assert body_of(rec.requests[0])["image_url"] == "https://cdn.test/oferta.png"

    client.deliver(make_contact(), OutboundAction(kind="image", text="Oferta", image_path=str(image)), "m2")
    upload = rec.requests[1]
    assert upload.headers["Content-Type"].startswith("multipart/form-data")
    assert b"\x89PNG-fake" in upload.content and b'filename="oferta.png"' in upload.content
    assert b'"kind": "image"' in upload.content


def test_deliver_rejections():
    client, _ = make([httpx.Response(409, json={"error": "service_cap_reached"})])
    with pytest.raises(CrmRejected) as info:
        client.deliver(make_contact(), OutboundAction(kind="text", text="x"), "m1")
    assert info.value.code == "service_cap_reached"
    with pytest.raises(ValueError):
        client.deliver(make_contact(), OutboundAction(kind="handoff"), "m2")
    with pytest.raises(ValueError):
        client.deliver(make_contact(), OutboundAction(kind="image"), "m3")


def test_request_approval():
    client, rec = make([httpx.Response(201, json={"approval_id": "ap-1"})])
    result = client.request_approval(make_contact(), "ap-1", "Oferta: 217 lei", make_quote(), "https://cdn.test/o.png")
    assert result == {"approval_id": "ap-1"}
    body = body_of(rec.requests[0])
    assert rec.requests[0].url.path == "/api/ec-quote/approvals"
    assert body["approval_id"] == "ap-1" and body["offer"]["total"] == "217.00"
    assert rec.requests[0].headers["Idempotency-Key"] == idempotency_key("approval", "ap-1")


def test_fetch_media(tmp_path):
    client, rec = make([httpx.Response(200, content=b"%PDF-1.7"), httpx.Response(200, content=b"x"),
                        httpx.Response(404, json={"error": "not_found"})])
    path = client.fetch_media("4411", str(tmp_path / "in"), "../../logo.pdf")
    assert path == str(tmp_path / "in" / "4411-logo.pdf")
    assert (tmp_path / "in" / "4411-logo.pdf").read_bytes() == b"%PDF-1.7"
    assert rec.requests[0].method == "GET" and rec.requests[0].url.path == "/api/ec-quote/media/4411"
    assert "Idempotency-Key" not in rec.requests[0].headers
    assert client.fetch_media("77", str(tmp_path)) == str(tmp_path / "77")
    with pytest.raises(CrmRejected):
        client.fetch_media("78", str(tmp_path))
    with pytest.raises(ValueError):
        client.fetch_media("../", str(tmp_path))


def test_ping():
    client, rec = make([httpx.Response(200, json={"status": "ok"}), httpx.Response(500), httpx.ConnectError("x")])
    assert client.ping() is True
    assert rec.requests[0].url.path == "/api/health"
    assert client.ping() is False
    assert client.ping() is False


def test_secret_and_phone_never_reach_the_log(caplog):
    client, _ = make([lead_ok(), httpx.Response(204)])
    with caplog.at_level(logging.DEBUG):
        client.upsert_lead(make_contact(), "s", None, None, "new")
        client.handoff(make_contact(), HandoffReason.COMPLAINT, "s", THURSDAY_NOON)
    assert SECRET not in caplog.text and SECRET not in repr(client)
    assert "40722123456" not in caplog.text
    assert "***456" in caplog.text


def test_constructor_and_helpers():
    with pytest.raises(ValueError):
        CrmClient("", SECRET, httpx.Client())
    assert mask(None) == "?" and mask("ab") == "***"
    assert json.loads(json.dumps(idempotency_key("a", None, 1))) == idempotency_key("a", "", "1")
