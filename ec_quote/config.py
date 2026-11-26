"""Setarile ec-quote, citite din variabile de mediu.

Incarcarea esueaza inchis: daca lipseste ceva obligatoriu, SettingsError enumera
numele variabilelor. Valorile secrete sunt SecretStr si nu apar in repr sau in erori.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from collections.abc import Mapping
from pathlib import Path

from pydantic import BaseModel, ConfigDict, SecretStr

MIN_SECRET_LENGTH = 24

DEFAULT_ALLOWED_MIMES = (
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/pdf",
    "image/svg+xml",
)

# Obligatorii doar cand se construiesc porturile reale (main.py).
INTEGRATION_VARS = (
    "CALCULATOR_BASE_URL",
    "CALCULATOR_SYNC_SECRET",
    "ANTHROPIC_API_KEY",
    "EC_QUOTE_MODEL",
    "SHOPIFY_SHOP_DOMAIN",
    "SHOPIFY_ADMIN_TOKEN",
    "CRM_BASE_URL",
    "CRM_API_SECRET",
)


class SettingsError(RuntimeError):
    """Configuratie lipsa sau invalida. Mesajul contine doar nume de variabile."""


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    # API
    inbound_secret: SecretStr
    signing_secret: SecretStr
    data_dir: Path
    rules_path: Path = Path("config/rules.json")
    public_base_url: str = ""
    cors_origins: tuple[str, ...] = ()
    trusted_proxy_hops: int = 0
    # True: /v1/chat/* accepta doar cereri venite prin App Proxy-ul calculatorului (cu secretul).
    chat_require_secret: bool = False
    demo: bool = False
    git_commit: str | None = None

    # Atasamente si incarcari
    attachment_hosts: tuple[str, ...] = ()
    allowed_mimes: tuple[str, ...] = DEFAULT_ALLOWED_MIMES
    max_attachment_bytes: int = 20 * 1024 * 1024
    max_upload_bytes: int = 20 * 1024 * 1024
    max_attachments_per_message: int = 5
    fetch_timeout_seconds: float = 15.0

    # Linkuri semnate si sesiuni
    media_url_ttl_seconds: int = 3600
    session_ttl_seconds: int = 24 * 3600

    # Limite de ritm (in memorie)
    rate_sessions_per_ip_per_hour: int = 20
    rate_messages_per_session_per_minute: int = 20
    rate_messages_per_ip_per_minute: int = 60
    rate_uploads_per_session_per_hour: int = 10
    rate_polls_per_session_per_minute: int = 30

    # Integrari (folosite de modulele surori)
    calculator_base_url: str = ""
    calculator_sync_secret: SecretStr = SecretStr("")
    anthropic_api_key: SecretStr = SecretStr("")
    model: str = ""
    shopify_shop_domain: str = ""
    shopify_admin_token: SecretStr = SecretStr("")
    crm_base_url: str = ""
    crm_api_secret: SecretStr = SecretStr("")

    def signing_key(self, purpose: str) -> bytes:
        """Cheie derivata pe scop, ca un token de sesiune sa nu fie valid ca link media."""
        root = self.signing_secret.get_secret_value().encode()
        return hmac.new(root, purpose.encode(), hashlib.sha256).digest()


def _csv(value: str) -> tuple[str, ...]:
    return tuple(part.strip() for part in value.split(",") if part.strip())


def _flag(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings(env: Mapping[str, str] | None = None, *,
                  require_integrations: bool = True) -> Settings:
    src = os.environ if env is None else env

    def get(name: str) -> str:
        return (src.get(name) or "").strip()

    missing: list[str] = []
    invalid: list[str] = []

    required = ["EC_QUOTE_INBOUND_SECRET"]
    if require_integrations:
        required += list(INTEGRATION_VARS)
    for name in required:
        if not get(name):
            missing.append(name)

    inbound = get("EC_QUOTE_INBOUND_SECRET")
    if inbound and len(inbound) < MIN_SECRET_LENGTH:
        invalid.append(f"EC_QUOTE_INBOUND_SECRET (minim {MIN_SECRET_LENGTH} caractere)")
    signing = get("EC_QUOTE_SIGNING_SECRET")
    if signing and len(signing) < MIN_SECRET_LENGTH:
        invalid.append(f"EC_QUOTE_SIGNING_SECRET (minim {MIN_SECRET_LENGTH} caractere)")

    def number(name: str, default: float, cast=int, minimum: float = 0):
        raw = get(name)
        if not raw:
            return cast(default)
        try:
            value = cast(raw)
        except ValueError:
            invalid.append(f"{name} (numar asteptat)")
            return cast(default)
        if value < minimum:
            invalid.append(f"{name} (minim {minimum})")
        return value

    mb = 1024 * 1024
    numbers = {
        "trusted_proxy_hops": number("EC_QUOTE_TRUSTED_PROXY_HOPS", 0),
        "max_attachment_bytes": number("EC_QUOTE_MAX_ATTACHMENT_MB", 20, minimum=1) * mb,
        "max_upload_bytes": number("EC_QUOTE_MAX_UPLOAD_MB", 20, minimum=1) * mb,
        "max_attachments_per_message": number("EC_QUOTE_MAX_ATTACHMENTS", 5, minimum=1),
        "fetch_timeout_seconds": number("EC_QUOTE_FETCH_TIMEOUT_SECONDS", 15, float, 1),
        "media_url_ttl_seconds": number("EC_QUOTE_MEDIA_URL_TTL_SECONDS", 3600, minimum=60),
        "session_ttl_seconds": number("EC_QUOTE_SESSION_TTL_SECONDS", 24 * 3600, minimum=60),
        "rate_sessions_per_ip_per_hour": number("EC_QUOTE_RATE_SESSIONS_PER_IP_HOUR", 20, minimum=1),
        "rate_messages_per_session_per_minute":
            number("EC_QUOTE_RATE_MESSAGES_PER_SESSION_MINUTE", 20, minimum=1),
        "rate_messages_per_ip_per_minute": number("EC_QUOTE_RATE_MESSAGES_PER_IP_MINUTE", 60, minimum=1),
        "rate_uploads_per_session_per_hour":
            number("EC_QUOTE_RATE_UPLOADS_PER_SESSION_HOUR", 10, minimum=1),
        "rate_polls_per_session_per_minute":
            number("EC_QUOTE_RATE_POLLS_PER_SESSION_MINUTE", 30, minimum=1),
    }

    origins = _csv(get("EC_QUOTE_CORS_ORIGINS"))
    if any(o == "*" or not o.startswith(("https://", "http://")) or o.endswith("/") for o in origins):
        invalid.append("EC_QUOTE_CORS_ORIGINS (origini exacte, de forma https://domeniu, fara / la final)")
    public_base_url = get("EC_QUOTE_PUBLIC_BASE_URL").rstrip("/")
    if public_base_url and not public_base_url.startswith(("https://", "http://")):
        invalid.append("EC_QUOTE_PUBLIC_BASE_URL (URL complet)")

    problems = []
    if missing:
        problems.append("lipsesc: " + ", ".join(missing))
    if invalid:
        problems.append("invalide: " + ", ".join(invalid))
    if problems:
        raise SettingsError("Configuratie ec-quote incompleta; " + "; ".join(problems))

    return Settings(
        inbound_secret=SecretStr(inbound),
        # Fara secret separat, cheia de semnare se deriva din secretul de intrare.
        signing_secret=SecretStr(signing or hmac.new(
            inbound.encode(), b"ec-quote-signing-v1", hashlib.sha256).hexdigest()),
        data_dir=Path(get("EC_QUOTE_DATA_DIR") or "./data"),
        rules_path=Path(get("EC_QUOTE_RULES_PATH") or "config/rules.json"),
        public_base_url=public_base_url,
        cors_origins=origins,
        demo=_flag(get("EC_QUOTE_DEMO")),
        chat_require_secret=_flag(get("EC_QUOTE_CHAT_REQUIRE_SECRET")),
        git_commit=get("GIT_COMMIT") or None,
        attachment_hosts=tuple(h.lower() for h in _csv(get("EC_QUOTE_ATTACHMENT_HOSTS"))),
        allowed_mimes=tuple(m.lower() for m in _csv(get("EC_QUOTE_ALLOWED_MIMES")))
        or DEFAULT_ALLOWED_MIMES,
        calculator_base_url=get("CALCULATOR_BASE_URL").rstrip("/"),
        calculator_sync_secret=SecretStr(get("CALCULATOR_SYNC_SECRET")),
        anthropic_api_key=SecretStr(get("ANTHROPIC_API_KEY")),
        model=get("EC_QUOTE_MODEL"),
        shopify_shop_domain=get("SHOPIFY_SHOP_DOMAIN"),
        shopify_admin_token=SecretStr(get("SHOPIFY_ADMIN_TOKEN")),
        crm_base_url=get("CRM_BASE_URL").rstrip("/"),
        crm_api_secret=SecretStr(get("CRM_API_SECRET")),
        **numbers,
    )
