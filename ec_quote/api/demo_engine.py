"""Motor demonstrativ pentru pagina de proba a widgetului si pentru proba modului asistat.

Nu este folosit in productie. In modul asistat, preturile provin exclusiv din FakeCalculator
(niciodata sume inventate in cod), ca panoul extensiei sa poata fi probat fara chei reale.
"""
from __future__ import annotations

import re
import struct
import threading
import uuid
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path

from ec_quote.agent import offer as offer_text
from ec_quote.agent.engine import ApprovalError
from ec_quote.agent.guard import normalize
from ec_quote.agent.rules import Rules, to_local
from ec_quote.contracts import (
    AssistMessage,
    AssistSuggestion,
    Button,
    Contact,
    HandoffReason,
    InboundMessage,
    LineChoices,
    OutboundAction,
    PriceQuote,
    Unpriced,
)
from ec_quote.pricing.fake import FAKE_CATALOG, LABEL_ID, STICKER_ID, FakeCalculator

_DEMO_OPTIONS = ["Rotundă, 5 cm, 500 buc", "Dreptunghiulară, 9 x 4 cm, 1000 buc", "Pe rolă, 500 buc"]
_DEMO_OFFER_NOTE = "Mod demonstrativ (prețuri din FakeCalculator, fără chei de producție)."
_UNUPLOADED_NOTE = (
    "Clientul a trimis un fișier în conversație; folosiți „Trimite fișierul la verificare” "
    "din panou pentru verificarea tehnică."
)

_RECT_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*[xX×]\s*(\d+(?:[.,]\d+)?)\s*(?:cm)?")
_SINGLE_CM = re.compile(r"(\d+(?:[.,]\d+)?)\s*cm\b")
_QTY_WITH_UNIT = re.compile(r"\b(\d{1,5})\s*(?:de\s+)?(?:buc\w*|etichet\w*|sticker\w*)\b")
_STANDALONE_QTY = re.compile(r"\b(\d{2,5})\b")

_COMPLAINT_WORDS = ("reclamat", "nemultumit", "gresit", "stricat", "defect")
_HUMAN_WORDS = ("coleg", "un om", "operator", "persoana reala", "consultant")
_DISCOUNT_WORDS = ("discount", "reducere", "negoci")


@dataclass
class _DemoRecord:
    key: str
    basis: tuple[str, int, int]
    status: str  # "pending" | "superseded" | "linked"
    suggestion: AssistSuggestion
    quote: PriceQuote | None = None


def write_png(path: Path, width: int = 480, height: int = 300) -> None:
    """Un PNG simplu (dungi), scris doar cu biblioteca standard."""
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            band = ((x + y) // 40) % 2
            rows += bytes((228, 87, 46)) if band else bytes((250, 240, 225))

    def chunk(kind: bytes, data: bytes) -> bytes:
        body = kind + data
        return struct.pack(">I", len(data)) + body + struct.pack(">I", zlib.crc32(body))

    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 6))
        + chunk(b"IEND", b"")
    )


def _dec(raw: str) -> Decimal:
    return Decimal(raw.replace(",", "."))


def _product_spec(product_id: str) -> dict:
    return next(p for p in FAKE_CATALOG["products"] if p["id"] == product_id)


def _extract_offer_choices(texts: list[str]) -> LineChoices | None:
    joined = " ".join(texts)
    plain = normalize(joined)
    latest = normalize(texts[-1]) if texts else ""

    rect_match = _RECT_SIZE.search(latest) or _RECT_SIZE.search(joined)
    cm_match = None if rect_match else (_SINGLE_CM.search(latest) or _SINGLE_CM.search(joined))
    qty_match = _QTY_WITH_UNIT.search(latest) or _QTY_WITH_UNIT.search(plain)
    if qty_match is None and ("ofert" in plain or rect_match or cm_match):
        qty_match = _STANDALONE_QTY.search(latest) or _STANDALONE_QTY.search(plain)

    wants_offer = bool("ofert" in plain or qty_match or rect_match or cm_match)
    if not wants_offer:
        return None

    is_roll = "rola" in plain or "pe rola" in plain
    product_id = LABEL_ID if is_roll else STICKER_ID
    spec = _product_spec(product_id)
    material = "Polipropilenă Albă" if is_roll else "Vinil Alb Lucios"

    if rect_match:
        shape = "rectangle"
        width_cm, height_cm = _dec(rect_match.group(1)), _dec(rect_match.group(2))
    elif "dreptunghi" in plain:
        shape = "rectangle"
        width_cm, height_cm = Decimal("9"), Decimal("4")
    else:
        shape = "circle"
        side = _dec(cm_match.group(1)) if cm_match else Decimal("5")
        width_cm, height_cm = side, side

    min_cm = Decimal(str(spec["customSize"]["minCm"]))
    max_cm = Decimal(str(spec["customSize"]["maxCm"]))
    width_cm = min(max(width_cm, min_cm), max_cm)
    height_cm = min(max(height_cm, min_cm), max_cm)

    min_qty = int(spec["quantity"]["min"])
    max_qty = int(spec["quantity"]["max"])
    default_qty = int(spec["quantity"]["default"])
    quantity = int(qty_match.group(1)) if qty_match else default_qty
    quantity = min(max(quantity, min_qty), max_qty)

    return LineChoices(
        product_id=product_id,
        material_name=material,
        shape=shape,
        width_cm=width_cm,
        height_cm=height_cm,
        quantity=quantity,
    )


class DemoEngine:
    def __init__(self, data_dir: Path, rules_path: Path | None = None):
        self._data_dir = Path(data_dir)
        self._rules = Rules.load(rules_path)
        self._pricing = FakeCalculator().client()
        self._pending: dict[str, str] = {}
        self._suggestions: dict[str, _DemoRecord] = {}
        self._active_by_chat: dict[str, str] = {}
        self._lock = threading.Lock()

    def _image(self, key: str, channel: str = "site", name: str = "demo-oferta.png") -> str:
        safe_key = re.sub(r"[^A-Za-z0-9_.-]", "_", key)
        path = self._data_dir / "conversations" / channel / safe_key / "out" / name
        if not path.exists():
            write_png(path)
        return str(path)

    # ---------- modul autonom (widgetul de proba) ----------

    def handle(self, message: InboundMessage) -> list[OutboundAction]:
        key = message.contact.key
        text = message.text.lower()
        if message.attachments:
            return [
                OutboundAction(kind="text", text="Am primit fișierul. Arată bine pentru tipar."),
                OutboundAction(kind="image", text="Simulare pe produs (exemplu demonstrativ).",
                               image_path=self._image(key)),
            ]
        if message.button_id == "demo_file" or "fisier" in text or "fișier" in text:
            return [OutboundAction(kind="text", text="Atașați fișierul cu butonul din stânga câmpului de mesaj.")]
        if message.button_id == "demo_human" or "coleg" in text:
            return [OutboundAction(kind="handoff", handoff_reason=HandoffReason.CUSTOMER_ASKED)]
        if message.button_id == "demo_offer" or "ofert" in text:
            approval_id = f"demo-{key[:8]}"
            self._pending[approval_id] = key
            return [OutboundAction(kind="pending_approval", approval_id=approval_id,
                                   text="Oferta demonstrativa, nevazuta de client pana la aprobare.")]
        return [
            OutboundAction(kind="text", text="Acesta este un mediu de probă, fără prețuri reale. "
                                             "Detalii: https://etichetecreative.ro"),
            OutboundAction(kind="buttons", text="Ce doriți să încercați?", buttons=[
                Button(id="demo_offer", title="Cer o ofertă"),
                Button(id="demo_file", title="Trimit un fișier"),
                Button(id="demo_human", title="Vorbesc cu un coleg"),
            ]),
        ]

    def approve(self, approval_id: str, approved_by: str, now: datetime,
                edited_text: str | None = None) -> list[OutboundAction]:
        key = self._pending.pop(approval_id)  # KeyError -> 404 in API
        return [OutboundAction(kind="image", text="Oferta dumneavoastră (exemplu demonstrativ).",
                               image_path=self._image(key))]

    def reject(self, approval_id: str, rejected_by: str, now: datetime) -> None:
        self._pending.pop(approval_id)

    # ---------- modul asistat (extensia Chrome pe WhatsApp Web) ----------

    def suggest(self, contact: Contact, messages: list[AssistMessage], now: datetime) -> AssistSuggestion:
        now_local = to_local(now)
        if not messages or messages[-1].direction == "out":
            return AssistSuggestion(suggestion_id=f"demo-{uuid.uuid4().hex[:12]}", kind="none")

        last = messages[-1]
        uploaded_count = sum(len(m.attachments) for m in messages if m.direction == "in")
        unuploaded_count = sum(
            len(m.unuploaded_attachments) for m in messages if m.direction == "in" and not m.attachments
        )
        basis = (last.id, uploaded_count, unuploaded_count)

        with self._lock:
            prev_id = self._active_by_chat.get(contact.key)
            prev = self._suggestions.get(prev_id) if prev_id else None
            if prev is not None and prev.status != "superseded" and prev.basis == basis:
                return prev.suggestion

            suggestion_id = f"demo-{uuid.uuid4().hex[:12]}"
            suggestion, quote = self._build_assist_suggestion(
                suggestion_id=suggestion_id,
                contact=contact,
                messages=messages,
                now=now_local,
                has_uploaded=uploaded_count > 0,
                has_unuploaded=unuploaded_count > 0 and uploaded_count == 0,
            )
            if prev is not None and prev.status == "pending":
                prev.status = "superseded"
            self._suggestions[suggestion_id] = _DemoRecord(
                key=contact.key,
                basis=basis,
                status="pending",
                suggestion=suggestion,
                quote=quote,
            )
            self._active_by_chat[contact.key] = suggestion_id
            return suggestion

    def _build_assist_suggestion(
        self,
        *,
        suggestion_id: str,
        contact: Contact,
        messages: list[AssistMessage],
        now: datetime,
        has_uploaded: bool,
        has_unuploaded: bool,
    ) -> tuple[AssistSuggestion, PriceQuote | None]:
        inbound_texts = [m.text for m in messages if m.direction == "in" and m.text.strip()]
        latest_plain = normalize(messages[-1].text)

        file_notes: list[str] = []
        if has_uploaded:
            file_notes.append("Fișier încărcat în conversație (mod demonstrativ).")
        elif has_unuploaded:
            file_notes.append(_UNUPLOADED_NOTE)

        if any(w in latest_plain for w in _COMPLAINT_WORDS):
            notes = ["Mod demonstrativ: reclamație sau client nemulțumit; răspunsul îl dă un coleg.", *file_notes]
            return AssistSuggestion(
                suggestion_id=suggestion_id,
                kind="needs_human",
                text=offer_text.assist_draft(HandoffReason.COMPLAINT),
                handoff_reason=HandoffReason.COMPLAINT,
                note_for_staff=" ".join(notes),
            ), None

        if any(w in latest_plain for w in _HUMAN_WORDS):
            notes = ["Mod demonstrativ: clientul a cerut legătura cu un coleg.", *file_notes]
            return AssistSuggestion(
                suggestion_id=suggestion_id,
                kind="needs_human",
                text="",
                handoff_reason=HandoffReason.CUSTOMER_ASKED,
                note_for_staff=" ".join(notes),
            ), None

        if any(w in latest_plain for w in _DISCOUNT_WORDS):
            notes = ["Mod demonstrativ: clientul cere reducere sau condiții speciale.", *file_notes]
            return AssistSuggestion(
                suggestion_id=suggestion_id,
                kind="needs_human",
                text="",
                handoff_reason=HandoffReason.SPECIAL_TERMS,
                note_for_staff=" ".join(notes),
            ), None

        choices = _extract_offer_choices(inbound_texts)
        if choices is not None:
            priced = self._pricing.get_price(choices)
            if not isinstance(priced, Unpriced):
                tiers = self._pricing.get_price_tiers(choices, self._rules.upsell_tier_count)
                lines = offer_text.build_lines(priced, tiers, self._rules.handoff_value_threshold_ron_ex_vat)
                valid_until = now + timedelta(days=self._rules.offer_validity_days)
                term = self._rules.production_term(False)
                title = _product_spec(choices.product_id)["title"]
                text = offer_text.build_offer_text(priced, lines, title, term, valid_until, None)
                image_path = self._image(contact.key, channel=contact.channel, name=f"{suggestion_id}.png")
                notes = [_DEMO_OFFER_NOTE, *file_notes]
                return AssistSuggestion(
                    suggestion_id=suggestion_id,
                    kind="offer",
                    text=text,
                    image_path=image_path,
                    offer_lines=lines,
                    can_create_payment_link=True,
                    note_for_staff=" ".join(notes),
                ), priced

        question_text = (
            "Bună ziua! Ce formă, dimensiune și cantitate doriți pentru etichete?\n"
            f"Variante: {', '.join(_DEMO_OPTIONS)}."
        )
        notes = ["Mod demonstrativ (fără chei de producție).", *file_notes]
        return AssistSuggestion(
            suggestion_id=suggestion_id,
            kind="question",
            text=question_text,
            options=list(_DEMO_OPTIONS),
            note_for_staff=" ".join(notes),
        ), None

    def create_payment_link(self, suggestion_id: str, staff: str, now: datetime,
                            edited_text: str | None = None) -> AssistSuggestion:
        with self._lock:
            record = self._suggestions.get(suggestion_id)
            if record is None:
                raise KeyError(suggestion_id)
            if record.status == "linked":
                return record.suggestion
            if record.status == "superseded" or record.quote is None or not record.suggestion.can_create_payment_link:
                raise ApprovalError("sugestia a fost inlocuita sau nu permite link de plata")
            url = f"https://etichetecreative.ro/plata/demo-{suggestion_id}"
            base = (edited_text if edited_text is not None else record.suggestion.text).strip()
            text = offer_text.with_payment_link(base, record.quote, url, signature=False)
            record.suggestion = record.suggestion.model_copy(update={
                "text": text,
                "payment_url": url,
                "can_create_payment_link": False,
            })
            record.status = "linked"
            return record.suggestion


def build_engine(settings, clock=None) -> DemoEngine:
    return DemoEngine(settings.data_dir, rules_path=settings.rules_path)
