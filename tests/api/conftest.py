"""Fixturi pentru testele API: motor fals, ceas fals, transport HTTP fals. Fara retea."""
from __future__ import annotations

import threading
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi.testclient import TestClient

from ec_quote.api.app import create_app
from ec_quote.api.store import ApiStore
from ec_quote.config import load_settings
from ec_quote.contracts import OutboundAction

SECRET = "test-inbound-secret-0123456789abcdef"
AUTH = {"X-EcQuote-Secret": SECRET}
ANA_TOKEN = "token-ana-0123456789abcdefghij"
MIHAI_TOKEN = "token-mihai-0123456789abcdefgh"
ANA = {"X-EcQuote-Assist-Token": ANA_TOKEN}
MIHAI = {"X-EcQuote-Assist-Token": MIHAI_TOKEN}
WA_KEY = "40700001234"
ORIGIN = "https://etichetecreative.ro"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.7\n" + b"0" * 64
START = datetime(2026, 11, 26, 10, 0, tzinfo=ZoneInfo("Europe/Bucharest"))


class FakeClock:
    def __init__(self):
        self.now = START
        self.mono = 1000.0

    def __call__(self) -> datetime:
        return self.now

    def monotonic(self) -> float:
        return self.mono

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        self.mono += seconds


class FakeEngine:
    """Inregistreaza apelurile; raspunsul este o lista sau o functie de mesaj."""

    def __init__(self, reply=None):
        self.reply = reply if reply is not None else [OutboundAction(kind="text", text="Salut")]
        self.handled = []
        self.approved = []
        self.edited = []
        self.rejected = []
        self.approvals = {}
        self.lock = threading.Lock()

    def handle(self, message):
        with self.lock:
            self.handled.append(message)
        return self.reply(message) if callable(self.reply) else list(self.reply)

    def approve(self, approval_id, approved_by, now, edited_text=None):
        self.approved.append((approval_id, approved_by, now))
        self.edited.append(edited_text)
        return list(self.approvals.pop(approval_id))

    def reject(self, approval_id, rejected_by, now):
        self.approvals.pop(approval_id)
        self.rejected.append((approval_id, rejected_by, now))


_stores: list[ApiStore] = []


@pytest.fixture(autouse=True)
def _close_stores():
    yield
    while _stores:
        _stores.pop().close()


async def public_resolver(host: str) -> list[str]:
    return ["93.184.216.34"]


def base_env(tmp_path, **extra) -> dict:
    env = {
        "EC_QUOTE_INBOUND_SECRET": SECRET,
        "EC_QUOTE_DATA_DIR": str(tmp_path / "data"),
        "EC_QUOTE_CORS_ORIGINS": ORIGIN,
        "EC_QUOTE_ATTACHMENT_HOSTS": "files.crm.test",
        "EC_QUOTE_MAX_ATTACHMENT_MB": "1",
        "EC_QUOTE_MAX_UPLOAD_MB": "1",
        "GIT_COMMIT": "abc1234",
        "EC_QUOTE_ASSIST_TOKENS": f"ana:{ANA_TOKEN}, mihai:{MIHAI_TOKEN}",
    }
    env.update(extra)
    return env


def build(tmp_path, *, engine=None, env=None, handler=None, resolver=public_resolver, assist=None):
    settings = load_settings(base_env(tmp_path, **(env or {})), require_integrations=False)
    engine = engine or FakeEngine()
    clock = FakeClock()
    requests: list[httpx.Request] = []

    def default_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=PNG, headers={"content-type": "image/png"})

    def recording(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return (handler or default_handler)(request)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(recording))
    store = ApiStore(settings.data_dir / "api.sqlite3", clock=lambda: clock().timestamp())
    _stores.append(store)
    app = create_app(engine, settings, clock=clock, monotonic=clock.monotonic,
                     http_client=http_client, resolver=resolver, store=store, assist=assist)
    client = TestClient(app, base_url="https://quote.test", raise_server_exceptions=False)
    return SimpleNamespace(app=app, client=client, engine=engine, assist=assist, clock=clock, settings=settings,
                           requests=requests, data_dir=settings.data_dir.resolve())


@pytest.fixture
def api(tmp_path):
    return build(tmp_path)


def inbound_body(**overrides) -> dict:
    body = {
        "channel": "whatsapp",
        "contact": {"key": WA_KEY, "phone": "+40700001234", "name": "Client Test", "ad_source": "fb:ad-1"},
        "message_id": "wamid.TEST1",
        "text": "Vreau 500 de etichete 5x5",
        "received_at": "2026-11-26T08:00:00Z",
    }
    body.update(overrides)
    return body


def new_session(client, **json) -> dict:
    response = client.post("/v1/chat/session", json=json or None)
    assert response.status_code == 200, response.text
    return {"Authorization": "Bearer " + response.json()["session_token"]}
