"""Porturi false, in memorie, pentru testele motorului. Fara retea, fara module vecine."""
from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from ec_quote.agent import InMemoryStore, ModelReply, QuoteEngine, Rules, ToolCall
from ec_quote.contracts import (
    AssistMessage, Attachment, Checkout, Contact, FileReport, FileVerdict, InboundMessage, KnowledgeEntry,
    LineProperty, MockupResult, PriceQuote, TierOffer, Unpriced,
)

TZ = ZoneInfo("Europe/Bucharest")
THURSDAY_10 = datetime(2026, 11, 26, 10, 0, tzinfo=TZ)

RULES_DATA = {
    "handoff_value_threshold_ron_ex_vat": "3000",
    "offer_validity_days": 7,
    "max_clarifying_questions": 2,
    "max_misunderstandings": 2,
    "max_file_attempts": 2,
    "upsell_tier_count": 2,
    "vat_percent": "21",
    "shadow_mode": False,
    "manual_mode_quiet_hours": 48,
    "max_offers_per_contact_per_day": 5,
    "business_hours": {"start": "09:00", "end": "18:00", "days": [1, 2, 3, 4, 5]},
    "approved_material_claims": ["rezistenta la umezeala si ulei", "lac UV mat", "fara laminare"],
    "production_term_standard": "3-5 zile lucrătoare",
}

CATALOG = {
    "version": 1,
    "generatedAt": "2026-11-26T08:00:00Z",
    "products": [{
        "id": "gid://shopify/Product/1",
        "title": "Etichete autocolante",
        "handle": "etichete-autocolante",
        "shapes": ["Rotund", "Dreptunghi"],
        "materials": [{"name": "Vinyl alb", "pricingTableId": "t1"}, {"name": "Hârtie", "pricingTableId": "t2"}],
        "customSize": {"enabled": True, "minCm": 2, "maxCm": 100},
        "addOnGroups": [{"name": "Finisaj", "choices": [{"name": "Lucios", "modifierPercent": 0}]}],
        "options": {"adhesive": True, "whitePrint": True, "cut": True, "urgency": True},
        "quantity": {"min": 25, "max": 10000, "tiers": [{"quantity": 500, "discountPercent": 10}]},
    }, {
        "id": "gid://shopify/Product/2",
        "title": "Stickere decupate",
        "handle": "stickere-decupate",
        "shapes": ["Contur"],
        "materials": [{"name": "Vinyl alb", "pricingTableId": "t1"}],
    }],
}

LINE = {"product_id": "gid://shopify/Product/1", "material_name": "vinyl alb", "shape": "rotund",
        "width_cm": 5, "height_cm": 5, "quantity": 500}


def make_rules(**overrides) -> Rules:
    return Rules.from_dict({**RULES_DATA, **overrides})


class FakePricing:
    def __init__(self, unit_ex_vat: str = "0.50") -> None:
        self.unit = Decimal(unit_ex_vat)
        self.unpriced: Unpriced | None = None
        self.min_quantity = 0
        self.promo_percent = 0
        self.price_calls: list = []
        self.tier_calls: list = []
        self.fail_catalog = False

    def catalog(self) -> dict:
        if self.fail_catalog:
            raise RuntimeError("calculator jos")
        return CATALOG

    def _totals(self, quantity: int) -> tuple[Decimal, Decimal]:
        ex_vat = (self.unit * quantity).quantize(Decimal("0.01"))
        return ex_vat, (ex_vat * Decimal("1.21")).quantize(Decimal("0.01"))

    def get_price(self, choices):
        self.price_calls.append(choices)
        if self.unpriced is not None:
            return self.unpriced
        if choices.quantity < self.min_quantity:
            return Unpriced(reason="quantity_below_minimum", details={"minQuantity": self.min_quantity})
        ex_vat, total = self._totals(choices.quantity)
        if choices.urgent:
            ex_vat, total = ex_vat + Decimal("125.00"), total + Decimal("151.25")
        if choices.adhesive == "strong":
            ex_vat, total = ex_vat + Decimal("20.00"), total + Decimal("24.20")
        unit = (total / choices.quantity).quantize(Decimal("0.01"))
        return PriceQuote(choices=choices, total=total, total_ex_vat=ex_vat, unit_price=unit,
                          discount_percent=Decimal("10"), breakdown={"promoPercent": self.promo_percent},
                          properties=[LineProperty(name="a", value="b")])

    def get_price_tiers(self, choices, count):
        self.tier_calls.append((choices, count))
        tiers = []
        for step in range(1, count + 1):
            quantity = choices.quantity * (step + 1)
            ex_vat, total = self._totals(quantity)
            unit = (total / quantity).quantize(Decimal("0.01"))
            tiers.append(TierOffer(quantity=quantity, total=total, total_ex_vat=ex_vat, unit_price=unit))
        return tiers


class FakeFiles:
    def __init__(self, verdict: FileVerdict = FileVerdict.OK) -> None:
        self.verdict = verdict
        self.calls: list = []

    def check_file(self, path, width_cm, height_cm):
        self.calls.append((path, width_cm, height_cm))
        problems = [] if self.verdict == FileVerdict.OK else ["low_dpi"]
        return FileReport(kind="raster", mime="image/png", verdict=self.verdict, problems=problems,
                          dpi_at_size=Decimal("96"))


class FakeMockup:
    def __init__(self) -> None:
        self.mockups: list = []
        self.offer_images: list = []
        self.fail = False

    def make_mockup(self, design_path, context_hint, out_dir):
        if self.fail:
            raise RuntimeError("fara sablon")
        self.mockups.append((design_path, context_hint, out_dir))
        return MockupResult(template_id="borcan-1", image_path=f"{out_dir}/mockup.png")

    def make_offer_image(self, mockup_path, lines, production_term, valid_until, out_dir):
        if self.fail:
            raise RuntimeError("fara imagine")
        self.offer_images.append((mockup_path, lines, production_term, valid_until))
        return f"{out_dir}/offer.png"


class FakeCheckout:
    def __init__(self) -> None:
        self.calls: list = []
        self.total_override: Decimal | None = None
        self.fail = False

    def create_checkout(self, quote, contact, artwork_url, valid_until):
        if self.fail:
            raise RuntimeError("shopify jos")
        self.calls.append((quote, contact, artwork_url, valid_until))
        return Checkout(draft_order_id=f"D{len(self.calls)}", invoice_url=f"https://pay.example/{len(self.calls)}",
                        total=self.total_override if self.total_override is not None else quote.total)


class FakeCrm:
    def __init__(self) -> None:
        self.calls: list = []
        self.fail = False

    def upsert_lead(self, contact, summary, quote, checkout, status):
        if self.fail:
            raise RuntimeError("crm jos")
        self.calls.append({"contact": contact, "summary": summary, "quote": quote, "checkout": checkout,
                           "status": status})
        return "lead-1"

    @property
    def statuses(self) -> list[str]:
        return [c["status"] for c in self.calls]


class FakeKnowledge:
    """Baza de cunostinte falsa: cauta dupa cuvinte in intrebare si raspuns."""

    def __init__(self, *entries: KnowledgeEntry) -> None:
        self.entries = list(entries)
        self.queries: list[str] = []

    def search(self, query, limit=5):
        from ec_quote.agent.guard import normalize
        self.queries.append(query)
        words = [w for w in normalize(query).split(" ") if len(w) > 3]
        hits = [e for e in self.entries if e.status == "verified"
                and any(w in normalize(f"{e.question} {e.answer} {e.topic}") for w in words)]
        return hits[:limit]

    def topics(self):
        return sorted({e.topic for e in self.entries})


KNOWLEDGE = [
    KnowledgeEntry(id="k1", topic="rezistenta", question="Rezista etichetele la apa?",
                   answer="Etichetele din vinyl rezistă la apă și la umezeală. Cele din hârtie nu sunt potrivite "
                          "pentru medii umede.", applies_to=["Vinyl alb"], status="verified"),
    KnowledgeEntry(id="k2", topic="livrare", question="Cat dureaza livrarea?",
                   answer="Livrarea se face prin curier, în 1-2 zile lucrătoare de la expediere. Transportul costă "
                          "20 lei și este gratuit la comenzi peste 300 lei.", status="verified"),
    KnowledgeEntry(id="k3", topic="rezistenta", question="Rezista la congelator?",
                   answer="Nu avem inca un raspuns verificat.", status="needs_owner"),
]


class FakeHandoff:
    def __init__(self) -> None:
        self.calls: list = []
        self.fail = False

    def handoff(self, contact, reason, summary, now):
        if self.fail:
            raise RuntimeError("inbox jos")
        self.calls.append((contact, reason, summary, now))


class ScriptedModel:
    """Raspunde cu replicile date, in ordine; tine minte ce a primit."""

    def __init__(self, *replies) -> None:
        self.replies = list(replies)
        self.calls: list[dict] = []

    def add(self, *replies) -> None:
        self.replies.extend(replies)

    def complete(self, *, system, tools, messages):
        self.calls.append({"system": system, "tools": tools, "messages": [dict(m) for m in messages]})
        if not self.replies:
            raise AssertionError("modelul fals nu mai are replici")
        reply = self.replies.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return reply


_counter = iter(range(1, 100000))


def call(name: str, **args) -> ModelReply:
    return ModelReply(tool_calls=[ToolCall(id=f"tu_{next(_counter)}", name=name, input=args)], stop_reason="tool_use")


def calls(*pairs) -> ModelReply:
    return ModelReply(tool_calls=[ToolCall(id=f"tu_{next(_counter)}", name=n, input=a) for n, a in pairs],
                      stop_reason="tool_use")


def say(text: str) -> ModelReply:
    return ModelReply(text=text)


def offer_script(quantity: int = 500) -> list[ModelReply]:
    return [call("get_price", **{**LINE, "quantity": quantity}), call("get_price_tiers", quote_id="q1"),
            call("create_checkout", quote_id="q1", summary="500 etichete rotunde 5 cm pentru borcane")]


class Harness:
    def __init__(self, tmp_path, *replies, store=None, **rule_overrides) -> None:
        self.model = ScriptedModel(*replies)
        self.pricing = FakePricing()
        self.files = FakeFiles()
        self.mockup = FakeMockup()
        self.checkout = FakeCheckout()
        self.crm = FakeCrm()
        self.handoff = FakeHandoff()
        self.knowledge = FakeKnowledge(*KNOWLEDGE)
        self.transcript: list[AssistMessage] = []
        self.store = store or InMemoryStore()
        self.rules = make_rules(**rule_overrides)
        ids = iter(f"ap{i}" for i in range(1, 1000))
        self.engine = QuoteEngine(
            model=self.model, pricing=self.pricing, files=self.files, mockup=self.mockup, checkout=self.checkout,
            crm=self.crm, handoff=self.handoff, knowledge=self.knowledge, store=self.store, rules=self.rules,
            data_dir=tmp_path,
            id_factory=lambda: next(ids))

    def state(self, key: str = "40700000001"):
        return self.store.load("whatsapp", key)

    def send(self, text: str = "", *, at: datetime = THURSDAY_10, key: str = "40700000001", staff: bool = False,
             button_id: str | None = None, attachment: bool = False, message_id: str | None = None):
        attachments = [Attachment(path="/tmp/in/logo.png", mime="image/png", filename="logo.png",
                                  public_url="https://cdn.example/logo.png")] if attachment else []
        message = InboundMessage(contact=Contact(channel="whatsapp", key=key, phone=f"+{key}"), text=text,
                                 button_id=button_id, attachments=attachments, received_at=at, from_staff=staff)
        return self.engine.handle(message, message_id=message_id)

    # ---------- mod asistat ----------

    def contact(self, key: str = "40700000001") -> Contact:
        return Contact(channel="whatsapp", key=key, phone=f"+{key}")

    def say(self, direction: str, text: str = "", *, at: datetime | None = None, mime: str | None = None,
            filename: str = "logo.png") -> AssistMessage:
        """Adauga un mesaj in conversatia vizibila (fara sa ceara inca o sugestie)."""
        stamp = at or THURSDAY_10 + timedelta(minutes=len(self.transcript))
        attachments = [Attachment(path=f"/tmp/in/{filename}", mime=mime, filename=filename,
                                  public_url=f"https://cdn.example/{filename}")] if mime else []
        message = AssistMessage(id=f"wa{len(self.transcript) + 1}", direction=direction, text=text, sent_at=stamp,
                                attachments=attachments)
        self.transcript.append(message)
        return message

    def suggest(self, text: str | None = None, *, now: datetime | None = None, **kwargs):
        """Clientul scrie (optional) si extensia cere sugestia pentru toata conversatia vizibila."""
        if text is not None or kwargs:
            self.say("in", text or "", **kwargs)
        moment = now or (self.transcript[-1].sent_at if self.transcript else THURSDAY_10)
        return self.engine.suggest(self.contact(), list(self.transcript), moment)
