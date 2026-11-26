"""Backendul intreg, legat ca in productie, cu module surori reale. Doar modelul, calculatorul si Shopify sunt dubluri."""
from __future__ import annotations

import io
from datetime import datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient
from PIL import Image, ImageDraw

from ec_quote import agent
from ec_quote.agent.eval import ScriptedModel
from ec_quote.api import wiring
from ec_quote.api.app import create_app
from ec_quote.api.store import ApiStore
from ec_quote.config import load_settings
from ec_quote.contracts import Checkout
from ec_quote.pricing.fake import FakeCalculator, STICKER_ID

TOKEN = "token-ana-0123456789abcdefghij"
ANA = {"X-EcQuote-Assist-Token": TOKEN}
CHAT = "40700001234"
START = datetime(2026, 11, 26, 10, 0, tzinfo=ZoneInfo("Europe/Bucharest"))
LINE = {"product_id": STICKER_ID, "material_name": "Vinil Alb Lucios", "shape": "circle",
        "width_cm": 5, "height_cm": 5, "quantity": 500}


class FakeCheckout:
    def __init__(self) -> None:
        self.calls: list = []

    def create_checkout(self, quote, contact, artwork_url, valid_until):
        self.calls.append((quote, contact, artwork_url, valid_until))
        return Checkout(draft_order_id=f"gid://shopify/DraftOrder/{len(self.calls)}",
                        invoice_url=f"https://shop.test/invoices/{len(self.calls)}", total=quote.total)


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        self.now += timedelta(**delta)


def logo_png(size: int = 1200) -> bytes:
    """Un logo generat, destul de mare pentru o eticheta de 5 cm."""
    image = Image.new("RGBA", (size, size), (255, 255, 255, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((40, 40, size - 40, size - 40), fill=(20, 110, 70, 255))
    draw.rectangle((size // 3, size // 3, 2 * size // 3, 2 * size // 3), fill=(250, 240, 200, 255))
    out = io.BytesIO()
    image.save(out, format="PNG", dpi=(300, 300))
    return out.getvalue()


def build(tmp_path, checkout=None, shadow: bool | None = None):
    settings = load_settings({
        "EC_QUOTE_INBOUND_SECRET": "test-inbound-secret-0123456789abcdef",
        "EC_QUOTE_DATA_DIR": str(tmp_path / "data"),
        "EC_QUOTE_ASSIST_TOKENS": f"ana:{TOKEN}",
    }, require_integrations=False)
    model = ScriptedModel()
    calculator = FakeCalculator()
    checkout = checkout or FakeCheckout()
    crm = wiring.NoCrm()
    clock = Clock()
    engine = agent.build_engine(
        knowledge=wiring.build_knowledge(settings), pricing=calculator.client(),
        files=wiring.build_files(settings), mockup=wiring.build_mockup(settings),
        checkout=checkout, crm=crm, handoff=crm, model=model,
        rules=agent.Rules.load(settings.rules_path), data_dir=settings.data_dir)
    store = ApiStore(settings.data_dir / "api.sqlite3", clock=lambda: clock().timestamp())
    app = create_app(engine, settings, clock=clock, store=store)
    client = TestClient(app, base_url="https://quote.test", raise_server_exceptions=False)
    return SimpleNamespace(client=client, engine=engine, model=model, calculator=calculator, checkout=checkout,
                           clock=clock, settings=settings, store=store, messages=[],
                           data_dir=settings.data_dir.resolve())


def script(ctx, *items) -> None:
    ctx.model.load([{"tool": i[0], "args": i[1]} if isinstance(i, tuple) else {"text": i} for i in items])


def customer(ctx, text: str = "", upload_id: str | None = None, direction: str = "in") -> None:
    ctx.clock.advance(minutes=1)
    ctx.messages.append({
        "id": f"wamid.{len(ctx.messages) + 1}", "direction": direction, "text": text,
        "sent_at": ctx.clock.now.isoformat(),
        "attachments": [{"upload_id": upload_id}] if upload_id else []})


def suggest(ctx) -> dict:
    response = ctx.client.post("/v1/assist/suggest", headers=ANA,
                               json={"chat": {"key": CHAT, "name": "Client Test", "phone": "+40700001234"},
                                     "messages": ctx.messages})
    assert response.status_code == 200, response.text
    return response.json()["suggestion"]


def close(ctx) -> None:
    ctx.store.close()
    ctx.engine.store.close()
