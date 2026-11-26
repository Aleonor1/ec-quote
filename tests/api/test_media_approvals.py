"""Linkuri media semnate si aprobarile din modul umbra."""
from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from ec_quote.api.security import Signer
from ec_quote.contracts import OutboundAction
from tests.api.conftest import AUTH, PNG, WA_KEY, FakeEngine, build, inbound_body, new_session


def image_engine(tmp_path, name="oferta.png", content=PNG, inside=True) -> tuple[FakeEngine, Path]:
    root = tmp_path / "data" if inside else tmp_path / "altundeva"
    path = root / "conversations" / "whatsapp" / WA_KEY / "out" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return FakeEngine([OutboundAction(kind="image", text="Oferta", image_path=str(path))]), path


def image_url(api) -> str:
    response = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert response.status_code == 200, response.text
    return response.json()["actions"][0]["image_url"]


def test_image_is_served_through_a_signed_url(tmp_path):
    engine, path = image_engine(tmp_path)
    api = build(tmp_path, engine=engine)
    url = image_url(api)
    assert url.startswith("https://quote.test/v1/media/")
    assert str(tmp_path) not in url
    response = api.client.get(url)
    assert response.status_code == 200
    assert response.content == PNG and response.headers["content-type"] == "image/png"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_public_base_url_setting_is_used(tmp_path):
    engine, _ = image_engine(tmp_path)
    api = build(tmp_path, engine=engine, env={"EC_QUOTE_PUBLIC_BASE_URL": "https://oferta.exemplu.ro/"})
    assert image_url(api).startswith("https://oferta.exemplu.ro/v1/media/")


def test_signed_url_expires(tmp_path):
    engine, _ = image_engine(tmp_path)
    api = build(tmp_path, engine=engine, env={"EC_QUOTE_MEDIA_URL_TTL_SECONDS": "600"})
    url = image_url(api)
    api.clock.advance(599)
    assert api.client.get(url).status_code == 200
    api.clock.advance(1)
    expired = api.client.get(url)
    assert expired.status_code == 410
    assert expired.json()["error"]["code"] == "media_expired"


def _tamper_payload(token: str, **changes) -> str:
    body, sig = token.split(".")
    payload = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    payload.update(changes)
    forged = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
    return f"{forged}.{sig}"


def test_tampered_media_tokens_are_rejected(tmp_path):
    engine, _ = image_engine(tmp_path)
    api = build(tmp_path, engine=engine)
    url = image_url(api)
    base, token = url.rsplit("/", 1)
    body, sig = token.split(".")
    forged = [
        _tamper_payload(token, p="api.sqlite3"),
        _tamper_payload(token, exp=9999999999),
        f"{body}.{sig[:-2]}AA",
        f"{body}.",
        body,
        f"{body}.{sig}.{sig}",
        f"{body}.%%%",
        "x" * 3000,
    ]
    for bad in forged:
        response = api.client.get(f"{base}/{bad}")
        assert response.status_code == 403, bad
        assert response.json()["error"]["code"] == "media_invalid"


def test_session_token_is_not_a_media_token(tmp_path):
    api = build(tmp_path)
    token = new_session(api.client)["Authorization"].split(" ")[1]
    assert api.client.get(f"/v1/media/{token}").status_code == 403


def test_validly_signed_token_cannot_leave_the_data_dir_or_serve_other_types(tmp_path):
    engine, path = image_engine(tmp_path)
    api = build(tmp_path, engine=engine)
    signer = Signer(api.settings.signing_key("media"))
    exp = api.clock().timestamp() + 60
    (tmp_path / "secret.png").write_bytes(PNG)
    (api.data_dir / "notes.pdf").write_bytes(b"%PDF-1.7 data")
    for payload in ({"p": "../secret.png"}, {"p": "notes.pdf"}, {"p": "missing.png"}, {"p": 7},
                    {"p": "api.sqlite3"}):
        response = api.client.get("/v1/media/" + signer.sign(payload, exp))
        assert response.status_code == 404, payload


def test_token_without_expiry_is_invalid(tmp_path):
    api = build(tmp_path)
    signer = Signer(api.settings.signing_key("media"))
    body = base64.urlsafe_b64encode(b'{"p":"x.png"}').rstrip(b"=").decode()
    sig = base64.urlsafe_b64encode(signer._mac(body)).rstrip(b"=").decode()
    assert api.client.get(f"/v1/media/{body}.{sig}").status_code == 403


@pytest.mark.parametrize("case", ["outside", "missing"])
def test_image_outside_the_data_dir_is_not_exposed(tmp_path, case):
    engine, path = image_engine(tmp_path, inside=case != "outside")
    if case == "missing":
        path.unlink()
    api = build(tmp_path, engine=engine)
    response = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert str(tmp_path) not in response.text


# ---------- aprobari ----------

def shadow_engine(tmp_path) -> FakeEngine:
    engine, path = image_engine(tmp_path)
    offer = [OutboundAction(kind="image", text="Oferta: 250,00 lei", image_path=str(path)),
             OutboundAction(kind="text", text="Link de plata: https://plata.test/x")]
    engine.reply = [OutboundAction(kind="pending_approval", approval_id="apr-1", text="Oferta: 250,00 lei",
                                   image_path=str(path))]
    engine.approvals = {"apr-1": offer}
    return engine


@pytest.mark.parametrize("path", ["/v1/approvals/apr-1/approve", "/v1/approvals/apr-1/reject"])
def test_approval_routes_require_secret(tmp_path, path):
    api = build(tmp_path, engine=shadow_engine(tmp_path))
    response = api.client.post(path, json={"by": "ana"})
    assert response.status_code == 401
    assert api.engine.approved == [] and api.engine.rejected == []


def test_crm_sees_the_pending_offer_and_approval_returns_actions_to_deliver(tmp_path):
    api = build(tmp_path, engine=shadow_engine(tmp_path))
    pending = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH).json()["actions"][0]
    assert pending["kind"] == "pending_approval" and pending["approval_id"] == "apr-1"
    assert pending["text"] == "Oferta: 250,00 lei" and pending["image_url"]

    response = api.client.post("/v1/approvals/apr-1/approve", json={"by": "ana"}, headers=AUTH)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["channel"] == "whatsapp" and data["key"] == WA_KEY and data["delivery"] == "crm"
    assert [a["kind"] for a in data["actions"]] == ["image", "text"]
    assert api.client.get(data["actions"][0]["image_url"]).status_code == 200
    assert api.engine.approved == [("apr-1", "ana", api.clock.now)]

    # Retrimiterea aprobarii intoarce aceleasi actiuni fara un al doilea apel la motor.
    again = api.client.post("/v1/approvals/apr-1/approve", json={"by": "ana"}, headers=AUTH).json()
    assert again["duplicate"] is True and again["actions"] == data["actions"]
    assert len(api.engine.approved) == 1


def test_reject(tmp_path):
    api = build(tmp_path, engine=shadow_engine(tmp_path))
    api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    response = api.client.post("/v1/approvals/apr-1/reject", json={"by": "ana"}, headers=AUTH)
    assert response.status_code == 200
    assert response.json() == {"approval_id": "apr-1", "channel": "whatsapp", "key": WA_KEY,
                               "status": "rejected", "actions": []}
    assert api.engine.rejected == [("apr-1", "ana", api.clock.now)]


@pytest.mark.parametrize("verb", ["approve", "reject"])
@pytest.mark.parametrize("approval_id", ["nu-exista", "id cu spatii"])
def test_unknown_approval_is_404(api, verb, approval_id):
    response = api.client.post(f"/v1/approvals/{approval_id}/{verb}", json={"by": "ana"}, headers=AUTH)
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "approval_not_found"


def test_approval_body_is_validated(api):
    response = api.client.post("/v1/approvals/apr-1/approve", json={}, headers=AUTH)
    assert response.status_code == 422
