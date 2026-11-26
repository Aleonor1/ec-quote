"""Chatul de pe site: sesiuni semnate, mesaje, incarcari, limite de ritm, oferta in asteptare."""
from __future__ import annotations

import base64
import json
import re
from pathlib import Path

import pytest

from ec_quote.api import texts
from ec_quote.contracts import Button, HandoffReason, OutboundAction
from tests.api.conftest import AUTH, PDF, PNG, FakeEngine, build, new_session
from tests.api.test_media_approvals import image_engine


def test_session_message_roundtrip(tmp_path):
    engine = FakeEngine([OutboundAction(kind="buttons", text="Ce material?",
                                        buttons=[Button(id="m1", title="Hartie")])])
    api = build(tmp_path, engine=engine)
    created = api.client.post("/v1/chat/session", json={"ad_source": "google:cpc"})
    assert created.status_code == 200
    data = created.json()
    assert data["expires_at"] == int(api.clock().timestamp()) + 24 * 3600
    headers = {"Authorization": "Bearer " + data["session_token"]}

    response = api.client.post("/v1/chat/message", json={"text": "Buna", "message_id": "c1"}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json() == {"poll": False, "actions": [{
        "kind": "buttons", "text": "Ce material?", "buttons": [{"id": "m1", "title": "Hartie"}],
        "image_url": None}]}
    message = engine.handled[0]
    assert message.contact.channel == "site" and re.fullmatch(r"[0-9a-f]{32}", message.contact.key)
    assert message.contact.ad_source == "google:cpc" and message.contact.phone is None
    assert message.received_at == api.clock.now and message.from_staff is False

    api.client.post("/v1/chat/message", json={"button_id": "m1"}, headers=headers)
    assert engine.handled[1].button_id == "m1"
    assert engine.handled[1].contact.key == message.contact.key


def test_session_without_body_and_alternate_header(api):
    token = api.client.post("/v1/chat/session").json()["session_token"]
    response = api.client.post("/v1/chat/message", json={"text": "Buna"}, headers={"X-EcQuote-Session": token})
    assert response.status_code == 200
    assert api.engine.handled[0].contact.ad_source is None


def test_two_sessions_are_two_conversations(api):
    one, two = new_session(api.client), new_session(api.client)
    api.client.post("/v1/chat/message", json={"text": "a"}, headers=one)
    api.client.post("/v1/chat/message", json={"text": "b"}, headers=two)
    assert api.engine.handled[0].contact.key != api.engine.handled[1].contact.key


def test_chat_message_is_idempotent_on_message_id(api):
    headers = new_session(api.client)
    body = {"text": "Buna", "message_id": "c1"}
    first = api.client.post("/v1/chat/message", json=body, headers=headers).json()
    assert api.client.post("/v1/chat/message", json=body, headers=headers).json() == first
    assert len(api.engine.handled) == 1


def _forge(token: str, **changes) -> str:
    body, sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload.update(changes)
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode() + "." + sig


def test_tampered_or_missing_session_token_is_rejected(api):
    token = new_session(api.client)["Authorization"].split(" ")[1]
    body, sig = token.split(".")
    bad_headers = [
        {},
        {"Authorization": token},
        {"Authorization": "Basic " + token},
        {"Authorization": "Bearer "},
        {"Authorization": "Bearer " + _forge(token, sid="0" * 32)},
        {"Authorization": "Bearer " + _forge(token, exp=9999999999)},
        {"Authorization": f"Bearer {body}.{sig[::-1]}"},
        {"Authorization": "Bearer " + token + "x"},
        {"X-EcQuote-Session": "abc.def"},
    ]
    for headers in bad_headers:
        for method, path, kwargs in (("post", "/v1/chat/message", {"json": {"text": "x"}}),
                                     ("post", "/v1/chat/upload", {"files": {"file": ("a.png", PNG)}}),
                                     ("get", "/v1/chat/poll", {})):
            response = getattr(api.client, method)(path, headers=headers, **kwargs)
            assert response.status_code == 401, (headers, path)
            assert response.json()["error"]["code"] == "session_invalid"
    assert api.engine.handled == []


def test_token_signed_for_another_purpose_or_with_a_bad_session_id(api):
    from ec_quote.api.security import Signer

    exp = api.clock().timestamp() + 60
    media = Signer(api.settings.signing_key("media")).sign({"sid": "a" * 32}, exp)
    odd = Signer(api.settings.signing_key("chat-session")).sign({"sid": "../../etc"}, exp)
    for token in (media, odd):
        response = api.client.post("/v1/chat/message", json={"text": "x"},
                                   headers={"Authorization": "Bearer " + token})
        assert response.status_code == 401


def test_session_expires(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_SESSION_TTL_SECONDS": "120"})
    headers = new_session(api.client)
    api.clock.advance(121)
    response = api.client.post("/v1/chat/message", json={"text": "x"}, headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "session_expired"


@pytest.mark.parametrize("body", [{}, {"text": "   "}, {"text": "x" * 5000}, {"text": "x", "altceva": 1},
                                  {"text": "x", "message_id": "cu spatiu"}])
def test_chat_message_validation(api, body):
    response = api.client.post("/v1/chat/message", json=body, headers=new_session(api.client))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


# ---------- limite de ritm ----------

def test_session_creation_is_limited_per_ip(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_SESSIONS_PER_IP_HOUR": "3"})
    for _ in range(3):
        assert api.client.post("/v1/chat/session").status_code == 200
    limited = api.client.post("/v1/chat/session")
    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert limited.headers["retry-after"] == "3600"
    api.clock.advance(3601)
    assert api.client.post("/v1/chat/session").status_code == 200


def test_messages_are_limited_per_session(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_MESSAGES_PER_SESSION_MINUTE": "2"})
    one, two = new_session(api.client), new_session(api.client)
    for _ in range(2):
        assert api.client.post("/v1/chat/message", json={"text": "x"}, headers=one).status_code == 200
    limited = api.client.post("/v1/chat/message", json={"text": "x"}, headers=one)
    assert limited.status_code == 429 and limited.headers["retry-after"] == "60"
    assert api.client.post("/v1/chat/message", json={"text": "x"}, headers=two).status_code == 200
    assert len(api.engine.handled) == 3
    api.clock.advance(30)
    assert api.client.post("/v1/chat/message", json={"text": "x"}, headers=one).headers["retry-after"] == "30"
    api.clock.advance(31)
    assert api.client.post("/v1/chat/message", json={"text": "x"}, headers=one).status_code == 200


def test_messages_are_limited_per_ip_across_sessions(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_MESSAGES_PER_IP_MINUTE": "2"})
    for _ in range(2):
        assert api.client.post("/v1/chat/message", json={"text": "x"},
                               headers=new_session(api.client)).status_code == 200
    assert api.client.post("/v1/chat/message", json={"text": "x"},
                           headers=new_session(api.client)).status_code == 429


def test_forwarded_ip_counts_only_behind_a_trusted_proxy(tmp_path):
    env = {"EC_QUOTE_RATE_SESSIONS_PER_IP_HOUR": "1"}
    direct = build(tmp_path / "a", env=env)
    assert direct.client.post("/v1/chat/session", headers={"X-Forwarded-For": "1.1.1.1"}).status_code == 200
    assert direct.client.post("/v1/chat/session", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 429

    proxied = build(tmp_path / "b", env=dict(env, EC_QUOTE_TRUSTED_PROXY_HOPS="1"))
    assert proxied.client.post("/v1/chat/session", headers={"X-Forwarded-For": "9.9.9.9, 1.1.1.1"}).status_code == 200
    assert proxied.client.post("/v1/chat/session", headers={"X-Forwarded-For": "2.2.2.2"}).status_code == 200
    assert proxied.client.post("/v1/chat/session", headers={"X-Forwarded-For": "8.8.8.8, 1.1.1.1"}).status_code == 429
    assert proxied.client.post("/v1/chat/session").status_code == 200  # fara antet: adresa conexiunii


def test_app_proxy_mode_requires_the_secret_and_trusts_its_client_ip(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_CHAT_REQUIRE_SECRET": "1", "EC_QUOTE_RATE_SESSIONS_PER_IP_HOUR": "1"})
    assert api.client.post("/v1/chat/session").status_code == 401
    assert api.client.post("/v1/chat/session", headers={"X-EcQuote-Client-IP": "1.1.1.1"}).status_code == 401
    proxy = dict(AUTH, **{"X-EcQuote-Client-IP": "1.1.1.1"})
    created = api.client.post("/v1/chat/session", headers=proxy)
    assert created.status_code == 200
    assert api.client.post("/v1/chat/session", headers=proxy).status_code == 429
    assert api.client.post("/v1/chat/session", headers=dict(proxy, **{"X-EcQuote-Client-IP": "2.2.2.2"})).status_code == 200
    session = {"Authorization": "Bearer " + created.json()["session_token"]}
    for method, path, kwargs in (("post", "/v1/chat/message", {"json": {"text": "x"}}),
                                 ("post", "/v1/chat/upload", {"files": {"file": ("a.png", PNG)}}),
                                 ("get", "/v1/chat/poll", {})):
        assert getattr(api.client, method)(path, headers=session, **kwargs).status_code == 401
        assert getattr(api.client, method)(path, headers=dict(session, **proxy), **kwargs).status_code == 200


def test_client_ip_header_is_ignored_without_the_secret(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_SESSIONS_PER_IP_HOUR": "1"})
    assert api.client.post("/v1/chat/session", headers={"X-EcQuote-Client-IP": "1.1.1.1"}).status_code == 200
    assert api.client.post("/v1/chat/session", headers={"X-EcQuote-Client-IP": "2.2.2.2"}).status_code == 429


# ---------- incarcari ----------

def test_upload_reaches_the_engine_as_an_attachment(api):
    headers = new_session(api.client)
    response = api.client.post("/v1/chat/upload", headers=headers,
                               files={"file": ("../Eticheta mea.pdf", PDF, "application/pdf")},
                               data={"text": "Fisierul meu", "message_id": "u1"})
    assert response.status_code == 200, response.text
    message = api.engine.handled[0]
    item = message.attachments[0]
    path = Path(item.path)
    assert path.parent == api.data_dir / "conversations" / "site" / message.contact.key / "inbound"
    assert path.read_bytes() == PDF and path.suffix == ".pdf"
    assert item.mime == "application/pdf" and item.filename == "Eticheta mea.pdf" and item.public_url is None
    assert message.text == "Fisierul meu"
    # Retrimiterea aceluiasi mesaj nu salveaza fisierul a doua oara.
    api.client.post("/v1/chat/upload", headers=headers, files={"file": ("a.pdf", PDF)}, data={"message_id": "u1"})
    assert len(api.engine.handled) == 1 and len(list(path.parent.iterdir())) == 1


def test_upload_type_comes_from_content(api):
    headers = new_session(api.client)
    response = api.client.post("/v1/chat/upload", headers=headers,
                               files={"file": ("poza.png", b"<html>nu</html>", "image/png")})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "attachment_type_not_allowed"
    assert api.engine.handled == []
    assert not list((api.data_dir / "conversations").rglob("*.*"))


def test_upload_over_the_cap(api):
    headers = new_session(api.client)
    just_over = PNG + b"\x00" * (1024 * 1024)
    response = api.client.post("/v1/chat/upload", headers=headers, files={"file": ("a.png", just_over)})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "upload_too_large"
    huge = PNG + b"\x00" * (2 * 1024 * 1024)
    response = api.client.post("/v1/chat/upload", headers=headers, files={"file": ("a.png", huge)})
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"
    assert api.engine.handled == []
    assert not list((api.data_dir / "conversations").rglob("*.*"))


@pytest.mark.parametrize("kwargs", [
    {"data": {"text": "fara fisier"}},
    {"files": [("file", ("a.png", PNG)), ("file", ("b.png", PNG))]},
    {"files": {"file": ("a.png", PNG)}, "data": {"message_id": "cu spatiu"}},
    {"files": {"file": ("a.png", PNG)}, "data": {"text": "x" * 5000}},
    {"json": {"file": "x"}},
])
def test_upload_validation(api, kwargs):
    response = api.client.post("/v1/chat/upload", headers=new_session(api.client), **kwargs)
    assert response.status_code in (400, 422)
    assert "error" in response.json()
    assert api.engine.handled == []


def test_uploads_are_limited_per_session(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_UPLOADS_PER_SESSION_HOUR": "1"})
    headers = new_session(api.client)
    assert api.client.post("/v1/chat/upload", headers=headers, files={"file": ("a.png", PNG)}).status_code == 200
    assert api.client.post("/v1/chat/upload", headers=headers, files={"file": ("a.png", PNG)}).status_code == 429


def test_json_body_over_the_cap_even_when_chunked(api):
    headers = new_session(api.client)

    def chunks():
        yield b'{"text": "'
        for _ in range(40):
            yield b"a" * 8192
        yield b'"}'

    response = api.client.post("/v1/chat/message", content=chunks(),
                               headers=dict(headers, **{"Content-Type": "application/json"}))
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"
    big = api.client.post("/v1/chat/message", content=b"a" * 300_000,
                          headers=dict(headers, **{"Content-Type": "application/json"}))
    assert big.status_code == 413 and big.json()["error"]["code"] == "body_too_large"
    assert api.engine.handled == []


# ---------- ce vede clientul ----------

def test_customer_texts_are_pinned():
    assert texts.PENDING_OFFER == "Pregătim oferta dumneavoastră. Revenim în câteva minute cu prețul și detaliile."
    assert texts.HANDOFF == "Conversația a fost predată unui coleg. Vă răspundem aici în cel mai scurt timp."
    for text in (texts.PENDING_OFFER, texts.HANDOFF):
        assert chr(0x2014) not in text and chr(0x2013) not in text


def test_pending_approval_never_leaks_the_offer_to_the_site_chat(tmp_path):
    engine, path = image_engine(tmp_path)
    offer_text = "Oferta: 500 buc, 250,00 lei cu TVA. Plata: https://plata.test/secret"
    engine.reply = [
        OutboundAction(kind="text", text="Am notat cererea."),
        OutboundAction(kind="pending_approval", approval_id="apr-site-1", text=offer_text,
                       image_path=str(path), buttons=[Button(id="pay", title="Platesc")]),
    ]
    engine.approvals = {"apr-site-1": [OutboundAction(kind="image", text=offer_text, image_path=str(path))]}
    api = build(tmp_path, engine=engine)
    headers = new_session(api.client)

    response = api.client.post("/v1/chat/message", json={"text": "vreau oferta"}, headers=headers)
    assert response.status_code == 200
    data = response.json()
    assert data["poll"] is True
    assert data["actions"] == [
        {"kind": "text", "text": "Am notat cererea.", "buttons": [], "image_url": None},
        {"kind": "notice", "text": texts.PENDING_OFFER, "buttons": [], "image_url": None},
    ]
    for leaked in ("250,00", "plata.test", "apr-site-1", "/v1/media/", "Platesc", "pending_approval"):
        assert leaked not in response.text

    # Pana la aprobare, clientul nu primeste nimic nici prin poll.
    assert api.client.get("/v1/chat/poll", headers=headers).json() == {"actions": [], "poll": False}

    approved = api.client.post("/v1/approvals/apr-site-1/approve", json={"by": "ana"}, headers=AUTH).json()
    assert approved["channel"] == "site" and approved["delivery"] == "site_chat"
    assert approved["key"] == engine.handled[0].contact.key

    other = new_session(api.client)
    assert api.client.get("/v1/chat/poll", headers=other).json()["actions"] == []
    delivered = api.client.get("/v1/chat/poll", headers=headers).json()
    assert delivered["poll"] is False
    assert delivered["actions"][0]["kind"] == "image" and delivered["actions"][0]["text"] == offer_text
    assert api.client.get(delivered["actions"][0]["image_url"]).content == PNG
    assert api.client.get("/v1/chat/poll", headers=headers).json()["actions"] == []
    # O aprobare retrimisa nu pune oferta a doua oara in coada.
    api.client.post("/v1/approvals/apr-site-1/approve", json={"by": "ana"}, headers=AUTH)
    assert api.client.get("/v1/chat/poll", headers=headers).json()["actions"] == []


def test_handoff_is_shown_as_a_notice_without_the_reason(tmp_path):
    engine = FakeEngine([OutboundAction(kind="handoff", handoff_reason=HandoffReason.VALUE_OVER_THRESHOLD)])
    api = build(tmp_path, engine=engine)
    headers = new_session(api.client)
    response = api.client.post("/v1/chat/message", json={"text": "x"}, headers=headers)
    assert response.json() == {"poll": True, "actions": [
        {"kind": "handoff", "text": texts.HANDOFF, "buttons": [], "image_url": None}]}
    assert "value_over_threshold" not in response.text
    engine.reply = [OutboundAction(kind="handoff", text="Va preia Ana.", handoff_reason=HandoffReason.COMPLAINT)]
    assert api.client.post("/v1/chat/message", json={"text": "y"}, headers=headers).json()["actions"][0]["text"] == "Va preia Ana."


def test_polls_are_limited_per_session(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_RATE_POLLS_PER_SESSION_MINUTE": "1"})
    headers = new_session(api.client)
    assert api.client.get("/v1/chat/poll", headers=headers).status_code == 200
    assert api.client.get("/v1/chat/poll", headers=headers).status_code == 429


def test_chunked_upload_over_the_cap_is_cut_off(api):
    headers = dict(new_session(api.client), **{"Content-Type": "multipart/form-data; boundary=XX"})

    def body():
        yield b'--XX\r\nContent-Disposition: form-data; name="file"; filename="a.png"\r\n\r\n' + PNG
        for _ in range(20):
            yield b"\x00" * (64 * 1024)
        yield b"\r\n--XX--\r\n"

    response = api.client.post("/v1/chat/upload", content=body(), headers=headers)
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "body_too_large"
    assert api.engine.handled == []
