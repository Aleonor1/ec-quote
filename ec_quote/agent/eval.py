"""Evaluarea scenariilor in modul asistat, cu verificari facute de cod (nu de model).

    python3 -m ec_quote.agent.eval --cases tests/agent/eval_cases.jsonl          # model real (cere ANTHROPIC_API_KEY)
    python3 -m ec_quote.agent.eval --cases tests/agent/eval_cases.jsonl --fake   # replicile scrise in cazuri

Porturile sunt demonstrative si in memorie: calculatorul, fisierele, Shopify si baza de cunostinte reale
nu sunt atinse. Fiecare caz are pasi; un pas adauga mesaje in conversatie, cere o sugestie si o verifica.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from ec_quote.contracts import (
    AssistMessage, AssistSuggestion, Attachment, Checkout, Contact, FileReport, FileVerdict, KnowledgeEntry,
    MockupResult, PriceQuote, TierOffer, Unpriced,
)

from .engine import QuoteEngine
from .guard import money_mentions, normalize
from .model import ModelPort, ModelReply, ToolCall
from .rules import TZ, Rules
from .store import InMemoryStore

START = datetime(2026, 11, 26, 10, 0, tzinfo=TZ)

DEMO_CATALOG = {
    "version": 1,
    "settings": {"minQuantity": 25, "urgency": {"enabled": True, "maxQuantity": 500}},
    "products": [
        {"id": "etichete", "title": "Etichete autocolante", "handle": "etichete-autocolante",
         "shapes": ["Rotund", "Dreptunghi", "Patrat"],
         "materials": [{"name": "Vinyl alb"}, {"name": "Hârtie"}, {"name": "Vinyl transparent"}],
         "customSize": {"enabled": True, "minCm": 2, "maxCm": 100},
         "options": {"adhesive": True, "whitePrint": True, "cut": True, "urgency": True},
         "quantity": {"min": 25, "default": 100, "max": 10000,
                      "tiers": [{"quantity": 100, "discountPercent": 0}, {"quantity": 500, "discountPercent": 10},
                                {"quantity": 1000, "discountPercent": 20}]}},
        {"id": "stickere", "title": "Stickere decupate", "handle": "stickere-decupate",
         "shapes": ["Contur"], "materials": [{"name": "Vinyl alb"}],
         "customSize": {"enabled": True, "minCm": 3, "maxCm": 50},
         "options": {"adhesive": False, "whitePrint": False, "cut": False, "urgency": False},
         "quantity": {"min": 50, "default": 100, "max": 5000, "tiers": []}},
    ],
}

DEMO_KNOWLEDGE = [
    KnowledgeEntry(id="apa", topic="rezistenta", question="Rezista etichetele la apa si umezeala?",
                   answer="Etichetele din vinyl rezistă la apă și la umezeală. Cele din hârtie nu sunt potrivite "
                          "pentru medii umede.", status="verified"),
    KnowledgeEntry(id="livrare", topic="livrare", question="Cum se face livrarea si cat dureaza?",
                   answer="Livrarea se face prin curier, în 1-2 zile lucrătoare de la expediere.", status="verified"),
    KnowledgeEntry(id="plata", topic="plata", question="Cum se poate plati?",
                   answer="Plata se face online, cu cardul, prin linkul de plată, sau prin transfer bancar.",
                   status="verified"),
    KnowledgeEntry(id="fisiere", topic="fisiere", question="In ce format trimit grafica?",
                   answer="Preferăm fișiere vectoriale (PDF, AI, SVG). Acceptăm și PNG sau JPG la rezoluție mare.",
                   status="verified"),
]


class DemoPricing:
    """Preturi deterministe; tine minte toate sumele pe care le-a dat."""

    def __init__(self) -> None:
        self.amounts: list[Decimal] = []

    def catalog(self) -> dict:
        return DEMO_CATALOG

    def _price(self, choices, quantity: int) -> tuple[Decimal, Decimal, Decimal]:
        area = choices.width_cm * choices.height_cm
        discount = Decimal("0.8") if quantity >= 1000 else Decimal("0.9") if quantity >= 500 else Decimal(1)
        material = Decimal("0.7") if normalize(choices.material_name) == "hartie" else Decimal(1)
        ex_vat = area * Decimal("0.02") * quantity * discount * material + Decimal(20)
        if choices.adhesive == "strong":
            ex_vat *= Decimal("1.10")
        if choices.white_print:
            ex_vat *= Decimal("1.15")
        if choices.cut != "none":
            ex_vat *= Decimal("1.05")
        if choices.urgent:
            ex_vat += Decimal(125)
        ex_vat = ex_vat.quantize(Decimal("0.01"))
        total = (ex_vat * Decimal("1.21")).quantize(Decimal("0.01"))
        unit = (total / quantity).quantize(Decimal("0.01"))
        self.amounts += [ex_vat, total, unit]
        return ex_vat, total, unit

    def get_price(self, choices):
        product = next(p for p in DEMO_CATALOG["products"] if p["id"] == choices.product_id)
        size, quantity, options = product["customSize"], product["quantity"], product["options"]
        if min(choices.width_cm, choices.height_cm) < size["minCm"]:
            return Unpriced(reason="size_below_minimum", details={"minCm": size["minCm"]})
        if max(choices.width_cm, choices.height_cm) > size["maxCm"]:
            return Unpriced(reason="size_above_maximum", details={"maxCm": size["maxCm"]})
        if choices.quantity < quantity["min"]:
            return Unpriced(reason="quantity_below_minimum", details={"minQuantity": quantity["min"]})
        if choices.quantity > quantity["max"]:
            return Unpriced(reason="quantity_above_maximum", details={"maxQuantity": quantity["max"]})
        if choices.urgent and not options["urgency"]:
            return Unpriced(reason="option_unavailable", details={"option": "urgency"})
        if choices.urgent and choices.quantity > DEMO_CATALOG["settings"]["urgency"]["maxQuantity"]:
            return Unpriced(reason="urgency_quantity_exceeded", details={"maxQuantity": 500})
        ex_vat, total, unit = self._price(choices, choices.quantity)
        return PriceQuote(choices=choices, total=total, total_ex_vat=ex_vat, unit_price=unit,
                          discount_percent=Decimal(10) if choices.quantity >= 500 else Decimal(0),
                          breakdown={"promoPercent": 0}, properties=[])

    def get_price_tiers(self, choices, count):
        tiers = []
        for quantity in [q for q in (100, 250, 500, 1000, 2500, 5000) if q > choices.quantity][:count]:
            ex_vat, total, unit = self._price(choices, quantity)
            tiers.append(TierOffer(quantity=quantity, total=total, total_ex_vat=ex_vat, unit_price=unit))
        return tiers


class DemoFiles:
    def check_file(self, path, width_cm, height_cm):
        name = Path(path).name.lower()
        verdict = FileVerdict.UNUSABLE if "bad" in name else FileVerdict.WEAK if "weak" in name else FileVerdict.OK
        return FileReport(kind="raster", mime="image/png", verdict=verdict,
                          problems=[] if verdict == FileVerdict.OK else ["low_dpi"])


class DemoMockup:
    def make_mockup(self, design_path, context_hint, out_dir):
        return MockupResult(template_id="demo", image_path=f"{out_dir}/mockup.png")

    def make_offer_image(self, mockup_path, lines, production_term, valid_until, out_dir):
        return f"{out_dir}/offer.png"


class DemoCheckout:
    def __init__(self) -> None:
        self.count = 0

    def create_checkout(self, quote, contact, artwork_url, valid_until):
        self.count += 1
        return Checkout(draft_order_id=f"D{self.count}", invoice_url=f"https://pay.example/{self.count}",
                        total=quote.total)


class DemoCrm:
    def upsert_lead(self, contact, summary, quote, checkout, status):
        return "lead-demo"


class DemoHandoff:
    def handoff(self, contact, reason, summary, now):
        return None


class DemoKnowledge:
    def __init__(self, entries: list[KnowledgeEntry] | None = None) -> None:
        self.entries = DEMO_KNOWLEDGE if entries is None else entries

    def search(self, query, limit=5):
        words = [w for w in normalize(query).split(" ") if len(w) > 3]
        hits = [e for e in self.entries if e.status == "verified"
                and any(w in normalize(f"{e.topic} {e.question} {e.answer}") for w in words)]
        return hits[:limit]

    def topics(self):
        return sorted({e.topic for e in self.entries})


class ScriptedModel:
    """Model fals: joaca replicile scrise in caz."""

    def __init__(self) -> None:
        self.replies: list[ModelReply] = []
        self._ids = 0

    def load(self, script: list[dict]) -> None:
        self.replies = [self._reply(item) for item in script]

    def _reply(self, item: dict) -> ModelReply:
        if "text" in item:
            return ModelReply(text=item["text"])
        calls = item.get("tools") or [item]
        built = []
        for call in calls:
            self._ids += 1
            built.append(ToolCall(id=f"tu_{self._ids}", name=call["tool"], input=call.get("args", {})))
        return ModelReply(tool_calls=built, stop_reason="tool_use")

    def complete(self, *, system, tools, messages):
        if not self.replies:
            raise RuntimeError("scenariul nu mai are replici")
        return self.replies.pop(0)


class RecordingModel:
    """Tine minte ce unelte a chemat modelul, pentru verificarile din cazuri."""

    def __init__(self, inner: ModelPort) -> None:
        self.inner = inner
        self.tools: list[str] = []

    def complete(self, *, system, tools, messages):
        reply = self.inner.complete(system=system, tools=tools, messages=messages)
        self.tools += [call.name for call in reply.tool_calls]
        return reply


def load_cases(path: str | os.PathLike) -> list[dict]:
    cases = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.lstrip().startswith("//"):
            cases.append(json.loads(line))
    return cases


def _sourced(pricing: DemoPricing, knowledge: DemoKnowledge, suggestion: AssistSuggestion) -> list[Decimal]:
    amounts = list(pricing.amounts)
    for entry in knowledge.entries:
        amounts += [a for a in money_mentions(entry.answer) if a is not None]
    lines = suggestion.offer_lines
    amounts += [sum((line.total for line in lines), Decimal(0)), sum((line.total_ex_vat for line in lines), Decimal(0))]
    return amounts


def check(expect: dict, suggestion: AssistSuggestion, tools: list[str], sourced: list[Decimal],
          gaps: int) -> list[str]:
    """Verificari de cod: tipul sugestiei, uneltele chemate, sume numai din surse."""
    failures = []
    kinds = expect.get("kind")
    if kinds and suggestion.kind not in ([kinds] if isinstance(kinds, str) else kinds):
        failures.append(f"kind={suggestion.kind}, asteptat {kinds}")
    for name in expect.get("tools", []):
        if name not in tools:
            failures.append(f"unealta {name} nu a fost chemata (chemate: {tools})")
    for name in expect.get("no_tools", []):
        if name in tools:
            failures.append(f"unealta {name} nu trebuia chemata")
    if "handoff_reason" in expect:
        actual = suggestion.handoff_reason.value if suggestion.handoff_reason else None
        allowed = expect["handoff_reason"]
        if actual not in ([allowed] if isinstance(allowed, str) else allowed):
            failures.append(f"handoff_reason={actual}, asteptat {allowed}")
    haystack = normalize(suggestion.text)
    for needle in expect.get("contains", []):
        if normalize(needle) not in haystack:
            failures.append(f"textul nu contine: {needle}")
    for needle in expect.get("not_contains", []):
        if normalize(needle) in haystack:
            failures.append(f"textul contine: {needle}")
    for needle in expect.get("note_contains", []):
        if normalize(needle) not in normalize(suggestion.note_for_staff):
            failures.append(f"nota pentru om nu contine: {needle}")
    if "can_link" in expect and suggestion.can_create_payment_link != expect["can_link"]:
        failures.append(f"can_create_payment_link={suggestion.can_create_payment_link}")
    if "has_link" in expect and bool(suggestion.payment_url) != expect["has_link"]:
        failures.append(f"payment_url={suggestion.payment_url}")
    if "lines" in expect and len(suggestion.offer_lines) != expect["lines"]:
        failures.append(f"{len(suggestion.offer_lines)} linii de oferta, asteptat {expect['lines']}")
    if "min_gaps" in expect and gaps < expect["min_gaps"]:
        failures.append(f"{gaps} intrebari fara raspuns inregistrate, asteptat cel putin {expect['min_gaps']}")
    # Mereu: nicio suma in text care nu vine din calculator sau din baza de cunostinte.
    for amount in money_mentions(suggestion.text):
        if amount is None or not any(amount.quantize(Decimal("0.01")) == s.quantize(Decimal("0.01")) for s in sourced):
            failures.append(f"suma fara sursa in text: {amount}")
    if chr(0x2014) in suggestion.text:
        failures.append("textul contine linie de pauza")
    return failures


def run_case(case: dict, model: ModelPort | None = None, rules: Rules | None = None) -> list[str]:
    """Ruleaza un caz. Fara `model`, joaca replicile din caz. Intoarce lista de esecuri (goala = trecut)."""
    scripted = ScriptedModel() if model is None else None
    recorder = RecordingModel(scripted or model)
    pricing, knowledge = DemoPricing(), DemoKnowledge()
    if case.get("knowledge") == "empty":
        knowledge = DemoKnowledge([])
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as data_dir:
        engine = QuoteEngine(
            model=recorder, pricing=pricing, files=DemoFiles(), mockup=DemoMockup(), checkout=DemoCheckout(),
            crm=DemoCrm(), handoff=DemoHandoff(), knowledge=knowledge, store=InMemoryStore(),
            rules=rules or Rules.load(), data_dir=data_dir)
        contact = Contact(channel="whatsapp", key=f"eval-{case['name']}")
        transcript: list[AssistMessage] = []
        suggestion: AssistSuggestion | None = None
        for index, step in enumerate(case["steps"], start=1):
            for turn in step.get("turns", []):
                direction = "in" if "in" in turn else "out"
                file = turn.get("file")
                attachments = [Attachment(path=f"{data_dir}/{file['name']}", mime=file["mime"],
                                          filename=file["name"])] if file else []
                transcript.append(AssistMessage(
                    id=f"m{len(transcript) + 1}", direction=direction, text=turn.get(direction, ""),
                    sent_at=START + timedelta(minutes=len(transcript)), attachments=attachments))
            if scripted is not None:
                scripted.load(step.get("script", []))
            recorder.tools = []
            now = START + timedelta(minutes=len(transcript))
            try:
                if step.get("link"):
                    suggestion = engine.create_payment_link(suggestion.suggestion_id, "eval", now)
                else:
                    suggestion = engine.suggest(contact, list(transcript), now)
            except Exception as exc:  # un caz stricat nu opreste restul evaluarii
                failures.append(f"pasul {index}: {type(exc).__name__}: {exc}")
                break
            found = check(step.get("expect", {}), suggestion, recorder.tools, _sourced(pricing, knowledge, suggestion),
                          len(engine.knowledge_gaps()))
            failures += [f"pasul {index}: {f}" for f in found]
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Evaluarea scenariilor ec-quote in modul asistat.")
    parser.add_argument("--cases", required=True, help="fisier JSONL cu scenarii")
    parser.add_argument("--fake", action="store_true", help="foloseste replicile scrise in cazuri, fara retea")
    parser.add_argument("--only", help="ruleaza doar cazul cu acest nume")
    args = parser.parse_args(argv)

    cases = [c for c in load_cases(args.cases) if not args.only or c["name"] == args.only]
    model: ModelPort | None = None
    if not args.fake:
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print(f"SKIP: ANTHROPIC_API_KEY nu este setat; {len(cases)} cazuri nerulate. "
                  "Pentru replicile scrise in cazuri folositi --fake.")
            return 0
        from .model import AnthropicModel

        model = AnthropicModel()

    failed = 0
    for case in cases:
        failures = run_case(case, model)
        if failures:
            failed += 1
            print(f"FAIL {case['name']}")
            for failure in failures:
                print(f"     {failure}")
        else:
            print(f"PASS {case['name']}")
    print(f"{len(cases) - failed}/{len(cases)} cazuri trecute ({'model fals' if args.fake else 'model real'})")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
