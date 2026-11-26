"""Regulile de politica din config/rules.json si calculul programului de lucru."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Bucharest")
DEFAULT_RULES_PATH = Path(__file__).resolve().parents[2] / "config" / "rules.json"

# Folosit doar daca rules.json nu are cheia production_term_standard.
_FALLBACK_PRODUCTION_TERM = "termen standard de producție, confirmat la plasarea comenzii"


def to_local(moment: datetime) -> datetime:
    """Ora in Europe/Bucharest; un datetime fara fus este considerat deja local."""
    if moment.tzinfo is None:
        return moment.replace(tzinfo=TZ)
    return moment.astimezone(TZ)


def _parse_time(value: str) -> time:
    hours, minutes = value.split(":")
    return time(int(hours), int(minutes))


@dataclass(frozen=True)
class Rules:
    handoff_value_threshold_ron_ex_vat: Decimal
    offer_validity_days: int
    max_clarifying_questions: int
    max_misunderstandings: int
    max_file_attempts: int
    upsell_tier_count: int
    vat_percent: Decimal
    shadow_mode: bool
    manual_mode_quiet_hours: int
    max_offers_per_contact_per_day: int
    business_start: time
    business_end: time
    business_days: tuple[int, ...]  # isoweekday, 1 = luni
    approved_material_claims: tuple[str, ...]
    production_term_standard: str = _FALLBACK_PRODUCTION_TERM
    production_term_urgent: str = ""
    raw: dict = field(default_factory=dict, compare=False, repr=False)

    @classmethod
    def from_dict(cls, data: dict) -> "Rules":
        hours = data["business_hours"]
        return cls(
            handoff_value_threshold_ron_ex_vat=Decimal(str(data["handoff_value_threshold_ron_ex_vat"])),
            offer_validity_days=int(data["offer_validity_days"]),
            max_clarifying_questions=int(data["max_clarifying_questions"]),
            max_misunderstandings=int(data["max_misunderstandings"]),
            max_file_attempts=int(data["max_file_attempts"]),
            upsell_tier_count=int(data["upsell_tier_count"]),
            vat_percent=Decimal(str(data["vat_percent"])),
            shadow_mode=bool(data["shadow_mode"]),
            manual_mode_quiet_hours=int(data["manual_mode_quiet_hours"]),
            max_offers_per_contact_per_day=int(data["max_offers_per_contact_per_day"]),
            business_start=_parse_time(hours["start"]),
            business_end=_parse_time(hours["end"]),
            business_days=tuple(int(d) for d in hours["days"]),
            approved_material_claims=tuple(data.get("approved_material_claims", [])),
            production_term_standard=data.get("production_term_standard") or _FALLBACK_PRODUCTION_TERM,
            production_term_urgent=data.get("production_term_urgent") or "",
            raw=dict(data),
        )

    @classmethod
    def load(cls, path: str | os.PathLike | None = None) -> "Rules":
        target = Path(path or os.environ.get("EC_QUOTE_RULES_PATH") or DEFAULT_RULES_PATH)
        return cls.from_dict(json.loads(target.read_text(encoding="utf-8")))

    def is_business_hours(self, now: datetime) -> bool:
        local = to_local(now)
        if local.isoweekday() not in self.business_days:
            return False
        return self.business_start <= local.time() < self.business_end

    def next_business_open(self, now: datetime) -> datetime:
        """Urmatoarea deschidere a programului, strict dupa `now`."""
        local = to_local(now)
        for offset in range(0, 15):
            day = local.date() + timedelta(days=offset)
            opening = datetime.combine(day, self.business_start, tzinfo=TZ)
            if day.isoweekday() in self.business_days and opening > local:
                return opening
        raise ValueError("business_hours.days este gol")

    def production_term(self, urgent: bool) -> str:
        if urgent and self.production_term_urgent:
            return self.production_term_urgent
        return self.production_term_standard
