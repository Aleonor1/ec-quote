"""CORS, ordinea pe conversatie, loguri, setari, radacina de compozitie, pagina de proba."""
from __future__ import annotations

import asyncio
import logging
import threading

import httpx
import pytest

from ec_quote.api import main
from ec_quote.api.logutil import configure_logging, contact_ref, logger, mask_phone, scrub
from ec_quote.api.ratelimit import RateLimiter
from ec_quote.api.security import secrets_equal
from ec_quote.api.store import IDEMPOTENCY_TTL_SECONDS, ApiStore
from ec_quote.config import INTEGRATION_VARS, SettingsError, load_settings
from ec_quote.contracts import OutboundAction
from tests.api.conftest import AUTH, ORIGIN, PNG, SECRET, WA_KEY, FakeEngine, base_env, build, inbound_body, new_session

# ---------- CORS ----------


def test_cors_allows_only_the_storefront_origin(api):
    preflight = {"Access-Control-Request-Method": "POST",
                 "Access-Control-Request-Headers": "authorization,content-type"}
    allowed = api.client.options("/v1/chat/message", headers=dict(preflight, Origin=ORIGIN))
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == ORIGIN
    assert "access-control-allow-credentials" not in allowed.headers

    for origin in ("https://evil.test", "https://etichetecreative.ro.evil.test", "null"):
        denied = api.client.options("/v1/chat/message", headers=dict(preflight, Origin=origin))
        assert denied.status_code == 400
        assert "access-control-allow-origin" not in denied.headers

    actual = api.client.post("/v1/chat/session", headers={"Origin": ORIGIN})
    assert actual.headers["access-control-allow-origin"] == ORIGIN
    foreign = api.client.post("/v1/chat/session", headers={"Origin": "https://evil.test"})
    assert "access-control-allow-origin" not in foreign.headers


def test_errors_carry_cors_headers_for_the_allowed_origin(tmp_path):
    def reply(message):
        raise RuntimeError("boom")

    api = build(tmp_path, engine=FakeEngine(reply))
    headers = dict(new_session(api.client), Origin=ORIGIN)
    response = api.client.post("/v1/chat/message", json={"text": "x"}, headers=headers)
    assert response.status_code == 500
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["x-request-id"] == response.json()["error"]["request_id"]


def test_without_configured_origins_no_origin_is_allowed(tmp_path):
    api = build(tmp_path, env={"EC_QUOTE_CORS_ORIGINS": ""})
    response = api.client.post("/v1/chat/session", headers={"Origin": ORIGIN})
    assert "access-control-allow-origin" not in response.headers


# ---------- o conversatie, un mesaj pe rand ----------

class BlockingEngine(FakeEngine):
    def __init__(self):
        super().__init__()
        self.events: list[str] = []
        self.entered = threading.Event()
        self.release = threading.Event()

    def handle(self, message):
        with self.lock:
            self.events.append(f"start {message.text}")
        if message.text == "first":
            self.entered.set()
            assert self.release.wait(10)
        with self.lock:
            self.events.append(f"end {message.text}")
        return [OutboundAction(kind="text", text=message.text)]


def test_same_conversation_is_serialized_and_others_are_not_blocked(tmp_path):
    engine = BlockingEngine()
    api = build(tmp_path, engine=engine)

    async def scenario():
        transport = httpx.ASGITransport(app=api.app)
        async with httpx.AsyncClient(transport=transport, base_url="https://quote.test") as client:
            def post(text, key):
                body = inbound_body(text=text, message_id=f"id-{text}")
                body["contact"] = {"key": key}
                return client.post("/v1/inbound", json=body, headers=AUTH)

            first = asyncio.create_task(post("first", WA_KEY))
            assert await asyncio.to_thread(engine.entered.wait, 10)
            second = asyncio.create_task(post("second", WA_KEY))
            # Alta conversatie trece cat timp prima este ocupata; bucla de evenimente nu este blocata.
            other = await post("other", "40700005678")
            assert other.status_code == 200
            assert engine.events == ["start first", "start other", "end other"]
            engine.release.set()
            return await asyncio.gather(first, second)

    responses = asyncio.run(scenario())
    assert [r.json()["actions"][0]["text"] for r in responses] == ["first", "second"]
    assert engine.events == ["start first", "start other", "end other",
                             "end first", "start second", "end second"]


def test_request_id_from_the_caller_is_kept_when_well_formed(api):
    kept = api.client.get("/health", headers={"X-Request-ID": "crm-req-12345678"})
    assert kept.headers["x-request-id"] == "crm-req-12345678"
    replaced = api.client.get("/health", headers={"X-Request-ID": "a b\tc"})
    assert replaced.headers["x-request-id"] != "a b\tc" and len(replaced.headers["x-request-id"]) == 16


# ---------- loguri ----------

def test_logs_have_request_id_and_no_phone_name_or_text(api, caplog):
    caplog.set_level(logging.INFO, logger="ec_quote.api")
    response = api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert response.status_code == 200
    lines = [r for r in caplog.records if r.name == "ec_quote.api"]
    assert len(lines) == 2
    assert {r.request_id for r in lines} == {response.headers["x-request-id"]}
    text = "\n".join(r.getMessage() for r in lines)
    assert "route=/v1/inbound status=200" in text and "actions=text" in text
    assert contact_ref(WA_KEY, api.settings.signing_key("log-ref")) in text
    for private in (WA_KEY, "0700001234", "Client Test", "etichete", SECRET):
        assert private not in text


def test_unhandled_error_logs_type_and_frames_but_not_the_message(tmp_path, caplog):
    def reply(message):
        raise RuntimeError(f"clientul {WA_KEY} a scris ceva privat")

    api = build(tmp_path, engine=FakeEngine(reply))
    caplog.set_level(logging.INFO, logger="ec_quote.api")
    api.client.post("/v1/inbound", json=inbound_body(), headers=AUTH)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "unhandled error type=RuntimeError at test_infra.py:" in text and " reply <" in text
    assert "privat" not in text and WA_KEY not in text


def test_media_route_is_logged_without_the_token(tmp_path, caplog):
    api = build(tmp_path)
    caplog.set_level(logging.INFO, logger="ec_quote.api")
    api.client.get("/v1/media/abc.def")
    api.client.get("/necunoscut/40700001234")
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "route=/v1/media/{token} status=403" in text and "abc.def" not in text
    assert "route=unmatched status=404" in text and "40700001234" not in text


def test_phone_masking_helpers():
    assert mask_phone("+40 700 001 234") == "407******34"
    assert mask_phone("12345") == "*****" and mask_phone(None) == "-"
    assert scrub("apel de la +40700001234 si 0700001234.") == "apel de la 407******34 si 070*****34."
    assert scrub("ms=1234 id=abc123456789def") == "ms=1234 id=abc123456789def"


def test_log_filter_scrubs_any_phone_like_number(caplog):
    caplog.set_level(logging.INFO, logger="ec_quote.api")
    logger.info("contact %s", "40700001234")
    logger.info("format gresit %d", "x")
    assert [r.getMessage() for r in caplog.records] == ["contact 407******34", "format gresit %d"]


def test_configure_logging_is_idempotent(monkeypatch):
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "propagate", True)
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    configure_logging()
    configure_logging()
    assert len(logger.handlers) == 1 and logger.propagate is False


# ---------- setari ----------

def test_settings_fail_closed_listing_every_missing_variable():
    with pytest.raises(SettingsError) as error:
        load_settings({})
    message = str(error.value)
    for name in ("EC_QUOTE_INBOUND_SECRET", *INTEGRATION_VARS):
        assert name in message


def test_settings_errors_never_contain_values(tmp_path):
    env = base_env(tmp_path, EC_QUOTE_INBOUND_SECRET="scurt-si-secret", EC_QUOTE_SIGNING_SECRET="alt-secret",
                   EC_QUOTE_MAX_UPLOAD_MB="multi", EC_QUOTE_MAX_ATTACHMENTS="0",
                   EC_QUOTE_CORS_ORIGINS="*", EC_QUOTE_PUBLIC_BASE_URL="oferta.exemplu.ro")
    with pytest.raises(SettingsError) as error:
        load_settings(env, require_integrations=False)
    message = str(error.value)
    for name in ("EC_QUOTE_INBOUND_SECRET", "EC_QUOTE_SIGNING_SECRET", "EC_QUOTE_MAX_UPLOAD_MB",
                 "EC_QUOTE_MAX_ATTACHMENTS", "EC_QUOTE_CORS_ORIGINS", "EC_QUOTE_PUBLIC_BASE_URL"):
        assert name in message
    assert "scurt-si-secret" not in message and "alt-secret" not in message and "multi" not in message


def test_settings_load_and_hide_secrets(tmp_path):
    env = base_env(tmp_path, **{name: f"valoare-{name}" for name in INTEGRATION_VARS},
                   EC_QUOTE_SIGNING_SECRET="s" * 32, EC_QUOTE_ALLOWED_MIMES="image/png, application/pdf",
                   EC_QUOTE_DEMO="true")
    settings = load_settings(dict(env, CRM_BASE_URL="https://crm.test/", CRM_API_SECRET="valoare-CRM_API_SECRET"))
    assert settings.crm_base_url == "https://crm.test"
    assert settings.demo is True and settings.allowed_mimes == ("image/png", "application/pdf")
    assert settings.cors_origins == (ORIGIN,) and settings.attachment_hosts == ("files.crm.test",)
    assert settings.max_upload_bytes == 1024 * 1024
    assert settings.calculator_sync_secret.get_secret_value() == "valoare-CALCULATOR_SYNC_SECRET"
    shown = repr(settings) + str(settings) + settings.model_dump_json()
    for secret in (SECRET, "s" * 32, "valoare-CALCULATOR_SYNC_SECRET", "valoare-ANTHROPIC_API_KEY",
                   "valoare-SHOPIFY_ADMIN_TOKEN", "valoare-CRM_API_SECRET"):
        assert secret not in shown
    assert settings.signing_key("media") != settings.signing_key("chat-session")


def test_signing_key_is_derived_when_not_set_and_env_is_the_default_source(tmp_path, monkeypatch):
    for name, value in base_env(tmp_path).items():
        monkeypatch.setenv(name, value)
    monkeypatch.delenv("EC_QUOTE_SIGNING_SECRET", raising=False)
    settings = load_settings(require_integrations=False)
    assert settings.signing_secret.get_secret_value() not in ("", SECRET)
    assert settings.demo is False and settings.chat_require_secret is False


def test_empty_secret_never_matches():
    assert secrets_equal("", "") is False and secrets_equal(None, "x") is False
    assert secrets_equal("x", "") is False and secrets_equal("abc", "abc") is True


# ---------- piese mici ----------

def test_rate_limiter_forgets_idle_keys():
    now = [0.0]
    limiter = RateLimiter(1, 10, clock=lambda: now[0])
    for index in range(499):
        assert limiter.hit(f"ip-{index}") is None
    now[0] = 11.0
    assert limiter.hit("ip-0") is None
    assert len(limiter._hits) == 1


def test_store_prunes_old_rows_on_open(tmp_path):
    now = [1000.0]
    path = tmp_path / "db" / "api.sqlite3"
    store = ApiStore(path, clock=lambda: now[0])
    store.save_response("whatsapp", WA_KEY, "m1", "[]")
    store.push_outbox("abc", "[]")
    store.close()
    now[0] += IDEMPOTENCY_TTL_SECONDS + 1
    store = ApiStore(path, clock=lambda: now[0])
    assert store.get_response("whatsapp", WA_KEY, "m1") is None and store.pop_outbox("abc") == []
    assert store.get_approval("nimic") is None
    store.close()
    memory = ApiStore(":memory:")
    assert memory.pop_outbox("x") == []
    memory.close()


def test_idempotency_survives_a_restart(tmp_path):
    first = build(tmp_path)
    one = first.client.post("/v1/inbound", json=inbound_body(), headers=AUTH).json()
    second = build(tmp_path)
    two = second.client.post("/v1/inbound", json=inbound_body(), headers=AUTH).json()
    assert two["duplicate"] is True and two["actions"] == one["actions"]
    assert second.engine.handled == []


def test_lifespan_closes_what_the_app_opened(tmp_path):
    settings = load_settings(base_env(tmp_path), require_integrations=False)
    from fastapi.testclient import TestClient

    from ec_quote.api.app import create_app
    from tests.api.conftest import FakeClock

    app = create_app(FakeEngine(), settings, clock=FakeClock())
    with TestClient(app, base_url="https://quote.test") as client:
        # Fara client injectat, aplicatia isi face unul; gazda blocata nu ajunge la retea.
        body = inbound_body(attachments=[{"url": "https://evil.test/a.png", "mime": "image/png"}])
        assert client.post("/v1/inbound", json=body, headers=AUTH).status_code == 422
    # Dupa oprire, baza de date a aplicatiei este inchisa.
    after = TestClient(app, base_url="https://quote.test").post("/v1/inbound", json=inbound_body(), headers=AUTH)
    assert after.status_code == 500


# ---------- pagina de proba si main.py ----------

def test_demo_page_is_served_only_in_demo_mode(tmp_path):
    off = build(tmp_path / "off")
    assert off.client.get("/demo/").status_code == 404
    assert off.client.get("/demo/widget.js").status_code == 404
    assert off.client.get("/docs").status_code == 404 and off.client.get("/openapi.json").status_code == 404
    on = build(tmp_path / "on", env={"EC_QUOTE_DEMO": "1"})
    page = on.client.get("/demo/")
    assert page.status_code == 200 and "widget.js" in page.text and 'lang="ro"' in page.text
    assert on.client.get("/demo/widget.js").status_code == 200
    assert on.client.get("/demo/widget.css").status_code == 200


def test_widget_copy_has_no_long_dashes_or_innerhtml():
    from ec_quote.api.app import STATIC_DIR

    for name in ("widget.js", "widget.css", "index.html"):
        text = (STATIC_DIR / name).read_text(encoding="utf-8")
        assert chr(0x2014) not in text and chr(0x2013) not in text
    script = (STATIC_DIR / "widget.js").read_text(encoding="utf-8")
    assert "innerHTML" not in script and "insertAdjacentHTML" not in script


def test_main_reports_missing_wiring_clearly(tmp_path):
    settings = load_settings(base_env(tmp_path), require_integrations=False)
    with pytest.raises(main.WiringError, match="ec_quote.nu_exista:build"):
        main.build_engine(settings, main.bucharest_now, "ec_quote.nu_exista:build")
    with pytest.raises(main.WiringError):
        main.load_object("ec_quote.api.demo_engine:lipsa")
    with pytest.raises(AttributeError):
        main.altceva
    assert main.bucharest_now().tzinfo is main.BUCHAREST


def test_main_uses_the_wiring_factory_by_default(tmp_path, monkeypatch):
    settings = load_settings(base_env(tmp_path), require_integrations=False)
    seen = {}
    monkeypatch.setattr(main, "load_object", lambda path: lambda **kwargs: seen.update(kwargs, path=path) or "engine")
    assert main.build_engine(settings, main.bucharest_now) == "engine"
    assert seen == {"settings": settings, "clock": main.bucharest_now, "path": "ec_quote.api.wiring:build_engine"}

    def broken(path):
        def factory(**kwargs):
            raise ModuleNotFoundError("anthropic")
        return factory

    monkeypatch.setattr(main, "load_object", broken)
    with pytest.raises(main.WiringError, match="ModuleNotFoundError"):
        main.build_engine(settings, main.bucharest_now)


def test_main_requires_integration_settings_for_the_real_engine(tmp_path):
    with pytest.raises(SettingsError, match="CALCULATOR_SYNC_SECRET"):
        main.build(base_env(tmp_path))


def test_main_app_attribute_builds_the_demo_end_to_end(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    env = base_env(tmp_path, EC_QUOTE_DEMO="1", EC_QUOTE_ENGINE_FACTORY="ec_quote.api.demo_engine:build_engine")
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(main, "_cache", {})
    monkeypatch.setattr(main, "configure_logging", lambda: None)
    app = main.app
    assert main.app is app
    client = TestClient(app, base_url="https://quote.test").__enter__()
    assert client.get("/demo/").status_code == 200
    headers = new_session(client)

    def say(**body):
        return client.post("/v1/chat/message", json=body, headers=headers).json()

    hello = say(text="Buna ziua")
    assert [a["kind"] for a in hello["actions"]] == ["text", "buttons"]
    assert all(len(b["title"]) <= 20 for b in hello["actions"][1]["buttons"])
    assert say(button_id="demo_file")["actions"][0]["kind"] == "text"
    assert say(text="vreau un coleg")["actions"][0]["kind"] == "handoff"
    pending = say(button_id="demo_offer")
    assert pending["poll"] is True and pending["actions"][0]["kind"] == "notice"
    assert "demonstrativa" not in str(pending)

    uploaded = client.post("/v1/chat/upload", headers=headers, files={"file": ("a.png", PNG)}).json()
    assert [a["kind"] for a in uploaded["actions"]] == ["text", "image"]
    assert client.get(uploaded["actions"][1]["image_url"]).headers["content-type"] == "image/png"

    key = [p.name for p in (tmp_path / "data" / "conversations" / "site").iterdir()][0]
    approval = f"demo-{key[:8]}"
    assert client.post(f"/v1/approvals/{approval}/reject", json={"by": "ana"}, headers=AUTH).status_code == 200
    assert client.post(f"/v1/approvals/{approval}/reject", json={"by": "ana"}, headers=AUTH).status_code == 404
    say(text="oferta")
    assert client.post(f"/v1/approvals/{approval}/approve", json={"by": "ana"}, headers=AUTH).status_code == 200
    assert client.get("/v1/chat/poll", headers=headers).json()["actions"][0]["kind"] == "image"
    client.__exit__(None, None, None)  # opreste aplicatia si inchide baza de date


def test_crm_is_optional_but_a_crm_url_needs_its_secret(tmp_path):
    env = base_env(tmp_path, **{name: "x" for name in INTEGRATION_VARS})
    assert load_settings(env).crm_base_url == ""
    with pytest.raises(SettingsError, match="CRM_API_SECRET"):
        load_settings(dict(env, CRM_BASE_URL="https://crm.test"))
    assert "CRM_BASE_URL" not in INTEGRATION_VARS and "EC_QUOTE_MODEL" not in INTEGRATION_VARS


@pytest.mark.parametrize("value", [
    "ana",                                         # fara token
    "ana:scurt",                                   # token prea scurt
    ":token-fara-nume-0123456789abcdef",
    "ana maria:token-ana-0123456789abcdefghij",    # nume cu spatiu
    "ana:token-ana-0123456789abcdefghij,ana:token-alt-0123456789abcdefghij",
    "ana:token-ana-0123456789abcdefghij,ion:token-ana-0123456789abcdefghij",
])
def test_assist_tokens_must_be_well_formed_and_unique(tmp_path, value):
    with pytest.raises(SettingsError) as error:
        load_settings(base_env(tmp_path, EC_QUOTE_ASSIST_TOKENS=value), require_integrations=False)
    assert "EC_QUOTE_ASSIST_TOKENS" in str(error.value) and "token-ana" not in str(error.value)


def test_assist_tokens_are_parsed_and_hidden(tmp_path):
    settings = load_settings(base_env(tmp_path), require_integrations=False)
    assert [name for name, _ in settings.assist_tokens] == ["ana", "mihai"]
    assert "token-ana" not in repr(settings) + settings.model_dump_json()
    empty = load_settings(base_env(tmp_path, EC_QUOTE_ASSIST_TOKENS=""), require_integrations=False)
    assert empty.assist_tokens == ()


# ---------- wiring.py: adaptoarele reale, cu module surori false ----------

def _fake_modules(monkeypatch, with_mockup_factory=False):
    import sys
    import types

    calls = {}

    def recorder(name):
        def make(*args, **kwargs):
            calls[name] = (args, kwargs)
            return name
        return make

    pricing = types.SimpleNamespace(CalculatorClient=recorder("pricing"))
    files = types.SimpleNamespace(FileChecker=recorder("files"))
    mockup = types.SimpleNamespace(MockupService=recorder("mockup"))
    if with_mockup_factory:
        mockup.build_mockup = recorder("mockup_factory")
    integrations = types.SimpleNamespace(ShopifyCheckout=recorder("checkout"), CrmClient=recorder("crm"),
                                         DEFAULT_API_VERSION="2026-04")
    agent = types.SimpleNamespace(
        AnthropicModel=recorder("model"), build_engine=recorder("engine"),
        Rules=types.SimpleNamespace(load=recorder("rules")))
    anthropic = types.SimpleNamespace(Anthropic=recorder("anthropic"))
    for name, module in (("ec_quote.pricing", pricing), ("ec_quote.files", files), ("ec_quote.mockup", mockup),
                         ("ec_quote.integrations", integrations), ("ec_quote.agent", agent),
                         ("anthropic", anthropic)):
        monkeypatch.setitem(sys.modules, name, module)
    return calls


def test_wiring_builds_the_engine_from_sibling_classes_without_crm(tmp_path, monkeypatch):
    import httpx

    from ec_quote.api import wiring

    calls = _fake_modules(monkeypatch)
    env = base_env(tmp_path, CALCULATOR_BASE_URL="https://calc.test/", CALCULATOR_SYNC_SECRET="sync-secret",
                   ANTHROPIC_API_KEY="sk-test", SHOPIFY_SHOP_DOMAIN="shop.test", SHOPIFY_ADMIN_TOKEN="shpat")
    settings = load_settings(env)
    assert wiring.build_engine(settings=settings, clock=main.bucharest_now) == "engine"

    args, kwargs = calls["pricing"]
    assert args == ("https://calc.test", "sync-secret") and isinstance(kwargs["http"], httpx.Client)
    assert calls["files"] == ((), {"rules_path": settings.rules_path})
    assert calls["checkout"][0][:2] == ("shop.test", "shpat") and calls["checkout"][0][3] == "2026-04"
    assert calls["anthropic"] == ((), {"api_key": "sk-test"})
    assert calls["model"] == ((), {"client": "anthropic", "model": None})
    assert calls["rules"] == ((settings.rules_path,), {})
    assert "crm" not in calls
    engine_kwargs = calls["engine"][1]
    assert isinstance(engine_kwargs["crm"], wiring.NoCrm) and engine_kwargs["handoff"] is engine_kwargs["crm"]
    assert engine_kwargs["pricing"] == "pricing" and engine_kwargs["files"] == "files"
    assert engine_kwargs["mockup"] == "mockup" and engine_kwargs["checkout"] == "checkout"
    assert engine_kwargs["model"] == "model" and engine_kwargs["rules"] == "rules"
    assert engine_kwargs["data_dir"] == settings.data_dir
    for call_args, call_kwargs in (calls["pricing"], calls["checkout"]):
        for value in (*call_args, *call_kwargs.values()):
            if isinstance(value, httpx.Client):
                value.close()


def test_wiring_uses_the_crm_client_and_a_mockup_factory_when_present(tmp_path, monkeypatch):
    from ec_quote.api import wiring

    calls = _fake_modules(monkeypatch, with_mockup_factory=True)
    settings = load_settings(base_env(tmp_path, CRM_BASE_URL="https://crm.test", CRM_API_SECRET="crm-secret",
                                      EC_QUOTE_MODEL="model-x"), require_integrations=False)
    wiring.build_engine(settings)
    assert calls["crm"][0][:2] == ("https://crm.test", "crm-secret")
    assert calls["engine"][1]["crm"] == "crm" and calls["engine"][1]["handoff"] == "crm"
    assert calls["mockup_factory"] == ((settings,), {}) and "mockup" not in calls
    assert calls["model"][1]["model"] == "model-x"
    for name in ("pricing", "checkout", "crm"):
        for value in (*calls[name][0], *calls[name][1].values()):
            if hasattr(value, "close"):
                value.close()


def test_no_crm_ports_do_nothing(caplog):
    from ec_quote.api.wiring import NoCrm
    from ec_quote.contracts import Contact, HandoffReason

    caplog.set_level(logging.INFO, logger="ec_quote.api")
    contact = Contact(channel="whatsapp", key=WA_KEY, name="Client Test")
    crm = NoCrm()
    assert crm.upsert_lead(contact, "rezumat", None, None, "new") == ""
    assert crm.handoff(contact, HandoffReason.COMPLAINT, "rezumat privat", main.bucharest_now()) is None
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "reason=complaint" in text and "privat" not in text and WA_KEY not in text
