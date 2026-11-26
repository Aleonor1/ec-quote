"""Compararea secretului si tokenuri semnate HMAC (sesiuni de chat, linkuri media)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json

MAX_TOKEN_LENGTH = 2048


class TokenError(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason  # "invalid" sau "expired"


def secrets_equal(given: str | None, expected: str) -> bool:
    """Comparare in timp constant; un secret asteptat gol nu se potriveste niciodata."""
    if not given or not expected:
        return False
    return hmac.compare_digest(given.encode("utf-8", "replace"), expected.encode())


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


class Signer:
    """Token = base64url(json) + "." + base64url(hmac-sha256). Payloadul are mereu "exp"."""

    def __init__(self, key: bytes):
        self._key = key

    def _mac(self, body: str) -> bytes:
        return hmac.new(self._key, body.encode(), hashlib.sha256).digest()

    def sign(self, payload: dict, expires_at: float) -> str:
        data = dict(payload, exp=int(expires_at))
        body = _b64(json.dumps(data, separators=(",", ":"), sort_keys=True).encode())
        return f"{body}.{_b64(self._mac(body))}"

    def verify(self, token: str, now: float) -> dict:
        if not token or len(token) > MAX_TOKEN_LENGTH or token.count(".") != 1:
            raise TokenError("invalid")
        body, sig = token.split(".")
        try:
            given = _unb64(sig)
        except (ValueError, TypeError):
            raise TokenError("invalid") from None
        # Semnatura se verifica inainte de a citi orice din payload.
        if not hmac.compare_digest(given, self._mac(body)):
            raise TokenError("invalid")
        try:
            payload = json.loads(_unb64(body))
            expires = int(payload["exp"])
        except (ValueError, TypeError, KeyError):
            raise TokenError("invalid") from None
        if now >= expires:
            raise TokenError("expired")
        return payload
