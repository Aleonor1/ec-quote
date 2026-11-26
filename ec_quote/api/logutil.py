"""Loguri: id de cerere pe fiecare linie si numere de telefon mascate."""
from __future__ import annotations

import contextvars
import hashlib
import hmac
import logging
import re

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("ec_quote_request_id", default="-")

logger = logging.getLogger("ec_quote.api")

_DIGIT_RUN = re.compile(r"(?<![\w.-])\+?\d{9,15}(?![\w-])")


def mask_phone(value: str | None) -> str:
    """40712345678 -> 407******78. Sirurile scurte se mascheaza complet."""
    if not value:
        return "-"
    digits = re.sub(r"\D", "", value)
    if len(digits) < 7:
        return "*" * len(digits)
    return digits[:3] + "*" * (len(digits) - 5) + digits[-2:]


def contact_ref(key: str, salt: bytes) -> str:
    """Referinta stabila a contactului pentru loguri: HMAC scurt, nu numarul si nu id-ul sesiunii."""
    return hmac.new(salt, key.encode(), hashlib.sha256).hexdigest()[:12]


def scrub(text: str) -> str:
    return _DIGIT_RUN.sub(lambda m: mask_phone(m.group()), text)


class ContextFilter(logging.Filter):
    """Adauga request_id si mascheaza orice sir care arata a numar de telefon (plasa de siguranta)."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        try:
            message = record.getMessage()
        except Exception:  # argumente de formatare gresite: lasam linia cum este
            return True
        record.msg = scrub(message)
        record.args = None
        return True


logger.addFilter(ContextFilter())


def configure_logging(level: int = logging.INFO) -> None:
    """Idempotent. Apelat din main.py; in teste se foloseste caplog."""
    if logger.handlers:
        return
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(request_id)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
