"""Motorul: bucla manuala de unelte, verificarile decise in cod, modul asistat si modul autonom.

Mod asistat (AssistEngine): extensia trimite conversatia vizibila, motorul intoarce o sugestie;
un om o trimite. Mod autonom (Engine): chatul de pe site, cu predare catre om si mod umbra.
"""
from __future__ import annotations

import difflib
import inspect
import json
import logging
import os
import re
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

from pydantic import ValidationError

from ec_quote.contracts import (
    AssistMessage, AssistSuggestion, Attachment, Button, CheckoutPort, Contact, CrmPort, FilePort, FileVerdict,
    HandoffPort, HandoffReason, InboundMessage, KnowledgePort, LineChoices, MockupPort, OfferLine,
    OutboundAction, PendingAttachment, PriceQuote, PricingPort, Unpriced,
)

from . import offer as offer_text
from .guard import check_text, money_mentions, normalize
from .model import ModelPort, ModelReply, ToolCall
from .prompts import (
    BUTTON_TITLE_MAX, MAX_BUTTONS, MODE_ASSIST, MODE_AUTONOMOUS, build_system, wrap_customer, wrap_file, wrap_quote,
)
from .rules import Rules, to_local
from .store import (
    Approval, ConversationState, ConversationStore, InMemoryStore, KnowledgeGap, LoggedMessage, Suggestion,
)
from .tools import MODEL_HANDOFF_REASONS, TOOLS

log = logging.getLogger("ec_quote.agent")

_HUMAN_REQUEST = re.compile(
    r"(vorb\w*|discut\w*|legatura|contact\w*)\b.{0,30}\b"
    r"(un om|o persoana|cineva|un coleg|un operator|un consultant|un reprezentant|un angajat)\b"
    r"|\b(operator uman|om real|persoana reala|agent uman)\b")
_BOT_QUESTION = re.compile(
    r"\b(robot|bot|chatbot|inteligenta artificiala|chatgpt)\b.{0,40}\?"
    r"|\b(esti|sunteti|vorbesc cu)\b.{0,25}\b(un om|om real|robot|bot)\b")
_UNSUPPORTED_MIME = ("audio/", "video/")
_TRANSCRIPT_LIMIT = 30
_KEPT_QUOTES = 12
_KEPT_SEEN = 2000
_MAX_GUARD_RETRIES = 2
_EDITED_RATIO = 0.6
_WEEKDAYS = ["luni", "marti", "miercuri", "joi", "vineri", "sambata", "duminica"]
_UNUPLOADED_STAFF_NOTE = (
    "Clientul a trimis un fișier în conversație; folosiți „Trimite fișierul la verificare” "
    "din panou pentru verificarea tehnică."
)


class ApprovalError(Exception):
    """Aprobarea sau sugestia nu exista, a fost inlocuita, a expirat sau nu poate fi trimisa.

    `code` este stabil, pentru API: `not_found` (nu exista) sau `not_available` (exista, dar nu mai poate fi folosita).
    """

    NOT_FOUND = "not_found"
    NOT_AVAILABLE = "not_available"

    def __init__(self, message: str, code: str = NOT_AVAILABLE) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _Outcome:
    """Rezultatul unei unelte: date pentru model sau actiuni care incheie runda."""

    payload: dict | None = None
    actions: list[OutboundAction] | None = None
    is_error: bool = False


@dataclass
class _Assist:
    """Colecteaza sugestia rundei in modul asistat."""

    result: dict | None = None


@dataclass
class _Turn:
    catalog: dict
    assist: _Assist | None = None
    customer_text: str = ""
    question_rejections: int = 0
    guard_retries: int = 0
    catalog_terms: list[str] = field(default_factory=list)
    sources: list[str] = field(default_factory=list)       # intrarile din baza intoarse in aceasta runda
    source_amounts: list[Decimal] = field(default_factory=list)  # sumele publicate in acele intrari
    knowledge_misses: list[str] = field(default_factory=list)
    open_questions: list[str] = field(default_factory=list)  # intrebari deschise pentru proprietar


def _fail(message: str) -> _Outcome:
    return _Outcome(payload={"error": message}, is_error=True)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


def _same_money(left: Decimal, right: Decimal) -> bool:
    return left.quantize(Decimal("0.01")) == right.quantize(Decimal("0.01"))


class QuoteEngine:
    """Implementeaza contracts.AssistEngine si contracts.Engine. Toate dependintele sunt porturi injectate."""

    def __init__(
        self, *, model: ModelPort, pricing: PricingPort, files: FilePort, mockup: MockupPort,
        checkout: CheckoutPort, crm: CrmPort, handoff: HandoffPort,
        knowledge: KnowledgePort | None = None,
        store: ConversationStore | None = None, rules: Rules | None = None,
        data_dir: str | os.PathLike | None = None, max_model_steps: int = 10,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.model = model
        self.pricing = pricing
        self.files = files
        self.mockup = mockup
        self.checkout = checkout
        self.crm = crm
        self.handoff_port = handoff
        self.knowledge = knowledge
        self.store = store or InMemoryStore()
        self.rules = rules or Rules.load()
        self.data_dir = Path(data_dir or os.environ.get("EC_QUOTE_DATA_DIR") or "./data")
        self.max_model_steps = max_model_steps
        self._new_id = id_factory or (lambda: uuid.uuid4().hex)
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ================= mod asistat =================

    def suggest(self, contact: Contact, messages: list[AssistMessage], now: datetime) -> AssistSuggestion:
        now = to_local(now)
        with self._lock(contact.channel, contact.key):
            state = self.store.load(contact.channel, contact.key)
            is_new = state is None
            if state is None:
                state = ConversationState(channel=contact.channel, key=contact.key, contact=contact)
            else:
                state.contact = _merge_contact(state.contact, contact)
            previous = self.store.get_suggestion(state.last_suggestion_id) if state.last_suggestion_id else None

            ordered = _ordered(messages)
            seen = set(state.assist_seen)
            logged_by_id = {
                entry.meta.get("id"): entry
                for entry in self.store.recent_messages(state.channel, state.key, _TRANSCRIPT_LIMIT * 2)
                if entry.meta.get("id")
            }
            new_attachment = False
            for existing in ordered:
                if existing.id in seen and existing.direction == "in" and existing.attachments:
                    prev_entry = logged_by_id.get(existing.id)
                    prev_files = (prev_entry.meta.get("attachments") or []) if prev_entry is not None else []
                    if len(existing.attachments) > len(prev_files):
                        new_attachment = True
                        self._take_design(state, existing.attachments)
                        at = to_local(existing.sent_at) if existing.sent_at else now
                        self.store.append_message(state.channel, state.key, LoggedMessage(
                            direction="in",
                            text=existing.text,
                            at=at,
                            meta={"id": existing.id, "attachments": [_file_name(a) for a in existing.attachments]},
                        ))
            fresh = [m for m in ordered if m.id not in seen]
            for message in fresh:
                at = to_local(message.sent_at) if message.sent_at else now
                meta: dict = {
                    "id": message.id,
                    "attachments": [_file_name(a) for a in message.attachments],
                    "first_seen_at": now.isoformat(),
                }
                if message.sent_at is None:
                    meta["missing_sent_at"] = True
                if message.quoted_text:
                    meta["quoted_text"] = message.quoted_text
                if message.unuploaded_attachments and not message.attachments:
                    meta["unuploaded_attachments"] = [
                        u.model_dump(exclude_none=True) for u in message.unuploaded_attachments
                    ]
                self.store.append_message(state.channel, state.key, LoggedMessage(
                    direction="in" if message.direction == "in" else "staff", text=message.text, at=at, meta=meta))
                state.assist_seen.append(message.id)
                if message.direction == "in":
                    state.first_inbound_at = state.first_inbound_at or at
                    self._take_design(state, message.attachments)
                elif previous is not None and previous.outcome is None and previous.suggestion.text:
                    # Primul mesaj al omului dupa sugestie spune cat de utila a fost.
                    threshold = float(self.rules.raw.get("suggestion_similarity_threshold", _EDITED_RATIO))
                    previous.outcome = _match_outcome(previous.suggestion.text, message.text, threshold=threshold)
                    self.store.save_suggestion(previous)
            state.assist_seen = state.assist_seen[-_KEPT_SEEN:]
            if fresh or new_attachment:
                state.last_message_at = now
            if state.status in ("manual", "closed", "offer_pending_approval"):
                state.status = "collecting"  # in modul asistat nu exista tacere

            last = ordered[-1] if ordered else None
            fresh_in = [m for m in fresh if m.direction == "in"]
            if last is None or last.direction == "out":
                self.store.save(state)
                return self._none_suggestion()
            if not fresh_in and not new_attachment and self._still_valid(previous, last.id, now):
                self.store.save(state)
                return previous.suggestion

            has_unuploaded = any(
                m.direction == "in" and m.unuploaded_attachments and not m.attachments for m in ordered
            )
            if is_new:
                state.summary = (last.text or _format_unuploaded_plain(last.unuploaded_attachments))[:200]
                self._crm(state, "new")
            assist = _Assist()
            text = " ".join(m.text for m in fresh_in if m.text) or last.text
            plain = normalize(text)
            if not last.text.strip() and last.attachments and all(_unsupported(a) for a in last.attachments):
                voice = any(a.mime.startswith("audio/") for a in last.attachments)
                assist.result = {
                    "kind": "question",
                    "text": offer_text.VOICE_TEXT if voice else offer_text.UNSUPPORTED_FILE_TEXT,
                    "note_for_staff": ("Clientul a trimis un mesaj vocal; asistentul nu îl poate asculta."
                                       if voice else "Clientul a trimis un fișier care nu poate fi folosit ca grafică.")}
            elif _HUMAN_REQUEST.search(plain):
                self._handoff(state, HandoffReason.CUSTOMER_ASKED, "", now, assist=assist,
                              note="Clientul a cerut explicit să vorbească cu un om.")
            elif _BOT_QUESTION.search(plain):
                self._handoff(state, HandoffReason.CUSTOMER_ASKED, "", now, assist=assist,
                              note="Clientul întreabă dacă vorbește cu un robot. Răspunsul îl dă omul, în nume propriu.")
            else:
                inbound = InboundMessage(contact=state.contact, message_id=last.id, text=last.text,
                                         attachments=last.attachments, received_at=now)
                actions = self._run_model(state, inbound, now, assist=assist, current_id=last.id,
                                          current_assist=last, has_unuploaded=has_unuploaded)
                if assist.result is None:
                    assist.result = ({"kind": "reply", "text": actions[0].text} if actions
                                     else {"kind": "none", "note_for_staff": "Nu este nevoie de răspuns."})

            suggestion, record = self._record_suggestion(state, assist.result, last, now,
                                                         has_unuploaded=has_unuploaded)
            if previous is not None and previous.status == "pending":
                previous.status = "superseded"
                self.store.save_suggestion(previous)
            self.store.save_suggestion(record)
            state.last_suggestion_id = record.id
            state.first_reply_at = state.first_reply_at or now
            self.store.save(state)
            return suggestion

    def create_payment_link(self, suggestion_id: str, staff: str, now: datetime,
                            edited_text: str | None = None) -> AssistSuggestion:
        """Omul accepta oferta: abia acum se creeaza Draft Order."""
        now = to_local(now)
        record = self._linkable(suggestion_id, now)
        with self._lock(record.channel, record.key):
            record = self._linkable(suggestion_id, now)
            if record.status == "linked":
                return record.suggestion  # al doilea clic nu creeaza inca o comanda
            state = self.store.load(record.channel, record.key)
            if state is None:
                raise ApprovalError("conversatia sugestiei nu mai exista", ApprovalError.NOT_FOUND)
            quote = record.quotes[0]
            checkout = self.checkout.create_checkout(quote, state.contact, record.artwork_url, record.valid_until)
            if not _same_money(checkout.total, quote.total):
                raise ApprovalError("totalul din checkout difera de pretul calculatorului")

            base = (edited_text if edited_text is not None else record.suggestion.text or record.offer_text).strip()
            record.suggestion = record.suggestion.model_copy(update={
                "text": offer_text.with_payment_link(base, quote, checkout.invoice_url, signature=False,
                                                     language=record.language),
                "payment_url": checkout.invoice_url, "can_create_payment_link": False})
            record.status = "linked"
            record.linked_by = staff
            record.linked_at = now
            self.store.save_suggestion(record)
            for quote_id, known in state.quotes.items():
                if known == quote:
                    state.payment_links[quote_id] = checkout.invoice_url
            state.status = "offer_sent"
            self._crm(state, "offer_sent", quote=quote, checkout=checkout)
            self.store.save(state)
            return record.suggestion

    def assist_metrics(self, channel: str, key: str) -> dict:
        """Cat de utile au fost sugestiile: timp pana la sugestie si ce a trimis omul fata de text."""
        records = self.store.list_suggestions(channel, key)
        latencies = [r.latency_s for r in records if r.latency_s is not None]
        outcomes = {name: sum(1 for r in records if r.outcome == name) for name in ("exact", "edited", "ignored")}
        return {
            "suggestions": len(records),
            **outcomes,
            "unanswered": sum(1 for r in records if r.outcome is None),
            "links_created": sum(1 for r in records if r.status == "linked"),
            "avg_latency_s": sum(latencies) / len(latencies) if latencies else None,
            "items": [{"id": r.id, "kind": r.suggestion.kind, "created_at": r.created_at, "latency_s": r.latency_s,
                       "outcome": r.outcome, "status": r.status} for r in records],
        }

    def knowledge_gaps(self, since: datetime | None = None) -> list[KnowledgeGap]:
        """Intrebarile fara raspuns aprobat, ca proprietarul sa stie ce sa adauge in baza."""
        return self.store.list_gaps(to_local(since) if since else None)

    def _none_suggestion(self) -> AssistSuggestion:
        return AssistSuggestion(suggestion_id=self._new_id(), kind="none")

    @staticmethod
    def _still_valid(previous: Suggestion | None, last_id: str, now: datetime) -> bool:
        if previous is None or previous.status == "superseded" or previous.basis_message_id != last_id:
            return False
        return previous.valid_until is None or now <= to_local(previous.valid_until)

    def _linkable(self, suggestion_id: str, now: datetime) -> Suggestion:
        record = self.store.get_suggestion(suggestion_id)
        if record is None:
            raise ApprovalError(f"sugestie necunoscuta: {suggestion_id}", ApprovalError.NOT_FOUND)
        if record.status == "superseded":
            raise ApprovalError(f"sugestia {suggestion_id} a fost inlocuita de una mai noua")
        if record.status == "linked":
            return record
        if not record.suggestion.can_create_payment_link or len(record.quotes) != 1:
            raise ApprovalError(f"sugestia {suggestion_id} nu are o oferta pentru care se poate crea link")
        if record.valid_until is not None and now > to_local(record.valid_until):
            raise ApprovalError("oferta a expirat; trebuie refacuta")
        return record

    def _record_suggestion(self, state: ConversationState, result: dict, last: AssistMessage,
                           now: datetime, *, has_unuploaded: bool = False) -> tuple[AssistSuggestion, Suggestion]:
        result = dict(result)
        quotes = result.pop("quotes", [])
        valid_until = result.pop("valid_until", None)
        artwork_url = result.pop("artwork_url", None)
        full_offer = result.pop("offer_text", "")
        language = result.pop("language", "ro")
        notes = [result.get("note_for_staff", "")]
        if result.get("kind") != "none":
            notes.append(offer_text.file_staff_note(state.file_report))
            if has_unuploaded and state.design is None:
                notes.append(_UNUPLOADED_STAFF_NOTE)
        notes += [f"Nu avem un răspuns aprobat pentru: {q}" for q in result.pop("gaps", [])]
        result["note_for_staff"] = " ".join(n for n in notes if n)
        suggestion = AssistSuggestion(suggestion_id=self._new_id(), **result)
        customer_sent_at = to_local(last.sent_at) if last.sent_at else None
        basis_at = customer_sent_at or now
        record = Suggestion(
            id=suggestion.suggestion_id, channel=state.channel, key=state.key, created_at=now,
            basis_message_id=last.id, suggestion=suggestion, quotes=quotes, offer_text=full_offer,
            language=language, valid_until=valid_until, artwork_url=artwork_url,
            latency_s=max((now - basis_at).total_seconds(), 0.0),
            customer_sent_at=customer_sent_at,
            first_seen_at=now,
            file_verdict=state.file_report.verdict if state.file_report is not None else None,
        )
        return suggestion, record

    # ================= mod autonom (chatul de pe site) =================

    def handle(self, message: InboundMessage, message_id: str | None = None) -> list[OutboundAction]:
        contact = message.contact
        now = to_local(message.received_at)
        with self._lock(contact.channel, contact.key):
            inbound_id = message_id or message.message_id
            if inbound_id and not self.store.claim_inbound(contact.channel, contact.key, str(inbound_id)):
                return []  # acelasi mesaj, livrat a doua oara

            state = self.store.load(contact.channel, contact.key)
            is_new = state is None
            if state is None:
                state = ConversationState(channel=contact.channel, key=contact.key, contact=contact)
            else:
                state.contact = _merge_contact(state.contact, contact)
            previous_message_at = state.last_message_at
            state.last_message_at = now
            self.store.append_message(contact.channel, contact.key, LoggedMessage(
                direction="staff" if message.from_staff else "in", text=message.text, at=now,
                meta={"button_id": message.button_id, "attachments": [_file_name(a) for a in message.attachments]}))

            if message.from_staff:
                # Un om a raspuns din aplicatie: motorul tace.
                if state.status != "manual":
                    state.status = "manual"
                    state.manual_since = now
                    self._crm(state, "manual")
                self.store.save(state)
                return []

            if state.first_inbound_at is None:
                state.first_inbound_at = now
            if state.status == "manual":
                quiet = timedelta(hours=self.rules.manual_mode_quiet_hours)
                if previous_message_at is None or now - previous_message_at < quiet:
                    self.store.save(state)
                    return []
                self._reset_for_new_request(state)
            elif state.status == "closed":
                self._reset_for_new_request(state)

            self._take_design(state, message.attachments)
            if is_new:
                state.summary = message.text[:200]
                self._crm(state, "new")

            if not message.text.strip() and message.attachments and all(_unsupported(a) for a in message.attachments):
                voice = any(a.mime.startswith("audio/") for a in message.attachments)
                actions = [OutboundAction(
                    kind="text", text=offer_text.VOICE_TEXT if voice else offer_text.UNSUPPORTED_FILE_TEXT)]
            elif _HUMAN_REQUEST.search(normalize(message.text)):
                actions = self._handoff(state, HandoffReason.CUSTOMER_ASKED,
                                        "Clientul a cerut explicit sa vorbeasca cu un om.", now)
            else:
                actions = self._run_model(state, message, now)

            self._log_outbound(state, actions, now)
            self.store.save(state)
            return actions

    def approve(self, approval_id: str, approved_by: str, now: datetime,
                edited_text: str | None = None) -> list[OutboundAction]:
        """Mod umbra: abia aici se creeaza checkout-ul si pleaca linkul de plata."""
        now = to_local(now)
        approval = self._pending_approval(approval_id)
        with self._lock(approval.channel, approval.key):
            approval = self._pending_approval(approval_id)
            state = self.store.load(approval.channel, approval.key)
            if state is None:
                raise ApprovalError("conversatia aprobarii nu mai exista", ApprovalError.NOT_FOUND)
            if now > to_local(approval.valid_until):
                raise ApprovalError("oferta a expirat; trebuie refacuta")
            checkout = self.checkout.create_checkout(
                approval.quote, state.contact, approval.artwork_url, approval.valid_until)
            if not _same_money(checkout.total, approval.quote.total):
                raise ApprovalError("totalul din checkout difera de pretul calculatorului")

            base = approval.offer_text
            changed = False
            if edited_text is not None and edited_text.strip() != base.strip():
                base = edited_text.strip()
                changed = True
            actions = self._offer_actions(base, approval.quote, checkout.invoice_url, approval.image_path)

            approval.status = "approved"
            approval.decided_by = approved_by
            approval.decided_at = now
            approval.human_changed = changed
            self.store.save_approval(approval)
            if state.pending_approval_id == approval.id:
                state.pending_approval_id = None
            if state.status == "offer_pending_approval":
                state.status = "offer_sent"
            self._crm(state, "offer_sent", quote=approval.quote, checkout=checkout)
            self._log_outbound(state, actions, now)
            self.store.save(state)
            return actions

    def reject(self, approval_id: str, rejected_by: str, now: datetime) -> None:
        now = to_local(now)
        approval = self._pending_approval(approval_id)
        with self._lock(approval.channel, approval.key):
            approval = self._pending_approval(approval_id)
            approval.status = "rejected"
            approval.decided_by = rejected_by
            approval.decided_at = now
            approval.human_changed = True
            self.store.save_approval(approval)
            state = self.store.load(approval.channel, approval.key)
            if state is None:
                return
            state.pending_approval_id = None
            state.status = "manual"
            state.manual_since = now
            state.last_message_at = now
            try:
                self.handoff_port.handoff(state.contact, HandoffReason.OFFER_REJECTED,
                                          f"Oferta respinsa de {rejected_by}. {approval.summary}".strip(), now)
            except Exception:
                log.exception("handoff esuat la respingerea ofertei %s", approval_id)
            self._crm(state, "manual", quote=approval.quote)
            self.store.save(state)

    def reactivate(self, channel: str, key: str, now: datetime) -> bool:
        """Un om reda conversatia asistentului inainte de expirarea linistii."""
        with self._lock(channel, key):
            state = self.store.load(channel, key)
            if state is None or state.status != "manual":
                return False
            self._reset_for_new_request(state)
            self.store.save(state)
            return True

    def close(self, channel: str, key: str, now: datetime) -> bool:
        with self._lock(channel, key):
            state = self.store.load(channel, key)
            if state is None:
                return False
            state.status = "closed"
            self._crm(state, "closed")
            self.store.save(state)
            return True

    def metrics(self, channel: str, key: str) -> dict:
        """Timp pana la primul raspuns, pana la oferta si daca omul a modificat oferta."""
        state = self.store.load(channel, key)
        if state is None:
            return {}
        approval = self.store.get_approval(state.last_approval_id) if state.last_approval_id else None

        def seconds(end: datetime | None) -> float | None:
            if end is None or state.first_inbound_at is None:
                return None
            return (end - state.first_inbound_at).total_seconds()

        return {
            "status": state.status,
            "time_to_first_reply_s": seconds(state.first_reply_at),
            "time_to_offer_s": seconds(state.first_offer_at),
            "approval_status": approval.status if approval else None,
            "human_changed": approval.human_changed if approval else None,
        }

    # ================= bucla modelului =================

    def _run_model(self, state: ConversationState, message: InboundMessage, now: datetime,
                   assist: _Assist | None = None, current_id: str | None = None,
                   current_assist: AssistMessage | None = None,
                   has_unuploaded: bool = False) -> list[OutboundAction]:
        try:
            catalog = self.pricing.catalog()
        except Exception:
            log.exception("catalogul calculatorului nu a putut fi citit")
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 "Eroare tehnică: catalogul calculatorului este indisponibil.", now, assist=assist)
        customer_text = message.text or (
            _format_unuploaded_plain(current_assist.unuploaded_attachments)
            if current_assist and current_assist.unuploaded_attachments else ""
        )
        turn = _Turn(catalog=catalog, assist=assist, customer_text=customer_text,
                     catalog_terms=_catalog_terms(catalog))
        system = build_system(self.rules, catalog)
        messages: list[dict] = [{"role": "user", "content": [{"type": "text", "text": self._render_turn(
            state, message, now, assist is not None, current_id,
            current_assist=current_assist, has_unuploaded=has_unuploaded)}]}]
        problems: list[str] = []

        for _ in range(self.max_model_steps):
            try:
                reply = self.model.complete(system=system, tools=TOOLS, messages=messages)
            except Exception:
                log.exception("apelul catre model a esuat")
                return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                     "Eroare tehnică: modelul nu a răspuns.", now, assist=assist)
            if reply.stop_reason in ("refusal", "max_tokens"):
                break
            messages.append({"role": "assistant", "content": _assistant_content(reply)})

            if reply.tool_calls:
                results = []
                for call in reply.tool_calls:
                    outcome = self._dispatch(state, turn, call, now)
                    if outcome.actions is not None:
                        self._attach_gaps(turn)
                        return outcome.actions
                    result = {"type": "tool_result", "tool_use_id": call.id,
                              "content": json.dumps(outcome.payload, ensure_ascii=False, default=str)}
                    if outcome.is_error:
                        result["is_error"] = True
                    results.append(result)
                # Toate rezultatele intr-un singur mesaj.
                messages.append({"role": "user", "content": results})
                continue

            text = reply.text.strip()
            problems = self._guard(state, turn, text) if text else [
                "Raspunsul a fost gol. Raspunde clientului sau foloseste o unealta."]
            if not problems:
                if turn.knowledge_misses and not turn.sources:
                    # Fara raspuns aprobat nu pleaca un text improvizat.
                    return self._knowledge_gap(state, turn, now)
                self._attach_gaps(turn, {"kind": "reply", "text": text})
                return [OutboundAction(kind="text", text=text)]
            turn.guard_retries += 1
            if turn.guard_retries > _MAX_GUARD_RETRIES:
                break
            messages.append({"role": "user", "content": [{"type": "text", "text": _blocked_note(problems)}]})

        return self._gave_up(state, turn, now, problems)

    def _dispatch(self, state: ConversationState, turn: _Turn, call: ToolCall, now: datetime) -> _Outcome:
        handler = getattr(self, f"_tool_{call.name}", None)
        if handler is None:
            return _fail(f"Unealta necunoscuta: {call.name}")
        if not isinstance(call.input, dict):
            return _fail("Argumentele uneltei trebuie sa fie un obiect JSON.")
        try:
            return handler(state, turn, call.input, now)
        except (KeyError, TypeError, ValueError, InvalidOperation, ValidationError) as exc:
            return _fail(f"Argumente invalide pentru {call.name}: {exc}")
        except Exception:
            log.exception("unealta %s a esuat", call.name)
            return _fail(f"Serviciul din spatele {call.name} este indisponibil acum. "
                         "Daca nu poti continua fara el, foloseste handoff.")

    def _attach_gaps(self, turn: _Turn, default: dict | None = None) -> None:
        """Mod asistat: omul afla si de intrebarile ramase fara raspuns aprobat."""
        if turn.assist is None:
            return
        if turn.assist.result is None and default is not None:
            turn.assist.result = default
        if turn.assist.result is not None and turn.knowledge_misses and not turn.sources:
            turn.assist.result.setdefault("gaps", self._gap_notes(turn))

    def _gave_up(self, state: ConversationState, turn: _Turn, now: datetime,
                 problems: list[str]) -> list[OutboundAction]:
        if turn.assist is not None:
            detail = "Verificările au blocat textul: " + " ".join(problems) if problems else ""
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD, detail, now, assist=turn.assist)
        return self._misunderstood(state, turn, now, "Asistentul nu a reusit sa formuleze un raspuns valid.")

    def _knowledge_gap(self, state: ConversationState, turn: _Turn, now: datetime) -> list[OutboundAction]:
        note = f"Nu avem un răspuns aprobat pentru: {self._gap_notes(turn)[0]}"
        return self._handoff(state, HandoffReason.NOT_UNDERSTOOD, note, now, assist=turn.assist, note=note,
                             draft=offer_text.HOLDING_TEXT)

    # ================= unelte =================

    def _tool_find_products(self, state, turn: _Turn, args: dict, now) -> _Outcome:
        products = _products(turn.catalog)
        words = [w for w in normalize(str(args["query"])).split(" ") if len(w) > 2]
        scored = []
        for product in products:
            haystack = normalize(f"{product.get('title', '')} {product.get('handle', '')}")
            score = sum(1 for w in words if w in haystack)
            if score:
                scored.append((score, product))
        chosen = [p for _, p in sorted(scored, key=lambda item: -item[0])][:5] or products[:10]
        return _Outcome(payload={"products": [_product_summary(p) for p in chosen]})

    def _tool_search_knowledge(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        query = str(args["query"]).strip()
        subject = str(args.get("product_or_material") or "").strip()
        entries = self._search_knowledge(query, subject) if self.knowledge is not None and query else []
        if not entries:
            turn.knowledge_misses.append(query)
            opened = self._open_question(query)
            if opened and opened not in turn.open_questions:
                turn.open_questions.append(opened)
            self.store.add_gap(KnowledgeGap(channel=state.channel, key=state.key,
                                            question=turn.customer_text, query=query, at=now))
            return _Outcome(payload={
                "entries": [],
                "note": "Nu avem un raspuns aprobat. Nu improviza: un coleg va raspunde. Poti continua cu "
                        "restul cererii (pret, intrebari) fara sa afirmi nimic despre acest subiect."})
        for entry in entries:
            turn.sources.append(f"{entry.question} {entry.answer}")
            turn.source_amounts += self._published_amounts(entry.id)
        return _Outcome(payload={"entries": [
            {"id": e.id, "topic": e.topic, "question": e.question, "answer": e.answer, "applies_to": e.applies_to}
            for e in entries]})

    def _search_knowledge(self, query: str, subject: str) -> list:
        """Baza reala stie sa filtreze dupa produs (`applies_to`); o baza simpla primeste produsul in intrebare."""
        search = self.knowledge.search
        try:
            scoped = "applies_to" in inspect.signature(search).parameters
        except (TypeError, ValueError):
            scoped = False
        if scoped:
            found = list(search(query, limit=5, applies_to=subject)) if subject else []
            # Numele din catalog nu este mereu cel din baza: fara rezultat, cautam si fara produs.
            return found or list(search(query, limit=5))
        entries = list(search(f"{query} {subject}".strip(), limit=5))
        if subject:
            wanted = normalize(subject)
            narrowed = [e for e in entries
                        if not e.applies_to or any(wanted in normalize(a) or normalize(a) in wanted
                                                   for a in e.applies_to)]
            entries = narrowed or entries
        return entries

    def _open_question(self, query: str) -> str:
        """Intrebarea deschisa a proprietarului care a blocat raspunsul, daca baza o poate spune."""
        finder = getattr(self.knowledge, "open_question", None)
        if not callable(finder):
            return ""
        try:
            entry = finder(query)
        except Exception:
            log.exception("open_question a esuat")
            return ""
        if entry is None:
            return ""
        try:
            # Formularea pentru proprietar, cand baza o are; altfel intrebarea canonica.
            asked = getattr(self.knowledge.entry(entry.id), "owner_question", "")
        except Exception:
            asked = ""
        return str(asked or getattr(entry, "question", "") or "")

    def _published_amounts(self, entry_id: str) -> list[Decimal]:
        """Sumele publicate ale unei intrari (campul de redactare `amounts`), cand baza le expune."""
        lookup = getattr(self.knowledge, "entry", None)
        if not callable(lookup):
            return []
        try:
            authored = lookup(entry_id)
        except Exception:
            return []
        found: list[Decimal] = []
        for amount in getattr(authored, "amounts", None) or []:
            found += [a for a in money_mentions(str(getattr(amount, "text", amount))) if a is not None]
        return found

    def _gap_notes(self, turn: _Turn) -> list[str]:
        question = turn.customer_text or turn.knowledge_misses[0]
        notes = [question]
        notes += [f"(întrebare deschisă pentru proprietar: {q})" for q in turn.open_questions]
        return [" ".join(notes)]

    def _tool_get_price(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        add_ons = {str(item["group"]): str(item["choice"]) for item in args.get("add_ons") or []}
        choices = LineChoices(
            product_id=str(args["product_id"]), material_name=str(args["material_name"]),
            shape=str(args["shape"]), width_cm=_decimal(args["width_cm"]), height_cm=_decimal(args["height_cm"]),
            quantity=int(args["quantity"]), add_ons=add_ons,
            adhesive=args.get("adhesive", "standard"), white_print=bool(args.get("white_print", False)),
            cut=args.get("cut", "none"), urgent=bool(args.get("urgent", False)),
            file_editing=args.get("file_editing", "none"))
        if choices.quantity < 1 or choices.width_cm <= 0 or choices.height_cm <= 0:
            return _fail("Cantitatea si dimensiunile trebuie sa fie pozitive.")
        choices, problem = _match_catalog(turn.catalog, choices)
        if problem:
            return _fail(problem)

        result = self.pricing.get_price(choices)
        if isinstance(result, Unpriced):
            return _Outcome(payload={"status": "unpriced", "reason": result.reason, "details": result.details,
                                     "hint": offer_text.unpriced_hint(result.reason, result.details)})
        if result.total_ex_vat > self.rules.handoff_value_threshold_ron_ex_vat:
            # Peste prag decide codul: modelul nu vede pretul si nu poate propune oferta.
            return _Outcome(actions=self._over_threshold(state, turn, [result], now))

        state.quote_seq += 1
        quote_id = f"q{state.quote_seq}"
        state.quotes[quote_id] = result
        for old in list(state.quotes)[:-_KEPT_QUOTES]:
            state.quotes.pop(old, None)
            state.tiers.pop(old, None)
            state.payment_links.pop(old, None)
        state.misunderstandings = 0
        payload = {
            "status": "priced", "quote_id": quote_id, "quantity": result.choices.quantity,
            "total_with_vat": str(result.total), "total_ex_vat": str(result.total_ex_vat),
            "unit_price_with_vat": str(result.unit_price), "discount_percent": str(result.discount_percent),
            "cap_quantity": result.cap_quantity,
            "next": "create_checkout pentru oferta sau send_price_comparison pentru o comparatie. "
                    "Nu scrie pretul in text.",
        }
        promo = offer_text.promo_percent(result)
        if promo > 0:
            payload["active_promo_percent"] = str(promo)
        return _Outcome(payload=payload)

    def _tool_get_price_tiers(self, state: ConversationState, turn, args: dict, now) -> _Outcome:
        quote_id = str(args["quote_id"])
        quote = state.quotes.get(quote_id)
        if quote is None:
            return _fail(f"quote_id necunoscut: {quote_id}. Cheama intai get_price.")
        tiers = list(self.pricing.get_price_tiers(quote.choices, self.rules.upsell_tier_count))
        state.tiers[quote_id] = tiers
        return _Outcome(payload={"quote_id": quote_id, "tiers": [
            {"quantity": t.quantity, "total_with_vat": str(t.total), "total_ex_vat": str(t.total_ex_vat),
             "unit_price_with_vat": str(t.unit_price)} for t in tiers]})

    def _tool_check_file(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        if state.design is None:
            return _fail("Clientul nu a trimis niciun fisier.")
        report = self.files.check_file(state.design.path, _decimal(args["width_cm"]), _decimal(args["height_cm"]))
        state.file_report = report
        if report.verdict == FileVerdict.UNUSABLE and state.last_failed_file != state.design.path:
            state.last_failed_file = state.design.path
            state.file_failures += 1
            if state.file_failures >= self.rules.max_file_attempts:
                return _Outcome(actions=self._handoff(
                    state, HandoffReason.FILE_UNUSABLE,
                    f"Fișier inutilizabil după {state.file_failures} încercări: {', '.join(report.problems)}",
                    now, assist=turn.assist))
        return _Outcome(payload={
            "verdict": report.verdict.value, "kind": report.kind, "problems": report.problems,
            "dpi_at_size": str(report.dpi_at_size) if report.dpi_at_size is not None else None,
            "attempts_left": max(self.rules.max_file_attempts - state.file_failures, 0),
        })

    def _tool_make_mockup(self, state: ConversationState, turn, args: dict, now) -> _Outcome:
        if state.design is None:
            return _fail("Clientul nu a trimis niciun fisier; oferta se poate face si fara mockup.")
        if state.file_report is not None and state.file_report.verdict == FileVerdict.UNUSABLE:
            return _fail("Fisierul este inutilizabil; nu se poate face mockup.")
        result = self.mockup.make_mockup(state.design.path, str(args["context_hint"])[:80], self._out_dir(state))
        state.mockup_path = result.image_path
        return _Outcome(payload={"status": "ok", "template_id": result.template_id})

    def _quote_ids(self, state: ConversationState, args: dict) -> tuple[list[str], str | None]:
        raw = args.get("quote_ids") or ([args["quote_id"]] if args.get("quote_id") else [])
        ids = list(dict.fromkeys(str(q) for q in raw))
        if not ids:
            return [], "Lipseste quote_ids. Cheama intai get_price."
        missing = [q for q in ids if q not in state.quotes]
        if missing:
            return [], f"quote_id necunoscut: {', '.join(missing)}. Cheama intai get_price."
        return ids, None

    def _tool_create_checkout(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        ids, problem = self._quote_ids(state, args)
        if problem:
            return _fail(problem)
        language = _language(args)
        return _Outcome(actions=self._finalize_offer(state, turn, ids, str(args.get("summary", "")), now, language))

    def _tool_send_price_comparison(self, state: ConversationState, turn: _Turn, args: dict,
                                    now: datetime) -> _Outcome:
        ids, problem = self._quote_ids(state, args)
        if problem:
            return _fail(problem)
        intro = str(args.get("intro") or "").strip()
        closing = str(args.get("closing") or "").strip()
        problems = self._guard(state, turn, f"{intro} {closing}") if intro or closing else []
        if problems:
            turn.guard_retries += 1
            if turn.guard_retries > _MAX_GUARD_RETRIES:
                return _Outcome(actions=self._gave_up(state, turn, now, problems))
            return _fail(" ".join(problems))
        language = _language(args)
        quotes = [state.quotes[q] for q in ids]
        tiers = None
        if args.get("include_tiers"):
            tiers = state.tiers.get(ids[0])
            if tiers is None:
                tiers = list(self.pricing.get_price_tiers(quotes[0].choices, self.rules.upsell_tier_count))
                state.tiers[ids[0]] = tiers
            threshold = self.rules.handoff_value_threshold_ron_ex_vat
            tiers = [t for t in tiers if t.total_ex_vat <= threshold]
        titles = [_product_title(turn.catalog, q.choices.product_id) for q in quotes]
        text = offer_text.build_comparison_text(quotes, titles, tiers, intro, closing, language)
        if turn.assist is not None:
            turn.assist.result = {
                "kind": "reply", "text": text,
                "offer_lines": [offer_text.quote_line(q, t, language) for q, t in zip(quotes, titles)],
                "note_for_staff": "Comparație de preț compusă din calculator; nu este încă o ofertă cu link."}
        return _Outcome(actions=[OutboundAction(kind="text", text=text)])

    def _tool_no_reply(self, state: ConversationState, turn: _Turn, args: dict, now) -> _Outcome:
        if turn.assist is not None:
            turn.assist.result = {"kind": "none",
                                  "note_for_staff": f"Nu este nevoie de răspuns: {str(args.get('reason', ''))[:200]}"}
        return _Outcome(actions=[])

    def _tool_upsert_lead(self, state: ConversationState, turn, args: dict, now) -> _Outcome:
        state.summary = str(args["summary"])[:500]
        updates = {k: str(args[k])[:200] for k in ("name", "email") if args.get(k)}
        if updates:
            state.contact = state.contact.model_copy(update=updates)
        self._crm(state, state.status, quote=_last_quote(state))
        return _Outcome(payload={"status": "ok"})

    def _tool_handoff(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        reason = str(args["reason"])
        if reason not in MODEL_HANDOFF_REASONS:
            return _fail(f"Motiv invalid. Variante: {', '.join(MODEL_HANDOFF_REASONS)}")
        return _Outcome(actions=self._handoff(state, HandoffReason(reason), str(args.get("summary", ""))[:500], now,
                                              assist=turn.assist))

    def _tool_ask_customer(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        text = str(args["text"]).strip()
        kind = args.get("kind", "clarify")
        titles = []
        for raw in args.get("buttons") or []:
            title = str(raw).strip()
            if title and title not in titles:
                titles.append(title)
        if not text:
            return _fail("Intrebarea este goala.")
        assist = turn.assist
        over_cap = kind == "clarify" and state.questions_asked >= self.rules.max_clarifying_questions

        if kind == "not_understood" and assist is None:
            return _Outcome(actions=self._misunderstood(state, turn, now, text, question=text))
        if over_cap and assist is None:
            turn.question_rejections += 1
            if turn.question_rejections >= 2:
                return _Outcome(actions=self._handoff(
                    state, HandoffReason.NOT_UNDERSTOOD,
                    "Limita de intrebari de clarificare a fost atinsa fara o cerere completa.", now))
            return _fail("Limita de intrebari de clarificare a fost atinsa. Continua cu variantele obisnuite "
                         "din catalog (get_price) sau foloseste handoff cu motivul not_understood.")

        problems = self._guard(state, turn, " ".join([text, *titles]))
        if problems:
            turn.guard_retries += 1
            if turn.guard_retries > _MAX_GUARD_RETRIES:
                return _Outcome(actions=self._gave_up(state, turn, now, problems))
            return _fail(" ".join(problems))

        if assist is not None:
            return _Outcome(actions=self._assist_question(state, turn, text, titles, kind, over_cap, now))
        if kind == "clarify":
            state.questions_asked += 1
        fits = 0 < len(titles) <= MAX_BUTTONS and all(len(t) <= BUTTON_TITLE_MAX for t in titles)
        if fits:
            buttons = [Button(id=f"opt_{i}", title=t) for i, t in enumerate(titles, start=1)]
            state.pending_buttons = {b.id: b.title for b in buttons}
            return _Outcome(actions=[OutboundAction(kind="buttons", text=text, buttons=buttons)])
        state.pending_buttons = {}
        if titles:
            # Prea multe variante sau prea lungi pentru butoane: lista in text.
            text = "\n".join([text, *[f"{i}. {t}" for i, t in enumerate(titles, start=1)]])
        return _Outcome(actions=[OutboundAction(kind="text", text=text)])

    def _assist_question(self, state: ConversationState, turn: _Turn, text: str, titles: list[str], kind: str,
                         over_cap: bool, now: datetime) -> list[OutboundAction]:
        """Fara butoane: textul trebuie sa se inteleaga singur; limita de intrebari devine o nota pentru om."""
        notes = []
        if kind == "not_understood":
            state.misunderstandings += 1
            if state.misunderstandings >= self.rules.max_misunderstandings:
                return self._handoff(
                    state, HandoffReason.NOT_UNDERSTOOD,
                    f"Cererea nu a fost înțeleasă după {state.misunderstandings} schimburi.", now,
                    assist=turn.assist, draft=text)
            notes.append("Asistentul nu a înțeles cererea; verificați întrebarea înainte de trimitere.")
        if kind == "clarify":
            state.questions_asked += 1
            if over_cap:
                notes.append(f"S-au pus deja {self.rules.max_clarifying_questions} întrebări de clarificare "
                             "(limita recomandată). Luați în calcul un apel sau o ofertă cu variantele obișnuite.")
        plain = normalize(text)
        if titles and not all(normalize(t) in plain for t in titles):
            text = f"{text}\nVariante: {', '.join(titles)}."
        turn.assist.result = {"kind": "question", "text": text, "options": titles, "note_for_staff": " ".join(notes)}
        return [OutboundAction(kind="text", text=text)]

    # ================= oferta =================

    def _compose(self, state: ConversationState, turn: _Turn, quotes: list[PriceQuote], quote_id: str | None,
                 now: datetime, language: str) -> dict:
        """Liniile, textul si imaginea ofertei, numai din rezultatele calculatorului."""
        threshold = self.rules.handoff_value_threshold_ron_ex_vat
        titles = [_product_title(turn.catalog, q.choices.product_id) for q in quotes]
        valid_until = now + timedelta(days=self.rules.offer_validity_days)
        term = self.rules.production_term(any(q.choices.urgent for q in quotes))
        usable_file = state.design is not None and not (
            state.file_report is not None and state.file_report.verdict == FileVerdict.UNUSABLE)
        if usable_file and state.mockup_path is None:
            try:
                state.mockup_path = self.mockup.make_mockup(
                    state.design.path, state.summary[:80], self._out_dir(state)).image_path
            except Exception:
                log.exception("mockup esuat; oferta ramane fara mockup")

        if len(quotes) == 1:
            quote = quotes[0]
            tiers = state.tiers.get(quote_id) if quote_id else None
            if tiers is None:
                try:
                    tiers = list(self.pricing.get_price_tiers(quote.choices, self.rules.upsell_tier_count))
                    if quote_id:
                        state.tiers[quote_id] = tiers
                except Exception:
                    log.exception("treptele de cantitate nu au putut fi citite")
                    tiers = []
            lines = offer_text.build_lines(quote, tiers, threshold, language)
            text = offer_text.build_offer_text(quote, lines, titles[0], term, valid_until, state.file_report, language)
        else:
            lines = [offer_text.quote_line(q, t, language) for q, t in zip(quotes, titles)]
            text = offer_text.build_multi_offer_text(lines, term, valid_until, state.file_report, language)
        try:
            image_path = self.mockup.make_offer_image(
                state.mockup_path if usable_file else None, lines, term, valid_until, self._out_dir(state))
        except Exception:
            log.exception("imaginea de oferta nu a putut fi generata")
            image_path = None
        return {"lines": lines, "text": text, "image_path": image_path, "valid_until": valid_until,
                "artwork_url": state.design.public_url if state.design is not None else None}

    def _over_threshold(self, state: ConversationState, turn: _Turn, quotes: list[PriceQuote],
                        now: datetime) -> list[OutboundAction]:
        total_ex_vat = sum((q.total_ex_vat for q in quotes), Decimal(0))
        titles = [_product_title(turn.catalog, q.choices.product_id) for q in quotes]
        state.summary = "; ".join(", ".join(offer_text.choice_parts(q, t)) for q, t in zip(quotes, titles))[:500]
        summary = f"{state.summary}. Valoare fără TVA: {offer_text.format_money(total_ex_vat)} lei."
        if turn.assist is None:
            return self._handoff(state, HandoffReason.VALUE_OVER_THRESHOLD, summary, now, quote=quotes[0])
        # Un om se uita la sugestie: primeste pretul calculatorului, dar nu un text gata de trimis.
        offer = self._compose(state, turn, quotes, None, now, "ro")
        actions = self._handoff(state, HandoffReason.VALUE_OVER_THRESHOLD, state.summary, now,
                                quote=quotes[0] if len(quotes) == 1 else None, assist=turn.assist)
        turn.assist.result.update({
            "text": "", "image_path": offer["image_path"], "offer_lines": offer["lines"],
            "can_create_payment_link": len(quotes) == 1, "quotes": quotes, "offer_text": offer["text"],
            "valid_until": offer["valid_until"], "artwork_url": offer["artwork_url"]})
        if len(quotes) > 1:
            turn.assist.result["note_for_staff"] += (
                f" Total calculator: {offer_text.money_pair(*offer_text.sum_lines(offer['lines']))}.")
        return actions

    def _finalize_offer(self, state: ConversationState, turn: _Turn, quote_ids: list[str], summary: str,
                        now: datetime, language: str = "ro") -> list[OutboundAction]:
        quotes = [state.quotes[q] for q in quote_ids]
        assist = turn.assist
        if summary:
            state.summary = summary[:500]
        if sum((q.total_ex_vat for q in quotes), Decimal(0)) > self.rules.handoff_value_threshold_ron_ex_vat:
            return self._over_threshold(state, turn, quotes, now)

        single = quote_ids[0] if len(quote_ids) == 1 else None
        existing = state.payment_links.get(single) if single else None
        if existing:
            # Clientul cere din nou linkul: nu se creeaza o a doua comanda.
            offer = self._compose(state, turn, quotes, single, now, language)
            text = offer_text.with_payment_link(offer["text"], quotes[0], existing, signature=assist is None,
                                                language=language)
            if assist is not None:
                assist.result = {"kind": "offer", "text": text, "image_path": offer["image_path"],
                                 "offer_lines": offer["lines"], "payment_url": existing, "language": language,
                                 "note_for_staff": "Linkul de plată a fost deja creat pentru această ofertă."}
            return [OutboundAction(kind="text", text=text)]

        today = now.date()
        state.offer_times = [t for t in state.offer_times if (today - to_local(t).date()).days <= 1]
        if sum(1 for t in state.offer_times if to_local(t).date() == today) >= self.rules.max_offers_per_contact_per_day:
            actions = self._handoff(state, HandoffReason.OFFER_LIMIT,
                                    f"Limita zilnică de oferte automate atinsă. {state.summary}".strip(), now,
                                    quote=quotes[0], assist=assist)
            if assist is None:
                actions[0].text = f"{offer_text.OFFER_LIMIT_TEXT} {actions[0].text}"
            return actions

        offer = self._compose(state, turn, quotes, single, now, language)
        lines, text, image_path = offer["lines"], offer["text"], offer["image_path"]

        if assist is not None:
            self._mark_offer(state, now)
            note = "Ofertă compusă din calculator. Linkul de plată se creează la cerere, după ce clientul acceptă."
            if len(quotes) > 1:
                note = ("Ofertă cu mai multe produse, compusă din calculator. Linkul de plată pentru mai multe "
                        "linii nu se poate crea automat; creați comanda manual.")
            assist.result = {
                "kind": "offer", "text": text, "image_path": image_path, "offer_lines": lines,
                "can_create_payment_link": len(quotes) == 1, "note_for_staff": note, "quotes": quotes,
                "offer_text": text, "valid_until": offer["valid_until"], "artwork_url": offer["artwork_url"],
                "language": language}
            self._crm(state, "offer_suggested", quote=quotes[0])
            return [OutboundAction(kind="text", text=text)]

        if len(quotes) > 1:
            # CheckoutPort primeste o singura linie: linkul pentru mai multe produse il face un om.
            return self._handoff(state, HandoffReason.SPECIAL_TERMS,
                                 f"Oferta cu mai multe produse; linkul de plata trebuie creat manual. {state.summary}",
                                 now, quote=quotes[0])
        quote = quotes[0]
        if self.rules.shadow_mode:
            self._supersede_pending(state)
            approval = Approval(
                id=self._new_id(), channel=state.channel, key=state.key, created_at=now, quote=quote,
                lines=lines, offer_text=text, image_path=image_path, artwork_url=offer["artwork_url"],
                valid_until=offer["valid_until"], summary=state.summary)
            self.store.save_approval(approval)
            self._mark_offer(state, now)
            state.pending_approval_id = approval.id
            state.last_approval_id = approval.id
            state.status = "offer_pending_approval"
            self._crm(state, "offer_pending_approval", quote=quote)
            return [OutboundAction(kind="pending_approval", text=text, image_path=image_path, approval_id=approval.id)]

        try:
            checkout = self.checkout.create_checkout(quote, state.contact, offer["artwork_url"], offer["valid_until"])
        except Exception:
            log.exception("checkout-ul nu a putut fi creat")
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Eroare tehnica la crearea linkului de plata. {state.summary}".strip(), now, quote=quote)
        if not _same_money(checkout.total, quote.total):
            log.error("checkout %s are totalul %s, calculatorul %s", checkout.draft_order_id, checkout.total, quote.total)
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Totalul din checkout difera de pretul calculatorului. {state.summary}".strip(),
                                 now, quote=quote)
        self._supersede_pending(state)
        self._mark_offer(state, now)
        state.status = "offer_sent"
        state.payment_links[single] = checkout.invoice_url
        self._crm(state, "offer_sent", quote=quote, checkout=checkout)
        return self._offer_actions(text, quote, checkout.invoice_url, image_path, language)

    @staticmethod
    def _offer_actions(text: str, quote: PriceQuote, invoice_url: str, image_path: str | None,
                       language: str = "ro") -> list[OutboundAction]:
        actions = []
        if image_path:
            actions.append(OutboundAction(kind="image", image_path=image_path))
        actions.append(OutboundAction(
            kind="text", text=offer_text.with_payment_link(text, quote, invoice_url, language=language)))
        return actions

    def _mark_offer(self, state: ConversationState, now: datetime) -> None:
        state.offer_times.append(now)
        if state.first_offer_at is None:
            state.first_offer_at = now
        state.questions_asked = 0
        state.misunderstandings = 0
        state.pending_buttons = {}

    def _supersede_pending(self, state: ConversationState) -> None:
        if not state.pending_approval_id:
            return
        previous = self.store.get_approval(state.pending_approval_id)
        if previous is not None and previous.status == "pending":
            previous.status = "superseded"
            self.store.save_approval(previous)
        state.pending_approval_id = None

    def _pending_approval(self, approval_id: str) -> Approval:
        approval = self.store.get_approval(approval_id)
        if approval is None:
            raise ApprovalError(f"aprobare necunoscuta: {approval_id}", ApprovalError.NOT_FOUND)
        if approval.status != "pending":
            raise ApprovalError(f"aprobarea {approval_id} este deja {approval.status}")
        return approval

    # ================= predare, neintelegeri =================

    def _handoff(self, state: ConversationState, reason: HandoffReason, summary: str, now: datetime,
                 quote: PriceQuote | None = None, assist: _Assist | None = None, draft: str = "",
                 note: str = "") -> list[OutboundAction]:
        if summary:
            state.summary = summary[:500]
        if assist is not None:
            # Mod asistat: omul este deja in conversatie, deci nimic nu se opreste si nimic nu se anunta.
            shown = quote or (_last_quote(state) if reason == HandoffReason.SPECIAL_TERMS else None)
            assist.result = {
                "kind": "needs_human", "text": draft or offer_text.assist_draft(reason), "handoff_reason": reason,
                "note_for_staff": note or offer_text.staff_note(self.rules, reason, summary, shown)}
            state.pending_buttons = {}
            self._crm(state, "needs_human", quote=shown)
            return [OutboundAction(kind="handoff", text=assist.result["text"], handoff_reason=reason)]
        try:
            self.handoff_port.handoff(state.contact, reason, state.summary, now)
        except Exception:
            log.exception("handoff esuat pentru %s/%s", state.channel, state.key)
        self._supersede_pending(state)
        state.status = "manual"
        state.manual_since = now
        state.pending_buttons = {}
        self._crm(state, "manual", quote=quote or _last_quote(state))
        return [OutboundAction(kind="handoff", text=offer_text.handoff_text(self.rules, reason, now),
                               handoff_reason=reason)]

    def _misunderstood(self, state: ConversationState, turn: _Turn | None, now: datetime, summary: str,
                       question: str | None = None) -> list[OutboundAction]:
        """Mod autonom: dupa numarul permis de neintelegeri, conversatia merge la om."""
        state.misunderstandings += 1
        if state.misunderstandings >= self.rules.max_misunderstandings:
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Cerere neinteleasa dupa {state.misunderstandings} schimburi. {summary}"[:500], now)
        return [OutboundAction(kind="text", text=question or offer_text.NOT_UNDERSTOOD_TEXT)]

    def _reset_for_new_request(self, state: ConversationState) -> None:
        state.status = "collecting"
        state.manual_since = None
        state.questions_asked = 0
        state.misunderstandings = 0
        state.file_failures = 0
        state.last_failed_file = None
        state.pending_buttons = {}

    def _take_design(self, state: ConversationState, attachments: list[Attachment]) -> None:
        usable = [a for a in attachments if not _unsupported(a)]
        if usable:
            state.design = usable[-1]
            state.file_report = None
            state.mockup_path = None

    # ================= verificari pe textul modelului =================

    def _guard(self, state: ConversationState, turn: _Turn, text: str) -> list[str]:
        amounts: list[Decimal] = list(turn.source_amounts)
        percents: list[Decimal] = [self.rules.vat_percent, *_catalog_percents(turn.catalog)]
        for quote in state.quotes.values():
            amounts += [quote.total, quote.total_ex_vat, quote.unit_price]
            percents += [quote.discount_percent, offer_text.promo_percent(quote)]
        for tiers in state.tiers.values():
            for tier in tiers:
                amounts += [tier.total, tier.total_ex_vat, tier.unit_price]
        return check_text(
            text, allowed_amounts=amounts, allowed_percents=percents,
            approved_claims=self.rules.approved_material_claims, catalog_terms=turn.catalog_terms,
            allowed_terms=[t for t in (self.rules.production_term_standard, self.rules.production_term_urgent) if t],
            sources=turn.sources)

    # ================= context pentru model =================

    def _render_turn(self, state: ConversationState, message: InboundMessage, now: datetime,
                     assisted: bool = False, current_id: str | None = None,
                     current_assist: AssistMessage | None = None,
                     has_unuploaded: bool = False) -> str:
        left = max(self.rules.max_clarifying_questions - state.questions_asked, 0)
        rows = [
            f"Ora curenta: {now.strftime('%Y-%m-%d %H:%M')} (Europe/Bucharest), {_WEEKDAYS[now.weekday()]}.",
            MODE_ASSIST if assisted else MODE_AUTONOMOUS,
            f"Canal: {state.channel}. Starea conversatiei: {state.status}.",
            f"Intrebari de clarificare ramase: {left}.",
        ]
        if self.knowledge is not None:
            try:
                rows.append(f"Subiecte in baza de cunostinte: {', '.join(self.knowledge.topics())}.")
            except Exception:
                log.exception("subiectele bazei de cunostinte nu au putut fi citite")
        if state.design is not None:
            check = "neverificat"
            if state.file_report is not None:
                check = f"{state.file_report.verdict.value} {state.file_report.problems}"
            rows.append(f"Fisier de la client: {wrap_file(_file_name(state.design))} ({state.design.mime}); "
                        f"verificare: {check}; mockup: {'facut' if state.mockup_path else 'nefacut'}.")
        elif has_unuploaded:
            rows.append("Fisier de la client: trimis in conversatie, neincarcat inca pentru verificare tehnica.")
        else:
            rows.append("Fisier de la client: niciunul.")
        if state.quotes:
            rows.append("Oferte pretuite pana acum (din calculator):")
            for quote_id, quote in state.quotes.items():
                c = quote.choices
                link = " [link de plata deja creat]" if quote_id in state.payment_links else ""
                rows.append(
                    f"- {quote_id}: produs {c.product_id}, {c.shape}, {c.width_cm} x {c.height_cm} cm, "
                    f"{c.material_name}, {c.quantity} buc; total cu TVA {quote.total}, fara TVA {quote.total_ex_vat}{link}")

        history = self.store.recent_messages(state.channel, state.key, _TRANSCRIPT_LIMIT + 1)
        if current_id is not None:
            history = [entry for entry in history if entry.meta.get("id") != current_id]
        else:
            history = history[:-1]
        if history:
            rows.append("")
            rows.append("Conversatia de pana acum:")
            for entry in history:
                stamp = to_local(entry.at).strftime("%d.%m %H:%M")
                quoted = entry.meta.get("quoted_text")
                quote_part = f" [raspuns la: {wrap_quote(str(quoted))}]" if quoted else ""
                if entry.direction == "in":
                    files = entry.meta.get("attachments") or []
                    pending = entry.meta.get("unuploaded_attachments") or []
                    if files:
                        extra = f" [fisiere: {wrap_file(', '.join(files))}]"
                    elif pending:
                        extra = f" [atasamente neincarcate: {_format_unuploaded_dicts(pending)}]"
                    else:
                        extra = ""
                    rows.append(f"[client {stamp}]{quote_part} {wrap_customer(entry.text)}{extra}")
                elif entry.direction == "staff":
                    rows.append(f"[coleg {stamp}]{quote_part} {wrap_customer(entry.text)}")
                elif entry.meta.get("kind") == "pending_approval":
                    rows.append(f"[sistem {stamp}] Oferta pregatita, asteapta aprobarea unui coleg.")
                else:
                    rows.append(f"[asistent {stamp}] {entry.text}")

        text = message.text
        if message.button_id:
            chosen = state.pending_buttons.get(message.button_id)
            text = chosen if chosen and not text else (text or message.button_id)
        rows.append("")
        rows.append("Mesajul curent al clientului:")
        if current_assist is not None and current_assist.quoted_text:
            rows.append(f"Raspuns la mesajul citat: {wrap_quote(current_assist.quoted_text)}")
        rows.append(wrap_customer(text))
        if message.attachments:
            rows.append(f"Fisiere atasate acum: {wrap_file(', '.join(_file_name(a) for a in message.attachments))}")
        elif current_assist is not None and current_assist.unuploaded_attachments:
            rows.append("Atasamente trimise de client (neincarcate inca pentru verificare): "
                        f"{_format_unuploaded(current_assist.unuploaded_attachments)}")
        return "\n".join(rows)

    # ================= utilitare =================

    def _lock(self, channel: str, key: str) -> threading.Lock:
        with self._locks_guard:
            return self._locks.setdefault((channel, key), threading.Lock())

    def _out_dir(self, state: ConversationState) -> str:
        safe_key = re.sub(r"[^A-Za-z0-9_-]", "_", state.key)
        path = self.data_dir / "out" / state.channel / safe_key
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def _crm(self, state: ConversationState, status: str, quote: PriceQuote | None = None, checkout=None) -> None:
        # CRM-ul nu are voie sa blocheze conversatia.
        try:
            state.lead_id = self.crm.upsert_lead(state.contact, state.summary, quote, checkout, status) or state.lead_id
        except Exception:
            log.exception("upsert_lead esuat pentru %s/%s", state.channel, state.key)

    def _log_outbound(self, state: ConversationState, actions: list[OutboundAction], now: datetime) -> None:
        for action in actions:
            self.store.append_message(state.channel, state.key, LoggedMessage(
                direction="out", text=action.text, at=now,
                meta={"kind": action.kind, "buttons": [b.title for b in action.buttons],
                      "image": bool(action.image_path),
                      "handoff_reason": action.handoff_reason.value if action.handoff_reason else None,
                      "approval_id": action.approval_id}))
        reaches_customer = any(a.kind != "pending_approval" for a in actions)
        if reaches_customer and state.first_reply_at is None:
            state.first_reply_at = now


# ================= functii pure =================

def _merge_contact(known: Contact, incoming: Contact) -> Contact:
    updates = {k: v for k, v in incoming.model_dump().items() if v is not None}
    return known.model_copy(update=updates)


def _ordered(messages: list[AssistMessage]) -> list[AssistMessage]:
    """Fara dubluri; dupa ora trimiterii cand toate o au, altfel in ordinea primita."""
    unique = list({m.id: m for m in messages}.values())
    if unique and all(m.sent_at is not None for m in unique):
        return sorted(unique, key=lambda m: to_local(m.sent_at))
    return unique


def _match_outcome(suggested: str, sent: str, *, threshold: float = _EDITED_RATIO) -> str:
    left, right = normalize(suggested), normalize(sent)
    if left == right:
        return "exact"
    return "edited" if difflib.SequenceMatcher(None, left, right).ratio() >= threshold else "ignored"


def _file_name(attachment: Attachment) -> str:
    return attachment.filename or Path(attachment.path).name


def _format_unuploaded(items: list[PendingAttachment]) -> str:
    parts = []
    for item in items:
        label = "imagine" if item.kind == "image" else "document"
        parts.append(f"{label} ({wrap_file(item.filename)})" if item.filename else label)
    return ", ".join(parts)


def _format_unuploaded_dicts(items: list[dict]) -> str:
    parts = []
    for item in items:
        label = "imagine" if item.get("kind") == "image" else "document"
        filename = item.get("filename")
        parts.append(f"{label} ({wrap_file(str(filename))})" if filename else label)
    return ", ".join(parts)


def _format_unuploaded_plain(items: list[PendingAttachment]) -> str:
    labels = ["imagine" if item.kind == "image" else "document" for item in items]
    return f"[fișier trimis: {', '.join(labels)}]" if labels else ""


def _unsupported(attachment: Attachment) -> bool:
    return attachment.mime.lower().startswith(_UNSUPPORTED_MIME)


def _language(args: dict) -> str:
    language = str(args.get("language") or "ro")
    return language if language in offer_text.LANGUAGES else "ro"


def _assistant_content(reply: ModelReply) -> object:
    if reply.raw_content is not None:
        return reply.raw_content
    content: list[dict] = []
    if reply.text:
        content.append({"type": "text", "text": reply.text})
    for call in reply.tool_calls:
        content.append({"type": "tool_use", "id": call.id, "name": call.name, "input": call.input})
    return content


def _blocked_note(problems: list[str]) -> str:
    return ("[Nota de sistem] Mesajul tau nu a fost trimis clientului. " + " ".join(problems)
            + " Rescrie raspunsul sau foloseste unealta potrivita.")


def _last_quote(state: ConversationState) -> PriceQuote | None:
    return next(reversed(state.quotes.values()), None) if state.quotes else None


def _products(catalog: dict) -> list[dict]:
    products = catalog.get("products") if isinstance(catalog, dict) else None
    return [p for p in products if isinstance(p, dict)] if isinstance(products, list) else []


def _product_title(catalog: dict, product_id: str) -> str:
    for product in _products(catalog):
        if str(product.get("id")) == product_id:
            return str(product.get("title") or "")
    return ""


def _material_names(product: dict) -> list[str]:
    names = []
    for material in product.get("materials") or []:
        names.append(str(material.get("name")) if isinstance(material, dict) else str(material))
    return names


def _product_summary(product: dict) -> dict:
    keep = ("id", "title", "shapes", "customSize", "sizesByShape", "addOnGroups", "quantity", "options")
    summary = {k: product[k] for k in keep if k in product}
    summary["materials"] = _material_names(product)
    return summary


def _catalog_terms(catalog: dict) -> list[str]:
    """Denumiri din catalog pe care modelul are voie sa le repete intocmai."""
    terms: list[str] = []
    for product in _products(catalog):
        terms.append(str(product.get("title") or ""))
        terms += _material_names(product)
        terms += [str(s) for s in product.get("shapes") or []]
        for group in product.get("addOnGroups") or []:
            if isinstance(group, dict):
                terms.append(str(group.get("name") or ""))
                terms += [str(c.get("name") or "") for c in group.get("choices") or [] if isinstance(c, dict)]
    return [t for t in terms if t]


def _catalog_percents(catalog: dict) -> list[Decimal]:
    """Reducerile de cantitate din catalog: singurele procente pe care modelul le poate repeta."""
    found: list[Decimal] = []
    for product in _products(catalog):
        quantity = product.get("quantity")
        for tier in (quantity.get("tiers") or []) if isinstance(quantity, dict) else []:
            try:
                found.append(Decimal(str(tier.get("discountPercent"))))
            except (AttributeError, InvalidOperation):
                continue
    return found


def _pick(value: str, options: list[str]) -> str | None:
    wanted = normalize(value)
    return next((o for o in options if normalize(o) == wanted), None)


def _match_catalog(catalog: dict, choices: LineChoices) -> tuple[LineChoices, str | None]:
    """Produsul, materialul si forma trebuie sa existe in catalog; ortografia se aliniaza la catalog."""
    products = _products(catalog)
    if not products:
        return choices, None  # catalog in alt format: decide calculatorul
    product = next((p for p in products if str(p.get("id")) == choices.product_id), None)
    if product is None:
        ids = ", ".join(f"{p.get('id')} ({p.get('title')})" for p in products[:20])
        return choices, f"product_id nu exista in catalog. Produse disponibile: {ids}"
    updates: dict[str, str] = {}
    materials = _material_names(product)
    if materials:
        material = _pick(choices.material_name, materials)
        if material is None:
            return choices, (f"Materialul nu exista pentru acest produs. Materiale: {', '.join(materials)}. "
                             "Daca niciunul nu se potriveste, foloseste handoff cu motivul not_in_calculator.")
        updates["material_name"] = material
    shapes = [str(s) for s in product.get("shapes") or []]
    if shapes:
        shape = _pick(choices.shape, shapes)
        if shape is None:
            return choices, f"Forma nu exista pentru acest produs. Forme: {', '.join(shapes)}."
        updates["shape"] = shape
    return choices.model_copy(update=updates), None
