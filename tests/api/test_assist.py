"""Modul asistat: rutele pentru extensia Chrome de pe WhatsApp Web."""
from __future__ import annotations

import logging
from decimal import Decimal
from pathlib import Path

import pytest

from ec_quote.contracts import AssistSuggestion, HandoffReason, OfferLine
from tests.api.conftest import ANA, AUTH, MIHAI, ORIGIN, PDF, PNG, WA_KEY, FakeEngine, build
from tests.api.test_media_approvals import image_engine


class FakeAssist:
    def __init__(self, suggestion=None):
        self.suggestion = suggestion or AssistSuggestion(suggestion_id="sug-1", kind="question",
                                                         text="Ce dimensiune doriti?", options=["5x5 cm", "10x10 cm"])
        self.suggested = []
        self.links = []
        self.error = None

    def suggest(self, contact, messages, now):
        self.suggested.append((contact, messages, now))
        return self.suggestion(contact, messages) if callable(self.suggestion) else self.suggestion

    def create_payment_link(self, suggestion_id, staff, now, edited_text=None):
        self.links.append((suggestion_id, staff, now, edited_text))
        if self.error:
            raise self.error
        return self.suggestion.model_copy(update={
            "suggestion_id": suggestion_id, "payment_url": "https://shop.test/invoices/abc",
            "text": (edited_text or "Oferta") + "\nPlata: https://shop.test/invoices/abc"})


def suggest_body(**chat) -> dict:
    return {
        "chat": {"key": WA_KEY, "name": "Client Test", "phone": "+40700001234", **chat},
        "messages": [
            {"id": "m1", "direction": "in", "text": "Buna, vreau etichete", "sent_at": "2026-11-26T09:00:00+02:00"},
            {"id": "m2", "direction": "out", "text": "Buna ziua!", "sent_at": None},
        ],
    }


@pytest.fixture
def assist_api(tmp_path):
    return build(tmp_path, assist=FakeAssist())


# ---------- acces ----------

ROUTES = [
    ("get", "/v1/assist/ping", {}),
    ("post", "/v1/assist/suggest", {"json": suggest_body()}),
    ("post", "/v1/assist/upload", {"files": {"file": ("a.png", PNG)}, "data": {"chat_key": WA_KEY, "message_id": "m1"}}),
    ("post", "/v1/assist/suggestions/sug-1/payment-link", {"json": {"edited_text": None}}),
]


@pytest.mark.parametrize("method, path, kwargs", ROUTES)
@pytest.mark.parametrize("headers", [{}, {"X-EcQuote-Assist-Token": "gresit"}, {"X-EcQuote-Assist-Token": ""},
                                     AUTH, {"X-EcQuote-Assist-Token": ANA["X-EcQuote-Assist-Token"] + "x"},
                                     {"X-EcQuote-Assist-Token": "ana"}])
def test_assist_routes_require_a_staff_token(assist_api, method, path, kwargs, headers):
    response = getattr(assist_api.client, method)(path, headers=headers, **kwargs)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"
    assert assist_api.assist.suggested == [] and assist_api.assist.links == []


@pytest.mark.parametrize("method, path, kwargs", ROUTES)
def test_without_configured_tokens_every_request_is_refused(tmp_path, method, path, kwargs):
    api = build(tmp_path, assist=FakeAssist(), env={"EC_QUOTE_ASSIST_TOKENS": ""})
    for headers in ({}, ANA, {"X-EcQuote-Assist-Token": ""}):
        assert getattr(api.client, method)(path, headers=headers, **kwargs).status_code == 401


def test_ping_names_the_staff_member(assist_api):
    assert assist_api.client.get("/v1/assist/ping", headers=ANA).json() == {
        "ok": True, "staff": "ana", "backend_version": "0.1.0", "min_extension_version": "",
    }
    assert assist_api.client.get("/v1/assist/ping", headers=MIHAI).json() == {
        "ok": True, "staff": "mihai", "backend_version": "0.1.0", "min_extension_version": "",
    }


def test_assist_routes_carry_no_cors_for_unknown_origins(assist_api):
    response = assist_api.client.get("/v1/assist/ping", headers=dict(ANA, Origin="chrome-extension://abcdef"))
    assert response.status_code == 200 and "access-control-allow-origin" not in response.headers
    preflight = assist_api.client.options("/v1/assist/suggest", headers={
        "Origin": ORIGIN, "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-ecquote-assist-token"})
    assert preflight.status_code == 400  # antetul tokenului nu este permis din browser


def test_assist_is_unavailable_without_an_assist_engine(tmp_path):
    api = build(tmp_path)  # FakeEngine nu are suggest
    assert api.client.get("/v1/assist/ping", headers=ANA).status_code == 200
    for path, body in (("/v1/assist/suggest", suggest_body()),
                       ("/v1/assist/suggestions/sug-1/payment-link", {"edited_text": None})):
        response = api.client.post(path, json=body, headers=ANA)
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "assist_unavailable"


def test_engine_that_implements_suggest_is_used_as_assist_engine(tmp_path):
    class Both(FakeEngine, FakeAssist):
        def __init__(self):
            FakeEngine.__init__(self)
            FakeAssist.__init__(self)

    api = build(tmp_path, engine=Both())
    assert api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA).status_code == 200
    assert len(api.engine.suggested) == 1


# ---------- sugestie ----------

def test_suggest_passes_the_conversation_and_returns_the_suggestion(assist_api):
    response = assist_api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    assert response.status_code == 200, response.text
    assert response.json() == {"suggestion": {
        "suggestion_id": "sug-1", "kind": "question", "text": "Ce dimensiune doriti?",
        "options": ["5x5 cm", "10x10 cm"], "image_url": None, "note_for_staff": "", "handoff_reason": None,
        "offer_lines": [], "can_create_payment_link": False, "payment_url": None}}
    contact, messages, now = assist_api.assist.suggested[0]
    assert contact.channel == "whatsapp" and contact.key == WA_KEY
    assert contact.name == "Client Test" and contact.phone == "+40700001234"
    assert [(m.id, m.direction, m.text) for m in messages] == [
        ("m1", "in", "Buna, vreau etichete"), ("m2", "out", "Buna ziua!")]
    assert messages[0].sent_at.isoformat() == "2026-11-26T09:00:00+02:00" and messages[1].sent_at is None
    assert now == assist_api.clock.now


def test_offer_suggestion_has_signed_image_and_money_as_text(tmp_path):
    _, path = image_engine(tmp_path)
    assist = FakeAssist(AssistSuggestion(
        suggestion_id="sug-9", kind="offer", text="Oferta: 250,00 lei", image_path=str(path),
        note_for_staff="Fisier slab: 180 dpi", handoff_reason=HandoffReason.VALUE_OVER_THRESHOLD,
        can_create_payment_link=True,
        offer_lines=[OfferLine(label="500 buc", quantity=500, total_ex_vat=Decimal("206.61"),
                               total=Decimal("250.00"), unit_price=Decimal("0.50"), highlighted=True)]))
    api = build(tmp_path, assist=assist)
    data = api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA).json()["suggestion"]
    assert "image_path" not in data and str(tmp_path) not in str(data)
    assert api.client.get(data["image_url"]).content == PNG
    assert data["handoff_reason"] == "value_over_threshold" and data["can_create_payment_link"] is True
    assert data["note_for_staff"] == "Fisier slab: 180 dpi"
    assert data["offer_lines"] == [{"label": "500 buc", "quantity": 500, "total_ex_vat": "206.61",
                                    "total": "250.00", "unit_price": "0.50", "highlighted": True}]


def test_only_the_last_40_messages_reach_the_engine_and_long_text_is_cut(assist_api):
    body = suggest_body()
    body["messages"] = [{"id": f"m{i}", "direction": "in", "text": "x" * 5000, "sent_at": "2026-11-26T09:00:00"}
                        for i in range(45)]
    assert assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA).status_code == 200
    messages = assist_api.assist.suggested[0][1]
    assert [m.id for m in messages] == [f"m{i}" for i in range(5, 45)]
    assert all(len(m.text) == 4096 for m in messages)
    assert messages[0].sent_at.utcoffset().total_seconds() == 0  # fara fus orar: UTC


def test_chat_key_may_be_a_stable_chat_id(assist_api):
    body = suggest_body(key="40700001234@c.us")
    assert assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA).status_code == 200
    assert assist_api.assist.suggested[0][0].key == "40700001234@c.us"


@pytest.mark.parametrize("change", [
    {"chat": {"key": "../etc"}},
    {"chat": {"key": ".."}},
    {"chat": {"key": "a/b"}},
    {"chat": {"key": ""}},
    {"chat": {"key": WA_KEY, "altceva": 1}},
    {"messages": [{"id": "m1", "direction": "sus", "text": "x"}]},
    {"messages": [{"id": "", "direction": "in"}]},
    {"messages": [{"id": "m1", "direction": "in", "attachments": [{"upload_id": "../x"}]}]},
    {"messages": [{"id": "m1", "direction": "in", "attachments": [{"upload_id": "a" * 32}] * 6}]},
    {"messages": "nu"},
])
def test_suggest_validation(assist_api, change):
    response = assist_api.client.post("/v1/assist/suggest", json=dict(suggest_body(), **change), headers=ANA)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
    assert assist_api.assist.suggested == []


def test_suggest_body_may_be_larger_than_other_json_bodies(assist_api):
    body = suggest_body()
    body["messages"] = [{"id": f"m{i}", "direction": "in", "text": "x" * 20000} for i in range(40)]
    assert assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA).status_code == 200
    body["messages"] = [{"id": f"m{i}", "direction": "in", "text": "x" * 60000} for i in range(40)]
    assert assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA).status_code == 413


def test_engine_failure_is_a_plain_500(tmp_path):
    def boom(contact, messages):
        raise RuntimeError(f"model cazut pentru {WA_KEY}")

    api = build(tmp_path, assist=FakeAssist(boom))
    response = api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    assert response.status_code == 500 and "model" not in response.text


# ---------- incarcari ----------

def upload(api, *, chat_key=WA_KEY, message_id="m1", name="logo.pdf", content=PDF, headers=ANA):
    return api.client.post("/v1/assist/upload", headers=headers, files={"file": (name, content)},
                           data={"chat_key": chat_key, "message_id": message_id})


def test_upload_then_suggest_resolves_the_attachment(assist_api):
    response = upload(assist_api, name="../Logo client.pdf")
    assert response.status_code == 200, response.text
    upload_id = response.json()["upload_id"]
    assert set(response.json()) == {"upload_id"} and len(upload_id) == 32

    body = suggest_body()
    body["messages"][0]["attachments"] = [{"upload_id": upload_id}]
    assert assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA).status_code == 200
    item = assist_api.assist.suggested[0][1][0].attachments[0]
    path = Path(item.path)
    assert path.parent == assist_api.data_dir / "conversations" / "whatsapp" / WA_KEY / "inbound"
    assert path.read_bytes() == PDF and item.mime == "application/pdf" and item.filename == "Logo client.pdf"


def test_upload_is_idempotent_on_chat_message_and_filename(assist_api):
    first = upload(assist_api).json()["upload_id"]
    assert upload(assist_api, headers=MIHAI).json()["upload_id"] == first
    folder = assist_api.data_dir / "conversations" / "whatsapp" / WA_KEY / "inbound"
    assert len(list(folder.iterdir())) == 1
    others = {upload(assist_api, message_id="m2").json()["upload_id"],
              upload(assist_api, name="alt.pdf").json()["upload_id"],
              upload(assist_api, chat_key="40700009999").json()["upload_id"]}
    assert len(others | {first}) == 4
    # Fisierul sters de pe disc se salveaza din nou sub acelasi id.
    for item in folder.iterdir():
        item.unlink()
    assert upload(assist_api).json()["upload_id"] == first
    assert len(list(folder.iterdir())) == 1


def test_upload_of_another_chat_cannot_be_referenced(assist_api):
    upload_id = upload(assist_api, chat_key="40700009999").json()["upload_id"]
    body = suggest_body()
    body["messages"][0]["attachments"] = [{"upload_id": upload_id}]
    response = assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_upload"
    assert assist_api.assist.suggested == []


def test_upload_type_and_size_checks(assist_api):
    bad = upload(assist_api, name="poza.png", content=b"<html>nu</html>")
    assert bad.status_code == 415 and bad.json()["error"]["code"] == "attachment_type_not_allowed"
    big = upload(assist_api, content=PNG + b"\x00" * (1024 * 1024))
    assert big.status_code == 413 and big.json()["error"]["code"] == "upload_too_large"
    huge = upload(assist_api, content=PNG + b"\x00" * (2 * 1024 * 1024))
    assert huge.status_code == 413 and huge.json()["error"]["code"] == "body_too_large"
    assert not list((assist_api.data_dir / "conversations").rglob("*.*"))


@pytest.mark.parametrize("kwargs", [
    {"data": {"chat_key": WA_KEY, "message_id": "m1"}},
    {"files": {"file": ("a.png", PNG)}, "data": {"chat_key": "../x", "message_id": "m1"}},
    {"files": {"file": ("a.png", PNG)}, "data": {"chat_key": WA_KEY}},
    {"files": {"file": ("a.png", PNG)}, "data": {"chat_key": WA_KEY, "message_id": "cu spatiu"}},
    {"files": {"file": ("a.png", PNG)}, "data": {"message_id": "m1"}},
])
def test_upload_validation(assist_api, kwargs):
    response = assist_api.client.post("/v1/assist/upload", headers=ANA, **kwargs)
    assert response.status_code == 422
    assert not list((assist_api.data_dir / "conversations").rglob("*.*"))


# ---------- link de plata ----------

def test_payment_link_returns_the_suggestion_with_the_url(assist_api):
    assist_api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    response = assist_api.client.post("/v1/assist/suggestions/sug-1/payment-link",
                                      json={"edited_text": "Oferta corectata"}, headers=MIHAI)
    assert response.status_code == 200, response.text
    data = response.json()["suggestion"]
    assert data["payment_url"] == "https://shop.test/invoices/abc" and data["suggestion_id"] == "sug-1"
    assert data["text"].startswith("Oferta corectata")
    assert assist_api.assist.links == [("sug-1", "mihai", assist_api.clock.now, "Oferta corectata")]


@pytest.mark.parametrize("kwargs", [{}, {"json": {}}, {"json": {"edited_text": None}}])
def test_payment_link_without_edited_text(assist_api, kwargs):
    response = assist_api.client.post("/v1/assist/suggestions/sug-7/payment-link", headers=ANA, **kwargs)
    assert response.status_code == 200
    assert assist_api.assist.links[0][3] is None


class ApprovalError(Exception):
    """Acelasi nume ca eroarea din modulul agent."""


@pytest.mark.parametrize("error, status, code", [
    (KeyError("sug-1"), 404, "suggestion_not_found"),
    (ApprovalError("sugestie necunoscuta: sug-1"), 404, "suggestion_not_found"),
    (ApprovalError("oferta a expirat; trebuie refacuta"), 409, "suggestion_not_available"),
    (RuntimeError("shopify cazut"), 500, "internal_error"),
])
def test_payment_link_errors(assist_api, error, status, code):
    assist_api.assist.error = error
    response = assist_api.client.post("/v1/assist/suggestions/sug-1/payment-link", json={}, headers=ANA)
    assert response.status_code == status
    assert response.json()["error"]["code"] == code
    assert "expirat" not in response.text and "shopify" not in response.text


def test_payment_link_with_a_malformed_id_or_body(assist_api):
    assert assist_api.client.post("/v1/assist/suggestions/id cu spatii/payment-link", json={},
                                  headers=ANA).status_code == 404
    assert assist_api.client.post("/v1/assist/suggestions/sug-1/payment-link", json={"altceva": 1},
                                  headers=ANA).status_code == 422
    assert assist_api.assist.links == []


# ---------- limite si loguri ----------

def test_rate_limit_is_per_token(tmp_path):
    api = build(tmp_path, assist=FakeAssist(), env={"EC_QUOTE_RATE_ASSIST_PER_TOKEN_MINUTE": "2"})
    assert api.client.get("/v1/assist/ping", headers=ANA).status_code == 200
    assert api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA).status_code == 200
    limited = api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
    assert api.client.get("/v1/assist/ping", headers=MIHAI).status_code == 200
    api.clock.advance(61)
    assert api.client.get("/v1/assist/ping", headers=ANA).status_code == 200


def test_logs_have_staff_name_and_hashed_chat_key_only(assist_api, caplog):
    from ec_quote.api.logutil import contact_ref

    caplog.set_level(logging.INFO, logger="ec_quote.api")
    upload(assist_api)
    assist_api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    assist_api.client.post("/v1/assist/suggestions/sug-1/payment-link", json={}, headers=ANA)
    assist_api.client.post("/v1/assist/suggestions/sug-x/payment-link", json={}, headers=ANA)
    text = "\n".join(r.getMessage() for r in caplog.records)
    ref = contact_ref(WA_KEY, assist_api.settings.signing_key("log-ref"))
    assert f"assist upload staff=ana contact={ref}" in text
    assert f"assist suggest staff=ana contact={ref} messages=2 kind=question" in text
    assert f"assist payment link staff=ana contact={ref}" in text
    assert "assist payment link staff=ana contact=-" in text
    for private in (WA_KEY, "Client Test", "vreau etichete", "token-ana", "logo.pdf"):
        assert private not in text


def test_suggest_and_inbound_share_the_conversation_lock(tmp_path):
    import asyncio
    import threading

    import httpx

    from tests.api.conftest import inbound_body

    events = []
    entered, release = threading.Event(), threading.Event()

    def slow_suggest(contact, messages):
        events.append("start suggest")
        entered.set()
        assert release.wait(10)
        events.append("end suggest")
        return AssistSuggestion(suggestion_id="s", kind="none")

    def handle(message):
        events.append("handle")
        return []

    api = build(tmp_path, engine=FakeEngine(handle), assist=FakeAssist(slow_suggest))

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),
                                     base_url="https://quote.test") as client:
            first = asyncio.create_task(client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA))
            assert await asyncio.to_thread(entered.wait, 10)
            second = asyncio.create_task(client.post("/v1/inbound", json=inbound_body(), headers=AUTH))
            assert (await client.get("/v1/assist/ping", headers=ANA)).status_code == 200
            assert events == ["start suggest"]
            release.set()
            return await asyncio.gather(first, second)

    assert [r.status_code for r in asyncio.run(scenario())] == [200, 200]
    assert events == ["start suggest", "end suggest", "handle"]


# ---------- citate, atasamente neincarcate, origine si versiune ----------

def test_suggest_maps_quoted_text_and_unuploaded_attachments(assist_api):
    body = suggest_body()
    body["messages"] = [
        {
            "id": "m1",
            "direction": "in",
            "text": "Asa vreau si eu",
            "quoted_text": "Oferta 500 buc: 302,50 lei",
            "unuploaded_attachments": [
                {"kind": "image", "filename": "../Logo client.png"},
                {"kind": "document"},
            ],
        },
        {"id": "m2", "direction": "in", "text": "Multumesc", "quoted_text": ""},
    ]
    response = assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA)
    assert response.status_code == 200, response.text
    first, second = assist_api.assist.suggested[0][1]
    assert first.quoted_text == "Oferta 500 buc: 302,50 lei"
    assert [(u.kind, u.filename) for u in first.unuploaded_attachments] == [
        ("image", "Logo client.png"),
        ("document", None),
    ]
    assert second.quoted_text is None and second.unuploaded_attachments == []


@pytest.mark.parametrize("message_extra", [
    {"quoted_text": "x" * 1001},
    {"unuploaded_attachments": [{"kind": "video"}]},
    {"unuploaded_attachments": [{"kind": "image", "extra": 1}]},
    {"unuploaded_attachments": [{"kind": "image"}] * 6},
])
def test_suggest_validates_quoted_text_and_unuploaded_attachments(assist_api, message_extra):
    body = suggest_body()
    body["messages"] = [{"id": "m1", "direction": "in", "text": "x", **message_extra}]
    response = assist_api.client.post("/v1/assist/suggest", json=body, headers=ANA)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_extension_origin_allowlist_and_cors(tmp_path):
    ext = "chrome-extension://abcdefghijklmnopabcdefghijklmnop"
    api = build(tmp_path, assist=FakeAssist(), env={"EC_QUOTE_EXTENSION_ORIGINS": ext})

    ok = api.client.get("/v1/assist/ping", headers=dict(ANA, Origin=ext))
    assert ok.status_code == 200
    assert ok.headers["access-control-allow-origin"] == ext

    preflight = api.client.options("/v1/assist/suggest", headers={
        "Origin": ext,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type,x-ecquote-assist-token,x-ecquote-extension-version",
    })
    assert preflight.status_code == 200
    assert preflight.headers["access-control-allow-origin"] == ext

    site_preflight = api.client.options("/v1/assist/suggest", headers={
        "Origin": ORIGIN,
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "x-ecquote-assist-token",
    })
    assert site_preflight.status_code == 400

    for bad_origin in ("chrome-extension://altid", ORIGIN, "https://evil.test"):
        denied = api.client.post("/v1/assist/suggest", json=suggest_body(), headers=dict(ANA, Origin=bad_origin))
        assert denied.status_code == 403
        assert denied.json()["error"]["code"] == "forbidden_origin"
        assert denied.json()["error"]["message"] == "Origine nepermisa."

    no_origin = api.client.post("/v1/assist/suggest", json=suggest_body(), headers=ANA)
    assert no_origin.status_code == 200


def test_min_extension_version_blocks_assist_actions_but_allows_ping(tmp_path):
    api = build(tmp_path, assist=FakeAssist(), env={"EC_QUOTE_MIN_EXTENSION_VERSION": "0.2.0"})

    # ping trece mereu pentru a raporta versiunea minima.
    for headers in (ANA, dict(ANA, **{"X-EcQuote-Extension-Version": "0.1.0"})):
        ping = api.client.get("/v1/assist/ping", headers=headers)
        assert ping.status_code == 200
        assert ping.json()["min_extension_version"] == "0.2.0"
        assert ping.json()["backend_version"] == "0.1.0"

    for bad_version in (None, "", "0.1.9", "v0.2.0", "0.2", "invalid"):
        hdrs = dict(ANA) if bad_version is None else dict(ANA, **{"X-EcQuote-Extension-Version": bad_version})
        for path, kwargs in (
            ("/v1/assist/suggest", {"json": suggest_body()}),
            ("/v1/assist/upload", {"files": {"file": ("a.png", PNG)}, "data": {"chat_key": WA_KEY, "message_id": "m1"}}),
            ("/v1/assist/suggestions/sug-1/payment-link", {"json": {}}),
        ):
            res = api.client.post(path, headers=hdrs, **kwargs)
            assert res.status_code == 426
            err = res.json()["error"]
            assert err["code"] == "extension_update_required"
            assert err["message"] == "Actualizati extensia."
            assert err["min_extension_version"] == "0.2.0"

    for good_version in ("0.2.0", "0.10.0", "1.0.0"):
        hdrs = dict(ANA, **{"X-EcQuote-Extension-Version": good_version})
        assert api.client.post("/v1/assist/suggest", json=suggest_body(), headers=hdrs).status_code == 200


@pytest.mark.parametrize("env_extra, var_name", [
    ({"EC_QUOTE_MIN_EXTENSION_VERSION": "v1.0.0"}, "EC_QUOTE_MIN_EXTENSION_VERSION"),
    ({"EC_QUOTE_MIN_EXTENSION_VERSION": "1.0"}, "EC_QUOTE_MIN_EXTENSION_VERSION"),
    ({"EC_QUOTE_EXTENSION_ORIGINS": "https://etichetecreative.ro"}, "EC_QUOTE_EXTENSION_ORIGINS"),
    ({"EC_QUOTE_EXTENSION_ORIGINS": "chrome-extension://abcdef/"}, "EC_QUOTE_EXTENSION_ORIGINS"),
    ({"EC_QUOTE_EXTENSION_ORIGINS": "*"}, "EC_QUOTE_EXTENSION_ORIGINS"),
])
def test_extension_settings_validation(tmp_path, env_extra, var_name):
    from ec_quote.config import SettingsError, load_settings
    from tests.api.conftest import base_env

    with pytest.raises(SettingsError) as exc:
        load_settings(base_env(tmp_path, **env_extra), require_integrations=False)
    assert var_name in str(exc.value)

