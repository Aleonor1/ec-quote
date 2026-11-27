"""Metrici pure de utilizare a sugestiilor (story-25).

Toate functiile primesc randuri si intervalul `(period_start, period_end)` in fusul
`Europe/Bucharest`, fara ceas global si fara efecte laterale.
"""
from __future__ import annotations

import difflib
import math
import statistics
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict

from ec_quote.agent.guard import money_mentions, normalize
from ec_quote.agent.store import ConversationStore, LoggedMessage, Suggestion
from ec_quote.contracts import FileVerdict, HandoffReason

TZ = ZoneInfo("Europe/Bucharest")
CENT = Decimal("0.01")
MILLION = Decimal("1000000")

# Pragul de similaritate este definit intr-un singur loc si poate fi suprascris din configuratie.
DEFAULT_SIMILARITY_THRESHOLD: float = 0.6

SuggestionKind = Literal["reply", "question", "offer", "needs_human", "none"]
Outcome = Literal["unchanged", "edited", "ignored", "pending"]

ALL_KINDS: tuple[SuggestionKind, ...] = ("reply", "question", "offer", "needs_human", "none")
TEXT_KINDS: tuple[SuggestionKind, ...] = ("reply", "question", "offer")
NON_IGNORED_KINDS: tuple[SuggestionKind, ...] = ("needs_human", "none")
ALL_OUTCOMES: tuple[Outcome, ...] = ("unchanged", "edited", "ignored", "pending")


def to_bucharest(moment: datetime) -> datetime:
    """Converteste un datetime la Europe/Bucharest (fara tzinfo = considerat deja local)."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=TZ)
    return moment.astimezone(TZ)


def _parse_config_decimal(raw: Any, key_name: str) -> Decimal:
    if isinstance(raw, bool) or isinstance(raw, float) or raw is None:
        raise ValueError(f"Cheia {key_name} trebuie sa fie numar Decimal sau text numeric, nu {type(raw).__name__}")
    text = str(raw).strip()
    if not text or any(tag in text.upper() for tag in ("TBD", "TODO", "PLACEHOLDER")):
        raise ValueError(f"Cheia {key_name} lipseste sau are valoare provizorie")
    try:
        val = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"Cheia {key_name} nu este un numar valid: {raw!r}") from exc
    if not val.is_finite() or val < 0:
        raise ValueError(f"Cheia {key_name} trebuie sa fie finita si nenegativa")
    return val


@dataclass(frozen=True)
class UsageMetricsConfig:
    """Preturile pe milion de tokeni, plafonul lunar si pragul de similaritate."""

    input_price_per_million: Decimal
    output_price_per_million: Decimal
    monthly_cost_ceiling: Decimal
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD

    def __post_init__(self) -> None:
        if not (0.0 < self.similarity_threshold <= 1.0):
            raise ValueError("similarity_threshold trebuie sa fie in intervalul (0, 1]")
        for name, val in (
            ("input_price_per_million", self.input_price_per_million),
            ("output_price_per_million", self.output_price_per_million),
            ("monthly_cost_ceiling", self.monthly_cost_ceiling),
        ):
            if isinstance(val, float) or not isinstance(val, Decimal) or not val.is_finite() or val < 0:
                raise ValueError(f"{name} trebuie sa fie Decimal finit si nenegativ")

    @classmethod
    def from_rules(cls, data: Mapping[str, Any]) -> UsageMetricsConfig:
        nested = data.get("model_cost") or data.get("model_pricing") or {}
        if not isinstance(nested, Mapping):
            nested = {}

        def pick(flat_key: str, nested_key: str) -> Any:
            return data[flat_key] if flat_key in data else nested.get(nested_key)

        in_price = _parse_config_decimal(
            pick("model_input_price_per_million", "input_price_per_million"),
            "model_input_price_per_million",
        )
        out_price = _parse_config_decimal(
            pick("model_output_price_per_million", "output_price_per_million"),
            "model_output_price_per_million",
        )
        ceiling = _parse_config_decimal(
            pick("model_monthly_cost_ceiling", "monthly_cost_ceiling"),
            "model_monthly_cost_ceiling",
        )
        raw_threshold = data.get(
            "suggestion_similarity_threshold",
            nested.get("similarity_threshold", DEFAULT_SIMILARITY_THRESHOLD),
        )
        try:
            threshold = float(raw_threshold)
        except (TypeError, ValueError) as exc:
            raise ValueError("suggestion_similarity_threshold invalid") from exc
        return cls(
            input_price_per_million=in_price,
            output_price_per_million=out_price,
            monthly_cost_ceiling=ceiling,
            similarity_threshold=threshold,
        )


class SuggestionMetricRow(BaseModel):
    """Un rand efemer de intrare pentru calculul pur al metricilor unei sugestii."""

    model_config = ConfigDict(frozen=True)

    suggestion_id: str
    conversation_key: str = ""
    kind: SuggestionKind
    created_at: datetime
    customer_sent_at: datetime | None = None
    first_seen_at: datetime | None = None
    backend_latency_s: float | None = None
    request_received_at: datetime | None = None
    response_sent_at: datetime | None = None
    suggestion_text: str = ""
    next_outgoing_text: str | None = None
    replaced_by_newer: bool = False
    handoff_reason: HandoffReason | None = None
    requested_by: str | None = None
    payment_link_created: bool = False
    payment_link_created_at: datetime | None = None
    guard_rejections: tuple[str, ...] = ()
    calculator_failures: int = 0
    file_verdict: FileVerdict | None = None
    input_tokens: int = 0
    output_tokens: int = 0


@dataclass(frozen=True)
class ClassifiedSuggestion:
    suggestion_id: str
    conversation_key: str
    kind: SuggestionKind
    outcome: Outcome | None
    similarity: float | None
    amounts_changed: bool | None
    time_to_suggestion_s: float | None
    missing_sent_at: bool
    backend_latency_s: float | None
    requested_by: str | None
    cost: Decimal


@dataclass(frozen=True)
class TimeToSuggestionStats:
    count: int
    missing_sent_at_count: int
    median_s: float | None
    p90_s: float | None
    share_under_60s: float | None
    share_under_300s: float | None


@dataclass(frozen=True)
class BackendLatencyStats:
    count: int
    median_s: float | None
    p90_s: float | None
    max_s: float | None


@dataclass(frozen=True)
class ModelCostSummary:
    total_input_tokens: int
    total_output_tokens: int
    total_cost: Decimal
    projected_month_end_cost: Decimal
    monthly_ceiling: Decimal
    over_ceiling: bool
    ceiling_share: Decimal | None


@dataclass(frozen=True)
class UsageMetricsReport:
    period_start: datetime
    period_end: datetime
    total_suggestions: int
    time_to_suggestion: TimeToSuggestionStats
    backend_latency: BackendLatencyStats
    suggestions_by_kind: dict[str, int]
    outcomes: dict[str, int]
    needs_human_by_reason: dict[str, int]
    offers_suggested: int
    edited_offers_amounts_changed: int
    payment_links_created: int
    guard_rejections_by_rule: dict[str, int]
    calculator_failures: int
    file_verdicts_by_level: dict[str, int]
    requests_by_staff: dict[str, int]
    model_cost: ModelCostSummary
    classified_rows: tuple[ClassifiedSuggestion, ...]


# ---------- similaritate, clasificarea rezultatului si verificarea sumelor ----------

def normalize_whitespace(text: str) -> str:
    """Compacteaza spatiile albe si liniile noi intr-un singur spatiu, pastrand literele si diacriticele."""
    return " ".join((text or "").split())


def text_similarity(suggested: str, sent: str) -> float:
    """Masura unica de similaritate (0..1) pe textele normalizate fara diacritice."""
    left = normalize(suggested or "")
    right = normalize(sent or "")
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def classify_text_outcome(
    suggested: str,
    sent: str | None,
    *,
    replaced_by_newer: bool = False,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Outcome:
    """Clasifica ce s-a intamplat cu o sugestie cu text."""
    if not (0.0 < similarity_threshold <= 1.0):
        raise ValueError("similarity_threshold trebuie sa fie in intervalul (0, 1]")
    if sent is not None:
        if normalize_whitespace(suggested) == normalize_whitespace(sent):
            return "unchanged"
        if text_similarity(suggested, sent) >= similarity_threshold:
            return "edited"
        return "ignored"
    if replaced_by_newer:
        return "ignored"
    return "pending"


def classify_row_outcome(
    row: SuggestionMetricRow,
    *,
    similarity_threshold: float = DEFAULT_SIMILARITY_THRESHOLD,
) -> Outcome | None:
    """Sugestiile `needs_human` si `none` nu sunt clasificate ca ignorate (AC6)."""
    if row.kind in NON_IGNORED_KINDS:
        return None
    if not normalize_whitespace(row.suggestion_text):
        return None
    return classify_text_outcome(
        row.suggestion_text,
        row.next_outgoing_text,
        replaced_by_newer=row.replaced_by_newer,
        similarity_threshold=similarity_threshold,
    )


def offer_amounts_changed(suggested_text: str, sent_text: str) -> bool:
    """True daca vreo suma din oferta propusa lipseste sau s-a schimbat in textul trimis (AC5)."""
    left = Counter(
        item.quantize(CENT, rounding=ROUND_HALF_UP) if item is not None else None
        for item in money_mentions(suggested_text)
    )
    right = Counter(
        item.quantize(CENT, rounding=ROUND_HALF_UP) if item is not None else None
        for item in money_mentions(sent_text)
    )
    return left != right


# ---------- calcule statistice si proiectia de cost ----------

def _percentile_90(sorted_values: list[float]) -> float:
    idx = max(0, math.ceil(0.90 * len(sorted_values)) - 1)
    return sorted_values[idx]


def _compute_time_stats(deltas: list[float], missing_count: int) -> TimeToSuggestionStats:
    if not deltas:
        return TimeToSuggestionStats(
            count=0,
            missing_sent_at_count=missing_count,
            median_s=None,
            p90_s=None,
            share_under_60s=None,
            share_under_300s=None,
        )
    ordered = sorted(deltas)
    n = len(ordered)
    return TimeToSuggestionStats(
        count=n,
        missing_sent_at_count=missing_count,
        median_s=float(statistics.median(ordered)),
        p90_s=_percentile_90(ordered),
        share_under_60s=sum(1 for v in ordered if v <= 60.0) / n,
        share_under_300s=sum(1 for v in ordered if v <= 300.0) / n,
    )


def _compute_backend_stats(latencies: list[float]) -> BackendLatencyStats:
    if not latencies:
        return BackendLatencyStats(count=0, median_s=None, p90_s=None, max_s=None)
    ordered = sorted(latencies)
    return BackendLatencyStats(
        count=len(ordered),
        median_s=float(statistics.median(ordered)),
        p90_s=_percentile_90(ordered),
        max_s=ordered[-1],
    )


def _row_backend_latency(row: SuggestionMetricRow) -> float | None:
    if row.backend_latency_s is not None:
        return max(float(row.backend_latency_s), 0.0)
    if row.request_received_at is not None and row.response_sent_at is not None:
        delta = (to_bucharest(row.response_sent_at) - to_bucharest(row.request_received_at)).total_seconds()
        return max(delta, 0.0)
    return None


def _month_bounds(period_end_local: datetime) -> tuple[datetime, datetime]:
    anchor = period_end_local - timedelta(microseconds=1)
    month_start = datetime(anchor.year, anchor.month, 1, 0, 0, tzinfo=TZ)
    if anchor.month == 12:
        next_month = datetime(anchor.year + 1, 1, 1, 0, 0, tzinfo=TZ)
    else:
        next_month = datetime(anchor.year, anchor.month + 1, 1, 0, 0, tzinfo=TZ)
    return month_start, next_month


def compute_usage_metrics(
    rows: Iterable[SuggestionMetricRow],
    period_start: datetime,
    period_end: datetime,
    config: UsageMetricsConfig,
) -> UsageMetricsReport:
    """Calculeaza pur toate metricile story-25 pe intervalul `[period_start, period_end)`."""
    start_local = to_bucharest(period_start)
    end_local = to_bucharest(period_end)
    if end_local <= start_local:
        raise ValueError("period_end trebuie sa fie strict dupa period_start")

    all_rows = list(rows)
    in_period: list[SuggestionMetricRow] = []
    payment_links_created = 0

    for row in all_rows:
        created_local = to_bucharest(row.created_at)
        if start_local <= created_local < end_local:
            in_period.append(row)
        if row.payment_link_created:
            link_moment = to_bucharest(row.payment_link_created_at or row.created_at)
            if start_local <= link_moment < end_local:
                payment_links_created += 1

    suggestions_by_kind: dict[str, int] = {k: 0 for k in ALL_KINDS}
    outcomes: dict[str, int] = {o: 0 for o in ALL_OUTCOMES}
    needs_human_by_reason: dict[str, int] = {}
    guard_rejections_by_rule: dict[str, int] = {}
    file_verdicts_by_level: dict[str, int] = {}
    requests_by_staff: dict[str, int] = {}

    offers_suggested = 0
    edited_offers_amounts_changed = 0
    calculator_failures = 0
    total_input_tokens = 0
    total_output_tokens = 0
    exact_total_cost = Decimal(0)

    time_deltas: list[float] = []
    missing_sent_at_count = 0
    backend_latencies: list[float] = []
    classified_rows: list[ClassifiedSuggestion] = []

    for row in in_period:
        suggestions_by_kind[row.kind] = suggestions_by_kind.get(row.kind, 0) + 1
        if row.kind == "offer":
            offers_suggested += 1
        if row.kind == "needs_human" and row.handoff_reason is not None:
            r_key = row.handoff_reason.value
            needs_human_by_reason[r_key] = needs_human_by_reason.get(r_key, 0) + 1

        # Numararea pe persoana exista doar ca numar de sugestii cerute, pentru auditul de tokeni (AC7).
        if row.requested_by:
            requests_by_staff[row.requested_by] = requests_by_staff.get(row.requested_by, 0) + 1

        for rule_name in (r for r in row.guard_rejections if r):
            guard_rejections_by_rule[rule_name] = guard_rejections_by_rule.get(rule_name, 0) + 1
        calculator_failures += max(int(row.calculator_failures), 0)
        if row.file_verdict is not None:
            v_key = row.file_verdict.value
            file_verdicts_by_level[v_key] = file_verdicts_by_level.get(v_key, 0) + 1

        created_local = to_bucharest(row.created_at)
        tts_s: float | None = None
        missing_flag = False
        if row.kind != "none":
            if row.customer_sent_at is not None:
                basis_local = to_bucharest(row.customer_sent_at)
            else:
                basis_local = to_bucharest(row.first_seen_at) if row.first_seen_at is not None else created_local
                missing_flag = True
                missing_sent_at_count += 1
            tts_s = max((created_local - basis_local).total_seconds(), 0.0)
            time_deltas.append(tts_s)

        b_lat = _row_backend_latency(row)
        if b_lat is not None:
            backend_latencies.append(b_lat)

        outcome = classify_row_outcome(row, similarity_threshold=config.similarity_threshold)
        sim: float | None = None
        amt_changed: bool | None = None
        if outcome is not None:
            outcomes[outcome] += 1
            if row.next_outgoing_text is not None:
                sim = text_similarity(row.suggestion_text, row.next_outgoing_text)
            if row.kind == "offer" and outcome == "edited" and row.next_outgoing_text is not None:
                amt_changed = offer_amounts_changed(row.suggestion_text, row.next_outgoing_text)
                if amt_changed:
                    edited_offers_amounts_changed += 1

        in_tok = max(int(row.input_tokens), 0)
        out_tok = max(int(row.output_tokens), 0)
        total_input_tokens += in_tok
        total_output_tokens += out_tok
        row_cost = (
            Decimal(in_tok) * config.input_price_per_million
            + Decimal(out_tok) * config.output_price_per_million
        ) / MILLION
        exact_total_cost += row_cost

        classified_rows.append(
            ClassifiedSuggestion(
                suggestion_id=row.suggestion_id,
                conversation_key=row.conversation_key,
                kind=row.kind,
                outcome=outcome,
                similarity=sim,
                amounts_changed=amt_changed,
                time_to_suggestion_s=tts_s,
                missing_sent_at=missing_flag,
                backend_latency_s=b_lat,
                requested_by=row.requested_by,
                cost=row_cost,
            )
        )

    month_start, next_month = _month_bounds(end_local)
    period_seconds = Decimal(str((end_local - start_local).total_seconds()))
    month_seconds = Decimal(str((next_month - month_start).total_seconds()))
    total_cost_q = exact_total_cost.quantize(CENT, rounding=ROUND_HALF_UP)
    projected_q = (exact_total_cost * month_seconds / period_seconds).quantize(CENT, rounding=ROUND_HALF_UP)
    ceiling_q = config.monthly_cost_ceiling.quantize(CENT, rounding=ROUND_HALF_UP)
    ceiling_share = (
        (projected_q / ceiling_q).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        if ceiling_q > 0
        else None
    )

    return UsageMetricsReport(
        period_start=start_local,
        period_end=end_local,
        total_suggestions=len(in_period),
        time_to_suggestion=_compute_time_stats(time_deltas, missing_sent_at_count),
        backend_latency=_compute_backend_stats(backend_latencies),
        suggestions_by_kind=suggestions_by_kind,
        outcomes=outcomes,
        needs_human_by_reason=dict(sorted(needs_human_by_reason.items())),
        offers_suggested=offers_suggested,
        edited_offers_amounts_changed=edited_offers_amounts_changed,
        payment_links_created=payment_links_created,
        guard_rejections_by_rule=dict(sorted(guard_rejections_by_rule.items())),
        calculator_failures=calculator_failures,
        file_verdicts_by_level=dict(sorted(file_verdicts_by_level.items())),
        requests_by_staff=dict(sorted(requests_by_staff.items())),
        model_cost=ModelCostSummary(
            total_input_tokens=total_input_tokens,
            total_output_tokens=total_output_tokens,
            total_cost=total_cost_q,
            projected_month_end_cost=projected_q,
            monthly_ceiling=ceiling_q,
            over_ceiling=projected_q > ceiling_q,
            ceiling_share=ceiling_share,
        ),
        classified_rows=tuple(classified_rows),
    )


# ---------- adaptor pur peste inregistrarile Suggestion si LoggedMessage din store ----------

def link_conversation_rows(
    suggestions: Sequence[Suggestion],
    messages: Sequence[LoggedMessage],
) -> list[SuggestionMetricRow]:
    """Leaga fiecare sugestie de mesajul clientului si de primul mesaj trimis ulterior in chat.

    Nu salveaza nicio copie suplimentara a mesajelor trimise (AC11): foloseste doar jurnalul existent.
    """
    msg_index_by_id: dict[str, int] = {}
    for idx, msg in enumerate(messages):
        mid = msg.meta.get("id") if isinstance(msg.meta, dict) else None
        if isinstance(mid, str) and mid and mid not in msg_index_by_id:
            msg_index_by_id[mid] = idx

    basis_indices: list[int | None] = [
        msg_index_by_id.get(s.basis_message_id) if s.basis_message_id else None
        for s in suggestions
    ]

    built: list[SuggestionMetricRow] = []
    for pos, item in enumerate(suggestions):
        b_idx = basis_indices[pos]
        next_b_idx: int | None = None
        for later_idx in basis_indices[pos + 1 :]:
            if later_idx is not None and (b_idx is None or later_idx > b_idx):
                next_b_idx = later_idx
                break

        customer_sent_at: datetime | None = getattr(item, "customer_sent_at", None)
        first_seen_at: datetime | None = getattr(item, "first_seen_at", None)
        if b_idx is not None:
            basis_msg = messages[b_idx]
            meta = basis_msg.meta if isinstance(basis_msg.meta, dict) else {}
            if customer_sent_at is None:
                if "sent_at" in meta:
                    raw_sent = meta["sent_at"]
                    customer_sent_at = datetime.fromisoformat(str(raw_sent)) if raw_sent is not None else None
                elif not meta.get("missing_sent_at"):
                    customer_sent_at = basis_msg.at
            if first_seen_at is None:
                raw_seen = meta.get("first_seen_at")
                first_seen_at = datetime.fromisoformat(str(raw_seen)) if raw_seen else basis_msg.at
        elif first_seen_at is None:
            first_seen_at = item.created_at

        next_outgoing_text: str | None = None
        if b_idx is not None:
            end_slice = next_b_idx if next_b_idx is not None else len(messages)
            for candidate in messages[b_idx + 1 : end_slice]:
                if candidate.direction in ("staff", "out"):
                    next_outgoing_text = candidate.text
                    break

        replaced = next_outgoing_text is None and (item.status == "superseded" or pos + 1 < len(suggestions))

        raw_verdict = getattr(item, "file_verdict", None)
        verdict = FileVerdict(raw_verdict) if raw_verdict is not None and not isinstance(raw_verdict, FileVerdict) else raw_verdict

        built.append(
            SuggestionMetricRow(
                suggestion_id=item.id,
                conversation_key=f"{item.channel}:{item.key}",
                kind=item.suggestion.kind,
                created_at=item.created_at,
                customer_sent_at=customer_sent_at,
                first_seen_at=first_seen_at,
                backend_latency_s=getattr(item, "backend_latency_s", None),
                suggestion_text=item.suggestion.text,
                next_outgoing_text=next_outgoing_text,
                replaced_by_newer=replaced,
                handoff_reason=item.suggestion.handoff_reason,
                requested_by=getattr(item, "requested_by", None) or item.linked_by,
                payment_link_created=item.status == "linked" or bool(item.suggestion.payment_url),
                payment_link_created_at=item.linked_at,
                guard_rejections=tuple(getattr(item, "guard_rejections", ()) or ()),
                calculator_failures=int(getattr(item, "calculator_failures", 0) or 0),
                file_verdict=verdict,
                input_tokens=int(getattr(item, "input_tokens", 0) or 0),
                output_tokens=int(getattr(item, "output_tokens", 0) or 0),
            )
        )
    return built


def rows_from_store(
    store: ConversationStore,
    channel: str,
    key: str,
    *,
    message_limit: int = 10_000,
) -> list[SuggestionMetricRow]:
    """Citeste sugestiile si mesajele unei conversatii din store si construieste randurile pure."""
    suggestions = store.list_suggestions(channel, key)
    messages = store.recent_messages(channel, key, message_limit)
    return link_conversation_rows(suggestions, messages)
