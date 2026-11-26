"""Motorul de conversatie: bucla manuala de unelte, regulile de predare decise in cod, modul umbra."""
from __future__ import annotations

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
    Button, CheckoutPort, Contact, CrmPort, FilePort, FileVerdict, HandoffPort, HandoffReason,
    InboundMessage, LineChoices, MockupPort, OutboundAction, PriceQuote, PricingPort, Unpriced,
)

from . import offer as offer_text
from .guard import check_text, normalize
from .model import ModelPort, ModelReply, ToolCall
from .prompts import BUTTON_TITLE_MAX, MAX_BUTTONS, build_system, wrap_customer, wrap_file
from .rules import Rules, to_local
from .store import Approval, ConversationState, ConversationStore, InMemoryStore, LoggedMessage
from .tools import MODEL_HANDOFF_REASONS, TOOLS

log = logging.getLogger("ec_quote.agent")

_HUMAN_REQUEST = re.compile(
    r"(vorb\w*|discut\w*|legatura|contact\w*)\b.{0,30}\b"
    r"(un om|o persoana|cineva|un coleg|un operator|un consultant|un reprezentant|un angajat)\b"
    r"|\b(operator uman|om real|persoana reala|agent uman)\b")
_TRANSCRIPT_LIMIT = 30
_KEPT_QUOTES = 10
_MAX_GUARD_RETRIES = 2
_WEEKDAYS = ["luni", "marti", "miercuri", "joi", "vineri", "sambata", "duminica"]


class ApprovalError(Exception):
    """Aprobarea nu exista, nu mai este in asteptare sau nu poate fi trimisa."""


@dataclass
class _Outcome:
    """Rezultatul unei unelte: date pentru model sau actiuni care incheie runda."""

    payload: dict | None = None
    actions: list[OutboundAction] | None = None
    is_error: bool = False


@dataclass
class _Turn:
    catalog: dict
    question_rejections: int = 0
    guard_retries: int = 0
    catalog_terms: list[str] = field(default_factory=list)


def _fail(message: str) -> _Outcome:
    return _Outcome(payload={"error": message}, is_error=True)


def _decimal(value: object) -> Decimal:
    return Decimal(str(value))


class QuoteEngine:
    """Implementeaza contracts.Engine. Toate dependintele sunt porturi injectate."""

    def __init__(
        self, *, model: ModelPort, pricing: PricingPort, files: FilePort, mockup: MockupPort,
        checkout: CheckoutPort, crm: CrmPort, handoff: HandoffPort,
        store: ConversationStore | None = None, rules: Rules | None = None,
        data_dir: str | os.PathLike | None = None, max_model_steps: int = 8,
        id_factory: Callable[[], str] | None = None,
    ) -> None:
        self.model = model
        self.pricing = pricing
        self.files = files
        self.mockup = mockup
        self.checkout = checkout
        self.crm = crm
        self.handoff_port = handoff
        self.store = store or InMemoryStore()
        self.rules = rules or Rules.load()
        self.data_dir = Path(data_dir or os.environ.get("EC_QUOTE_DATA_DIR") or "./data")
        self.max_model_steps = max_model_steps
        self._new_id = id_factory or (lambda: uuid.uuid4().hex)
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._locks_guard = threading.Lock()

    # ---------- API public ----------

    def handle(self, message: InboundMessage, message_id: str | None = None) -> list[OutboundAction]:
        contact = message.contact
        now = to_local(message.received_at)
        with self._lock(contact.channel, contact.key):
            inbound_id = message_id or getattr(message, "message_id", None)
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
                meta={"button_id": message.button_id,
                      "attachments": [a.filename or Path(a.path).name for a in message.attachments]}))

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

            if message.attachments:
                state.design = message.attachments[-1]
                state.file_report = None
                state.mockup_path = None
            if is_new:
                state.summary = message.text[:200]
                self._crm(state, "new")

            if _HUMAN_REQUEST.search(normalize(message.text)):
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
                raise ApprovalError("conversatia aprobarii nu mai exista")
            if now > to_local(approval.valid_until):
                raise ApprovalError("oferta a expirat; trebuie refacuta")
            checkout = self.checkout.create_checkout(
                approval.quote, state.contact, approval.artwork_url, approval.valid_until)
            if checkout.total.quantize(Decimal("0.01")) != approval.quote.total.quantize(Decimal("0.01")):
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
                # Contractul nu are un motiv dedicat pentru oferta respinsa.
                self.handoff_port.handoff(state.contact, HandoffReason.SPECIAL_TERMS,
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

    # ---------- bucla modelului ----------

    def _run_model(self, state: ConversationState, message: InboundMessage, now: datetime) -> list[OutboundAction]:
        try:
            catalog = self.pricing.catalog()
        except Exception:
            log.exception("catalogul calculatorului nu a putut fi citit")
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 "Eroare tehnica: catalogul calculatorului este indisponibil.", now)
        turn = _Turn(catalog=catalog, catalog_terms=_catalog_terms(catalog))
        system = build_system(self.rules, catalog)
        messages: list[dict] = [
            {"role": "user", "content": [{"type": "text", "text": self._render_turn(state, message, now)}]}]

        for _ in range(self.max_model_steps):
            try:
                reply = self.model.complete(system=system, tools=TOOLS, messages=messages)
            except Exception:
                log.exception("apelul catre model a esuat")
                return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                     "Eroare tehnica: modelul nu a raspuns.", now)
            if reply.stop_reason in ("refusal", "max_tokens"):
                break
            messages.append({"role": "assistant", "content": _assistant_content(reply)})

            if reply.tool_calls:
                results = []
                for call in reply.tool_calls:
                    outcome = self._dispatch(state, turn, call, now)
                    if outcome.actions is not None:
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
                return [OutboundAction(kind="text", text=text)]
            turn.guard_retries += 1
            if turn.guard_retries > _MAX_GUARD_RETRIES:
                break
            messages.append({"role": "user", "content": [{"type": "text", "text": _blocked_note(problems)}]})

        return self._misunderstood(state, now, "Asistentul nu a reusit sa formuleze un raspuns valid.")

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

    # ---------- unelte ----------

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
            return _Outcome(payload={"status": "unpriced", "reason": result.reason, "details": result.details})
        if result.total_ex_vat > self.rules.handoff_value_threshold_ron_ex_vat:
            # Peste prag decide codul: modelul nu vede pretul si nu poate trimite oferta.
            state.summary = self._choices_summary(turn, result)
            return _Outcome(actions=self._handoff(
                state, HandoffReason.VALUE_OVER_THRESHOLD,
                f"{state.summary}. Valoare fara TVA: {result.total_ex_vat} RON.", now, quote=result))

        state.quote_seq += 1
        quote_id = f"q{state.quote_seq}"
        state.quotes[quote_id] = result
        for old in list(state.quotes)[:-_KEPT_QUOTES]:
            state.quotes.pop(old, None)
            state.tiers.pop(old, None)
        state.misunderstandings = 0
        return _Outcome(payload={
            "status": "priced", "quote_id": quote_id, "quantity": result.choices.quantity,
            "total_with_vat": str(result.total), "total_ex_vat": str(result.total_ex_vat),
            "unit_price": str(result.unit_price), "discount_percent": str(result.discount_percent),
            "cap_quantity": result.cap_quantity,
            "next": "get_price_tiers, apoi create_checkout. Nu scrie pretul in text.",
        })

    def _tool_get_price_tiers(self, state: ConversationState, turn, args: dict, now) -> _Outcome:
        quote_id = str(args["quote_id"])
        quote = state.quotes.get(quote_id)
        if quote is None:
            return _fail(f"quote_id necunoscut: {quote_id}. Cheama intai get_price.")
        tiers = list(self.pricing.get_price_tiers(quote.choices, self.rules.upsell_tier_count))
        state.tiers[quote_id] = tiers
        return _Outcome(payload={"quote_id": quote_id, "tiers": [
            {"quantity": t.quantity, "total_with_vat": str(t.total), "total_ex_vat": str(t.total_ex_vat),
             "unit_price": str(t.unit_price)} for t in tiers]})

    def _tool_check_file(self, state: ConversationState, turn, args: dict, now: datetime) -> _Outcome:
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
                    f"Fisier inutilizabil dupa {state.file_failures} incercari: {', '.join(report.problems)}", now))
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

    def _tool_create_checkout(self, state: ConversationState, turn: _Turn, args: dict, now: datetime) -> _Outcome:
        quote_id = str(args["quote_id"])
        if quote_id not in state.quotes:
            return _fail(f"quote_id necunoscut: {quote_id}. Cheama intai get_price.")
        return _Outcome(actions=self._finalize_offer(state, turn, quote_id, str(args.get("summary", "")), now))

    def _tool_upsert_lead(self, state: ConversationState, turn, args: dict, now) -> _Outcome:
        state.summary = str(args["summary"])[:500]
        updates = {k: str(args[k])[:200] for k in ("name", "email") if args.get(k)}
        if updates:
            state.contact = state.contact.model_copy(update=updates)
        self._crm(state, state.status, quote=_last_quote(state))
        return _Outcome(payload={"status": "ok"})

    def _tool_handoff(self, state: ConversationState, turn, args: dict, now: datetime) -> _Outcome:
        reason = str(args["reason"])
        if reason not in MODEL_HANDOFF_REASONS:
            return _fail(f"Motiv invalid. Variante: {', '.join(MODEL_HANDOFF_REASONS)}")
        return _Outcome(actions=self._handoff(state, HandoffReason(reason), str(args.get("summary", ""))[:500], now))

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

        if kind == "not_understood":
            return _Outcome(actions=self._misunderstood(state, now, text, question=text))
        if kind == "clarify" and state.questions_asked >= self.rules.max_clarifying_questions:
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
                return _Outcome(actions=self._misunderstood(state, now, "Intrebare blocata de verificari."))
            return _fail(" ".join(problems))

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

    # ---------- oferta ----------

    def _finalize_offer(self, state: ConversationState, turn: _Turn, quote_id: str, summary: str,
                        now: datetime) -> list[OutboundAction]:
        quote = state.quotes[quote_id]
        threshold = self.rules.handoff_value_threshold_ron_ex_vat
        if summary:
            state.summary = summary[:500]
        if quote.total_ex_vat > threshold:
            return self._handoff(state, HandoffReason.VALUE_OVER_THRESHOLD, state.summary, now, quote=quote)

        today = now.date()
        state.offer_times = [t for t in state.offer_times if (today - to_local(t).date()).days <= 1]
        if sum(1 for t in state.offer_times if to_local(t).date() == today) >= self.rules.max_offers_per_contact_per_day:
            # Contractul nu are un motiv dedicat pentru limita de oferte.
            actions = self._handoff(state, HandoffReason.SPECIAL_TERMS,
                                    f"Limita zilnica de oferte automate atinsa. {state.summary}".strip(), now)
            actions[0].text = f"{offer_text.OFFER_LIMIT_TEXT} {actions[0].text}"
            return actions

        try:
            tiers = state.tiers.get(quote_id)
            if tiers is None:
                tiers = list(self.pricing.get_price_tiers(quote.choices, self.rules.upsell_tier_count))
                state.tiers[quote_id] = tiers
        except Exception:
            log.exception("treptele de cantitate nu au putut fi citite")
            tiers = []
        lines = offer_text.build_lines(quote, tiers, threshold)

        usable_file = state.design is not None and not (
            state.file_report is not None and state.file_report.verdict == FileVerdict.UNUSABLE)
        if usable_file and state.mockup_path is None:
            try:
                state.mockup_path = self.mockup.make_mockup(
                    state.design.path, state.summary[:80], self._out_dir(state)).image_path
            except Exception:
                log.exception("mockup esuat; oferta pleaca fara mockup")
        valid_until = now + timedelta(days=self.rules.offer_validity_days)
        term = self.rules.production_term(quote.choices.urgent)
        try:
            image_path = self.mockup.make_offer_image(
                state.mockup_path if usable_file else None, lines, term, valid_until, self._out_dir(state))
        except Exception:
            log.exception("imaginea de oferta nu a putut fi generata")
            image_path = None
        text = offer_text.build_offer_text(
            quote, lines, _product_title(turn.catalog, quote.choices.product_id), term, valid_until, state.file_report)
        artwork_url = state.design.public_url if state.design is not None else None

        if self.rules.shadow_mode:
            self._supersede_pending(state)
            approval = Approval(
                id=self._new_id(), channel=state.channel, key=state.key, created_at=now, quote=quote,
                lines=lines, offer_text=text, image_path=image_path, artwork_url=artwork_url,
                valid_until=valid_until, summary=state.summary)
            self.store.save_approval(approval)
            self._mark_offer(state, now)
            state.pending_approval_id = approval.id
            state.last_approval_id = approval.id
            state.status = "offer_pending_approval"
            self._crm(state, "offer_pending_approval", quote=quote)
            return [OutboundAction(kind="pending_approval", text=text, image_path=image_path, approval_id=approval.id)]

        try:
            checkout = self.checkout.create_checkout(quote, state.contact, artwork_url, valid_until)
        except Exception:
            log.exception("checkout-ul nu a putut fi creat")
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Eroare tehnica la crearea linkului de plata. {state.summary}".strip(), now, quote=quote)
        if checkout.total.quantize(Decimal("0.01")) != quote.total.quantize(Decimal("0.01")):
            log.error("checkout %s are totalul %s, calculatorul %s", checkout.draft_order_id, checkout.total, quote.total)
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Totalul din checkout difera de pretul calculatorului. {state.summary}".strip(),
                                 now, quote=quote)
        self._supersede_pending(state)
        self._mark_offer(state, now)
        state.status = "offer_sent"
        self._crm(state, "offer_sent", quote=quote, checkout=checkout)
        return self._offer_actions(text, quote, checkout.invoice_url, image_path)

    @staticmethod
    def _offer_actions(text: str, quote: PriceQuote, invoice_url: str, image_path: str | None) -> list[OutboundAction]:
        actions = []
        if image_path:
            actions.append(OutboundAction(kind="image", image_path=image_path))
        actions.append(OutboundAction(kind="text", text=offer_text.with_payment_link(text, quote, invoice_url)))
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
            raise ApprovalError(f"aprobare necunoscuta: {approval_id}")
        if approval.status != "pending":
            raise ApprovalError(f"aprobarea {approval_id} este deja {approval.status}")
        return approval

    # ---------- predare, neintelegeri ----------

    def _handoff(self, state: ConversationState, reason: HandoffReason, summary: str, now: datetime,
                 quote: PriceQuote | None = None) -> list[OutboundAction]:
        if summary:
            state.summary = summary[:500]
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

    def _misunderstood(self, state: ConversationState, now: datetime, summary: str,
                       question: str | None = None) -> list[OutboundAction]:
        state.misunderstandings += 1
        if state.misunderstandings >= self.rules.max_misunderstandings:
            return self._handoff(state, HandoffReason.NOT_UNDERSTOOD,
                                 f"Cerere neinteleasa dupa {state.misunderstandings} schimburi. {summary}"[:500], now)
        text = question or offer_text.NOT_UNDERSTOOD_TEXT
        if question and self._guard_plain(state, question):
            text = offer_text.NOT_UNDERSTOOD_TEXT
        return [OutboundAction(kind="text", text=text)]

    def _reset_for_new_request(self, state: ConversationState) -> None:
        state.status = "collecting"
        state.manual_since = None
        state.questions_asked = 0
        state.misunderstandings = 0
        state.file_failures = 0
        state.last_failed_file = None
        state.pending_buttons = {}

    # ---------- verificari pe textul modelului ----------

    def _guard(self, state: ConversationState, turn: _Turn, text: str) -> list[str]:
        amounts: list[Decimal] = []
        percents: list[Decimal] = [self.rules.vat_percent]
        for quote in state.quotes.values():
            amounts += [quote.total, quote.total_ex_vat, quote.unit_price]
            percents.append(quote.discount_percent)
        for tiers in state.tiers.values():
            for tier in tiers:
                amounts += [tier.total, tier.total_ex_vat, tier.unit_price]
        return check_text(
            text, allowed_amounts=amounts, allowed_percents=percents,
            approved_claims=self.rules.approved_material_claims, catalog_terms=turn.catalog_terms,
            allowed_terms=[t for t in (self.rules.production_term_standard, self.rules.production_term_urgent) if t])

    def _guard_plain(self, state: ConversationState, text: str) -> list[str]:
        return self._guard(state, _Turn(catalog={}), text)

    # ---------- context pentru model ----------

    def _render_turn(self, state: ConversationState, message: InboundMessage, now: datetime) -> str:
        left = max(self.rules.max_clarifying_questions - state.questions_asked, 0)
        rows = [
            f"Ora curenta: {now.strftime('%Y-%m-%d %H:%M')} (Europe/Bucharest), {_WEEKDAYS[now.weekday()]}.",
            f"Canal: {state.channel}. Starea conversatiei: {state.status}.",
            f"Intrebari de clarificare ramase: {left}.",
        ]
        if state.design is not None:
            name = state.design.filename or Path(state.design.path).name
            check = "neverificat"
            if state.file_report is not None:
                check = f"{state.file_report.verdict.value} {state.file_report.problems}"
            rows.append(f"Fisier de la client: {wrap_file(name)} ({state.design.mime}); verificare: {check}; "
                        f"mockup: {'facut' if state.mockup_path else 'nefacut'}.")
        else:
            rows.append("Fisier de la client: niciunul.")
        if state.quotes:
            rows.append("Oferte pretuite pana acum (din calculator):")
            for quote_id, quote in state.quotes.items():
                c = quote.choices
                rows.append(
                    f"- {quote_id}: produs {c.product_id}, {c.shape}, {c.width_cm} x {c.height_cm} cm, "
                    f"{c.material_name}, {c.quantity} buc; total cu TVA {quote.total}, fara TVA {quote.total_ex_vat}")

        history = self.store.recent_messages(state.channel, state.key, _TRANSCRIPT_LIMIT + 1)[:-1]
        if history:
            rows.append("")
            rows.append("Conversatia de pana acum:")
            for entry in history:
                stamp = to_local(entry.at).strftime("%d.%m %H:%M")
                if entry.direction == "in":
                    files = entry.meta.get("attachments") or []
                    extra = f" [fisiere: {wrap_file(', '.join(files))}]" if files else ""
                    rows.append(f"[client {stamp}] {wrap_customer(entry.text)}{extra}")
                elif entry.direction == "staff":
                    rows.append(f"[coleg {stamp}] {wrap_customer(entry.text)}")
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
        rows.append(wrap_customer(text))
        if message.attachments:
            names = ", ".join(a.filename or Path(a.path).name for a in message.attachments)
            rows.append(f"Fisiere atasate acum: {wrap_file(names)}")
        return "\n".join(rows)

    def _choices_summary(self, turn: _Turn, quote: PriceQuote) -> str:
        title = _product_title(turn.catalog, quote.choices.product_id)
        return f"{offer_text.describe_choices(quote, title)}, {quote.choices.quantity} buc"

    # ---------- utilitare ----------

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


# ---------- functii pure ----------

def _merge_contact(known: Contact, incoming: Contact) -> Contact:
    updates = {k: v for k, v in incoming.model_dump().items() if v is not None}
    return known.model_copy(update=updates)


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
    keep = ("id", "title", "shapes", "customSize", "sizesByShape", "addOnGroups", "quantity")
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
