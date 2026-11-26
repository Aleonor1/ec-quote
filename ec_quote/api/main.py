"""Radacina de compozitie: singurul loc unde se construiesc adaptoarele reale si se citeste ceasul.

Pornire: python3 -m uvicorn ec_quote.api.main:app --port 8080

Modulele surori se incarca dupa calea de import abia la construirea aplicatiei, asa ca
importul acestui fisier nu cere nici setari, nici module surori (testele raman fara retea).

Conventia asteptata de la fiecare modul:
- porturile: o functie `fabrica(settings)` care intoarce implementarea portului;
- motorul: `build_engine(settings=..., clock=..., pricing=..., files=..., mockup=...,
  checkout=..., crm=..., handoff=...)`.

EC_QUOTE_ENGINE_FACTORY="modul:functie" inlocuieste tot lantul cu `functie(settings=..., clock=...)`;
asa porneste pagina de proba cu motorul demonstrativ (ec_quote.api.demo_engine:build_engine).
"""
from __future__ import annotations

import importlib
import os
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from fastapi import FastAPI

from ec_quote.api.app import create_app
from ec_quote.api.logutil import configure_logging, logger
from ec_quote.config import Settings, load_settings
from ec_quote.contracts import Engine

BUCHAREST = ZoneInfo("Europe/Bucharest")

PORT_FACTORIES = {
    "pricing": "ec_quote.pricing:build_pricing",
    "files": "ec_quote.files:build_files",
    "mockup": "ec_quote.mockup:build_mockup",
    "checkout": "ec_quote.integrations:build_checkout",
    "crm": "ec_quote.integrations:build_crm",
    "handoff": "ec_quote.integrations:build_handoff",
}
ENGINE_FACTORY = "ec_quote.agent:build_engine"


class WiringError(RuntimeError):
    """Un modul sau o fabrica lipseste. Procesul nu porneste."""


def bucharest_now() -> datetime:
    return datetime.now(BUCHAREST)


def load_object(path: str) -> Any:
    module_name, _, attr = path.partition(":")
    try:
        return getattr(importlib.import_module(module_name), attr)
    except (ImportError, AttributeError, ValueError) as exc:
        raise WiringError(f"Nu pot incarca {path!r} ({type(exc).__name__})") from exc


def build_engine(settings: Settings, clock: Callable[[], datetime],
                 override: str | None = None) -> Engine:
    if override:
        return load_object(override)(settings=settings, clock=clock)
    ports = {name: load_object(path)(settings) for name, path in PORT_FACTORIES.items()}
    return load_object(ENGINE_FACTORY)(settings=settings, clock=clock, **ports)


def build(env: Mapping[str, str] | None = None) -> FastAPI:
    src = os.environ if env is None else env
    override = (src.get("EC_QUOTE_ENGINE_FACTORY") or "").strip() or None
    configure_logging()
    settings = load_settings(src, require_integrations=override is None)
    engine = build_engine(settings, bucharest_now, override)
    logger.info("ec-quote starting commit=%s demo=%s cors_origins=%d attachment_hosts=%d",
                settings.git_commit or "-", settings.demo, len(settings.cors_origins),
                len(settings.attachment_hosts))
    return create_app(engine, settings, clock=bucharest_now)


_cache: dict[str, FastAPI] = {}


def __getattr__(name: str):
    # `main:app` se construieste la prima citire (uvicorn), nu la import.
    if name == "app":
        if "app" not in _cache:
            _cache["app"] = build()
        return _cache["app"]
    raise AttributeError(name)
