"""Fabricile adaptoarelor reale, chemate numai din main.py.

Modulele surori se importa abia aici, in functii, ca importul aplicatiei sa nu ceara
nici retea, nici SDK-uri. Fiecare fabrica primeste Settings si intoarce un port.
"""
from __future__ import annotations

import importlib
from collections.abc import Callable
from datetime import datetime

import httpx

from ec_quote.api.logutil import logger
from ec_quote.config import Settings
from ec_quote.contracts import (
    Checkout,
    CheckoutPort,
    Contact,
    CrmPort,
    Engine,
    FilePort,
    HandoffPort,
    HandoffReason,
    MockupPort,
    PriceQuote,
    PricingPort,
)

HTTP_TIMEOUT_SECONDS = 30.0


class NoCrm:
    """CrmPort si HandoffPort care nu fac nimic: fara CRM, lead-ul si predarea raman la omul din WhatsApp."""

    def upsert_lead(self, contact: Contact, summary: str, quote: PriceQuote | None,
                    checkout: Checkout | None, status: str) -> str:
        return ""

    def handoff(self, contact: Contact, reason: HandoffReason, summary: str, now: datetime) -> None:
        logger.info("handoff without crm reason=%s", reason.value)


def _http() -> httpx.Client:
    return httpx.Client(timeout=HTTP_TIMEOUT_SECONDS)


def build_pricing(settings: Settings) -> PricingPort:
    module = importlib.import_module("ec_quote.pricing")
    return module.CalculatorClient(settings.calculator_base_url,
                                   settings.calculator_sync_secret.get_secret_value(), http=_http())


def build_files(settings: Settings) -> FilePort:
    return importlib.import_module("ec_quote.files").FileChecker(rules_path=settings.rules_path)


def build_mockup(settings: Settings) -> MockupPort:
    module = importlib.import_module("ec_quote.mockup")
    factory = getattr(module, "build_mockup", None)
    return factory(settings) if factory else module.MockupService()


def build_checkout(settings: Settings) -> CheckoutPort:
    module = importlib.import_module("ec_quote.integrations")
    return module.ShopifyCheckout(settings.shopify_shop_domain,
                                  settings.shopify_admin_token.get_secret_value(), _http(),
                                  module.DEFAULT_API_VERSION)


def build_crm(settings: Settings) -> CrmPort | HandoffPort:
    """Un singur obiect pentru CrmPort si HandoffPort; NoCrm cand CRM_BASE_URL este gol."""
    if not settings.crm_base_url:
        return NoCrm()
    module = importlib.import_module("ec_quote.integrations")
    return module.CrmClient(settings.crm_base_url, settings.crm_api_secret.get_secret_value(), _http())


def build_engine(settings: Settings, clock: Callable[[], datetime] | None = None) -> Engine:
    """Motorul de productie. Obiectul intors implementeaza si AssistEngine cand modulul agent il are."""
    agent = importlib.import_module("ec_quote.agent")
    import anthropic  # import tarziu: doar productia are nevoie de SDK

    crm = build_crm(settings)
    model = agent.AnthropicModel(
        client=anthropic.Anthropic(api_key=settings.anthropic_api_key.get_secret_value()),
        model=settings.model or None)
    return agent.build_engine(
        pricing=build_pricing(settings), files=build_files(settings), mockup=build_mockup(settings),
        checkout=build_checkout(settings), crm=crm, handoff=crm, model=model,
        rules=agent.Rules.load(settings.rules_path), data_dir=settings.data_dir)
