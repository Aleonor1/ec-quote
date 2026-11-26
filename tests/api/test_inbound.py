"""POST /v1/inbound: secret, trecerea campurilor spre motor, idempotenta, atasamente."""
from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from ec_quote.contracts import Button, HandoffReason, OutboundAction
from tests.api.conftest import AUTH, PDF, PNG, WA_KEY, FakeEngine, build, inbound_body


def test_health_reports_commit(api):
    response = api.client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "commit": "abc1234"}
    assert response.headers["x-request-id"]


def test_health_commit_is_null_when_unset(tmp_path):
    api = build(tmp_path, env={"GIT_COMMIT": ""})
    assert api.client.get("/health").json() == {"status": "ok", "commit": None}


@pytest.mark.parametrize("headers", [{}, {"X-EcQuote-Secret": "gresit"}, {"X-EcQuote-Secret": ""},
                                     {"X-EcQuote-Secret": AUTH["X-EcQuote-Secret"] + "x"}])
def test_inbound_requires_secret(api, headers):
    response = api.client.post("/v1/inbound", json=inbound_body(), headers=headers)
    assert response.status_code == 401
    error = response.json()["error"]
    assert error["code"] == "unauthorized"
    assert error["request_id"] == response.headers["x-request-id"]
    assert api.engine.handled == []


def test_inbound_passes_message_to_engine_and_serializes_actions(tmp_path):
    engine = FakeEngine([
        OutboundAction(kind="text", text="Buna ziua"),
        OutboundAction(kind="buttons", text="Alegeti", buttons=[Button(id="b1", title="Mat")]),
        OutboundAction(kind="handoff", handoff_reason=HandoffReason.COMPLAINT),
    ])
    api = build(tmp_path, engine=engine)
    body = inbound_body(button_id="b0", from_staff=False)
    response = api.client.post("/v1/inbound", json=body, headers=AUTH)
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["message_id"] == "wamid.TEST1" and data["duplicate"] is False
    assert [a["kind"] for a in data["actions"]] == ["text", "buttons", "handoff"]
    assert data["actions"][1]["buttons"] == [{"id": "b1", "title": "Mat"}]
    assert data["actions"][2]["handoff_reason"] == "complaint"
    assert data["actions"][0] == {"kind": "text", "text": "Buna ziua", "buttons": [], "image_url": None,
                                  "handoff_reason": None, "approval_id": None}

    message = engine.handled[0]
    assert message.contact.channel == "whatsapp" and message.contact.key == WA_KEY
    assert message.contact.phone == "+40700001234" and message.contact.name == "Client Test"
    assert message.contact.ad_source == "fb:ad-1"
    assert message.text == body["text"] and message.button_id == "b0"
    assert message.received_at.isoformat() == "2026-11-26T08:00:00+00:00"
    assert message.attachments == [] and message.from_staff is False


def test_naive_received_at_is_read_as_utc(api):
    api.client.post("/v1/inbound", json=inbound_body(received_at="2026-11-26T08:00:00"), headers=AUTH)
    assert api.engine.handled[0].received_at.utcoffset().total_seconds() == 0


def test_same_message_id_is_handled_once(api):
    first = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH).json()
    second = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH).json()
    assert len(api.engine.handled) == 1
    assert second["duplicate"] is True and first["duplicate"] is False
    assert second["actions"] == first["actions"]
    # Alt id de mesaj sau alt contact: mesaj nou.
    api.client.post("/v1/inbound", json=inbound_body(message_id="wamid.TEST2"), headers=AUTH)
    other = inbound_body()
    other["contact"] = {"key": "40700009999"}
    api.client.post("/v1/inbound", json=other, headers=AUTH)
    assert len(api.engine.handled) == 3


def test_failed_engine_call_is_not_remembered(tmp_path):
    calls = []

    def reply(message):
        calls.append(message)
        if len(calls) == 1:
            raise RuntimeError("detaliu intern 40700001234")
        return [OutboundAction(kind="text", text="ok")]

    api = build(tmp_path, engine=FakeEngine(reply))
    failed = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert failed.status_code == 500
    assert failed.json()["error"]["code"] == "internal_error"
    assert "detaliu" not in failed.text and "Traceback" not in failed.text
    retry = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert retry.status_code == 200 and retry.json()["duplicate"] is False


@pytest.mark.parametrize("change", [
    {"channel": "sms"},
    {"contact": {"key": "nu-cifre"}},
    {"contact": {"key": "40700001234", "necunoscut": 1}},
    {"message_id": ""},
    {"received_at": "ieri"},
    {"channel": "site"},  # cheia de WhatsApp nu este un id de sesiune
])
def test_invalid_body_gets_uniform_error_without_echo(api, change):
    response = api.client.post("/v1/inbound", json=inbound_body(**change), headers=AUTH)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_request" and error["fields"]
    assert "nu-cifre" not in response.text and "ieri" not in response.text


def test_unknown_route_and_method_use_the_error_shape(api):
    assert api.client.get("/nimic").json()["error"]["code"] == "not_found"
    assert api.client.get("/v1/inbound").json()["error"]["code"] == "method_not_allowed"


# ---------- atasamente ----------

def attachment(url="https://files.crm.test/a/1", mime="image/png", filename="logo.png") -> dict:
    return {"url": url, "mime": mime, "filename": filename}


def post_with(api, *attachments):
    return api.client.post("/v1/inbound", json=inbound_body(attachments=list(attachments)), headers=AUTH)


def no_files_left(api) -> bool:
    return not [p for p in api.data_dir.rglob("*") if p.is_file() and p.suffix != ".sqlite3"]


def test_attachment_is_downloaded_into_the_conversation_directory(api):
    response = post_with(api, attachment(filename="../../etc/Logo final.png"))
    assert response.status_code == 200, response.text
    item = api.engine.handled[0].attachments[0]
    path = Path(item.path)
    assert path.parent == api.data_dir / "conversations" / "whatsapp" / WA_KEY / "inbound"
    assert path.read_bytes() == PNG and path.suffix == ".png"
    assert item.mime == "image/png" and item.filename == "Logo final.png"
    assert item.public_url == "https://files.crm.test/a/1"
    assert len(api.requests) == 1


def test_mime_comes_from_content_not_from_declaration(tmp_path):
    api = build(tmp_path, handler=lambda r: httpx.Response(200, content=PDF))
    assert post_with(api, attachment(mime="image/png")).status_code == 200
    item = api.engine.handled[0].attachments[0]
    assert item.mime == "application/pdf" and item.path.endswith(".pdf")


@pytest.mark.parametrize("url", [
    "https://evil.test/a.png",
    "http://files.crm.test/a.png",
    "https://files.crm.test:8443/a.png",
    "https://user:pw@files.crm.test/a.png",
    "https://files.crm.test.evil.test/a.png",
    "https://127.0.0.1/a.png",
    "https://[::1]/a.png",
    "https://files.crm.test:notaport/a.png",
    "ftp://files.crm.test/a.png",
    "//files.crm.test/a.png",
])
def test_blocked_urls_are_never_fetched(api, url):
    response = post_with(api, attachment(url=url))
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "attachment_host_not_allowed"
    assert api.requests == [] and api.engine.handled == []


def test_allowed_host_resolving_to_private_address_is_blocked(tmp_path):
    async def private(host):
        return ["10.0.0.5"]

    api = build(tmp_path, resolver=private)
    response = post_with(api, attachment())
    assert response.json()["error"]["code"] == "attachment_host_not_allowed"
    assert api.requests == []


def test_resolution_failure_is_a_fetch_error(tmp_path):
    async def broken(host):
        raise OSError("dns")

    api = build(tmp_path, resolver=broken)
    response = post_with(api, attachment())
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "attachment_fetch_failed"


def test_too_large_by_content_length(tmp_path):
    big = PNG + b"\x00" * (1024 * 1024)
    api = build(tmp_path, handler=lambda r: httpx.Response(200, content=big))
    response = post_with(api, attachment())
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "attachment_too_large"
    assert api.engine.handled == [] and no_files_left(api)


def test_too_large_while_streaming_without_content_length(tmp_path):
    async def body():
        yield PNG
        for _ in range(9):
            yield b"\x00" * (128 * 1024)

    api = build(tmp_path, handler=lambda r: httpx.Response(200, content=body()))
    response = post_with(api, attachment())
    assert response.json()["error"]["code"] == "attachment_too_large"
    assert no_files_left(api)


@pytest.mark.parametrize("mime", ["text/html", "application/zip", "application/octet-stream", ""])
def test_declared_mime_outside_the_allow_list(api, mime):
    response = post_with(api, attachment(mime=mime or " "))
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "attachment_type_not_allowed"
    assert api.requests == []


@pytest.mark.parametrize("content", [b"<html><script>alert(1)</script></html>", b"MZ\x90\x00binary",
                                     b"GIF89a" + b"\x00" * 20, b""])
def test_content_that_is_not_an_allowed_type(tmp_path, content):
    api = build(tmp_path, handler=lambda r: httpx.Response(200, content=content))
    response = post_with(api, attachment())
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "attachment_type_not_allowed"
    assert api.engine.handled == [] and no_files_left(api)


def test_redirect_to_another_host_is_blocked(tmp_path):
    def handler(request):
        return httpx.Response(302, headers={"location": "https://169.254.169.254/latest/meta-data"})

    api = build(tmp_path, handler=handler)
    response = post_with(api, attachment())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "attachment_redirect_blocked"
    assert [str(r.url) for r in api.requests] == ["https://files.crm.test/a/1"]


def test_redirect_to_http_on_the_same_host_is_blocked(tmp_path):
    api = build(tmp_path, handler=lambda r: httpx.Response(301, headers={"location": "http://files.crm.test/x"}))
    assert post_with(api, attachment()).json()["error"]["code"] == "attachment_redirect_blocked"


def test_redirect_within_allowed_hosts_is_followed(tmp_path):
    def handler(request):
        if request.url.path == "/a/1":
            return httpx.Response(307, headers={"location": "/b/2"})
        return httpx.Response(200, content=PNG)

    api = build(tmp_path, handler=handler)
    assert post_with(api, attachment()).status_code == 200
    assert [r.url.path for r in api.requests] == ["/a/1", "/b/2"]


def test_redirect_loop_stops(tmp_path):
    api = build(tmp_path, handler=lambda r: httpx.Response(302, headers={"location": "/again"}))
    response = post_with(api, attachment())
    assert response.json()["error"]["code"] == "attachment_redirect_blocked"
    assert len(api.requests) == 4


@pytest.mark.parametrize("failure", ["status", "timeout", "connect"])
def test_upstream_failures(tmp_path, failure):
    def handler(request):
        if failure == "status":
            return httpx.Response(404)
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        raise httpx.ConnectError("refused", request=request)

    api = build(tmp_path, handler=handler)
    response = post_with(api, attachment())
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "attachment_fetch_failed"
    assert "files.crm.test" not in response.text


def test_one_bad_attachment_discards_the_good_ones(tmp_path):
    def handler(request):
        return httpx.Response(200, content=PNG if request.url.path == "/ok" else b"nope")

    api = build(tmp_path, handler=handler)
    response = post_with(api, attachment(url="https://files.crm.test/ok"),
                         attachment(url="https://files.crm.test/bad"))
    assert response.status_code == 415
    assert api.engine.handled == [] and no_files_left(api)


def test_too_many_attachments(api):
    response = post_with(api, *[attachment() for _ in range(6)])
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "too_many_attachments"
    assert api.requests == []


def test_staff_message_passes_through_without_downloads(api):
    response = api.client.post(
        "/v1/inbound", json=inbound_body(from_staff=True, attachments=[attachment()]), headers=AUTH)
    assert response.status_code == 200
    assert api.engine.handled[0].from_staff is True
    assert api.engine.handled[0].attachments == [] and api.requests == []


def test_engine_failure_removes_downloaded_files(tmp_path):
    def reply(message):
        raise RuntimeError("boom")

    api = build(tmp_path, engine=FakeEngine(reply))
    assert post_with(api, attachment()).status_code == 500
    assert no_files_left(api)


def test_svg_is_accepted_as_artwork(tmp_path):
    svg = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'
    api = build(tmp_path, handler=lambda r: httpx.Response(200, content=svg))
    assert post_with(api, attachment(mime="image/svg+xml")).status_code == 200
    assert api.engine.handled[0].attachments[0].mime == "image/svg+xml"


def test_message_id_is_passed_to_the_engine(api):
    api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert api.engine.handled[0].message_id == "wamid.TEST1"


def test_default_resolver_blocks_a_host_that_points_to_loopback(tmp_path):
    from ec_quote.api.fetcher import system_resolver

    api = build(tmp_path, env={"EC_QUOTE_ATTACHMENT_HOSTS": "localhost"}, resolver=system_resolver)
    response = post_with(api, attachment(url="https://localhost/a.png"))
    assert response.json()["error"]["code"] == "attachment_host_not_allowed"
    assert api.requests == []


def test_sniffing_and_file_names():
    from ec_quote.api.fetcher import normalize_mime, safe_filename, sniff_mime

    assert sniff_mime(b"\xff\xd8\xff\xe0JFIF") == "image/jpeg"
    assert sniff_mime(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == "image/webp"
    assert sniff_mime(b"II*\x00data") == "image/tiff" and sniff_mime(b"MM\x00*data") == "image/tiff"
    assert sniff_mime(b"%!PS-Adobe-3.0 EPSF-3.0") == "application/postscript"
    assert sniff_mime(b"\xef\xbb\xbf  <svg xmlns='x'>") == "image/svg+xml"
    assert sniff_mime(b"<?xml version='1.0'?><html>") is None and sniff_mime(b"RIFF1234WAVE") is None
    assert normalize_mime("Image/PNG; charset=binary") == "image/png" and normalize_mime(None) == ""
    assert safe_filename(None) is None and safe_filename("../../") is None
    assert safe_filename("C:\\Users\\x\\logo\x00.png") == "logo.png"
    assert len(safe_filename("a" * 500)) == 120
