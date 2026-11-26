"""Erorile tipizate ale integrarilor (Shopify, CRM). Niciuna nu se arata clientului ca atare."""
from __future__ import annotations

from decimal import Decimal


class IntegrationError(Exception):
    """Baza erorilor de integrare."""


# ---------- Shopify ----------

class ShopifyError(IntegrationError):
    """Baza erorilor Shopify."""


class ShopifyUnavailable(ShopifyError):
    """Retea, timeout sau 5xx. Mutatia de creare NU se reincearca orbeste (ar dubla draftul)."""


class ShopifyThrottled(ShopifyUnavailable):
    """Limita de cost depasita si dupa singura reincercare."""


class ShopifyUnauthorized(ShopifyError):
    """401/403: token lipsa, gresit sau fara scope (write_draft_orders). Problema de configurare."""


class ShopifyProtocolError(ShopifyError):
    """Raspuns neasteptat (status, forma sau erori GraphQL de nivel superior)."""


class ShopifyUserError(ShopifyError):
    """userErrors intoarse de o mutatie: datele trimise nu au fost acceptate."""

    def __init__(self, operation: str, errors: list[dict]):
        self.operation = operation
        self.errors = [
            {"field": e.get("field"), "message": str(e.get("message", ""))} for e in errors
        ]
        text = "; ".join(e["message"] for e in self.errors) or "?"
        super().__init__(f"{operation}: {text}")


class ShopifyProductNotFound(ShopifyError):
    """Produsul liniei nu exista in magazin."""


class ShopifyInvalidQuote(ShopifyError):
    """Oferta nu poate deveni draft (total zero sau negativ, produs lipsa)."""


class ShopifyPriceMismatch(ShopifyError):
    """Totalul draftului difera de pretul de pe site (de ex. TVA adaugat peste). Draftul a fost sters."""

    def __init__(self, expected: Decimal, actual: Decimal, draft_order_id: str, deleted: bool):
        self.expected = expected
        self.actual = actual
        self.draft_order_id = draft_order_id
        self.deleted = deleted
        super().__init__(
            f"draft {draft_order_id}: total {actual} in loc de {expected}"
            f" ({'sters' if deleted else 'NU a putut fi sters'})"
        )


class DraftOrderNotFound(ShopifyError):
    """Draftul nu (mai) exista."""


# ---------- CRM ----------

class CrmError(IntegrationError):
    """Baza erorilor CRM."""


class CrmUnavailable(CrmError):
    """Retea, timeout sau 5xx, si dupa reincercare. Scrierile au cheie de idempotenta, deci se pot relua."""


class CrmNotConfigured(CrmUnavailable):
    """503 din partea CRM-ului: tokenul puntii nu e configurat acolo."""


class CrmUnauthorized(CrmError):
    """401/403: secretul comun lipseste sau e gresit."""


class CrmRejected(CrmError):
    """4xx cu un cod de business (de ex. outreach_disabled, service_cap_reached, window_closed)."""

    def __init__(self, status_code: int, code: str, details: dict | None = None):
        self.status_code = status_code
        self.code = code
        self.details = details or {}
        super().__init__(f"{status_code} {code}")


class CrmProtocolError(CrmError):
    """Raspuns neasteptat (status sau forma necunoscuta)."""
