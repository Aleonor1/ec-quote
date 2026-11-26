"""Erorile tipizate ale clientului de pret."""
from __future__ import annotations


class PricingError(Exception):
    """Baza erorilor de pret. Niciuna nu se arata clientului ca atare."""


class PricingUnavailable(PricingError):
    """Calculatorul nu raspunde (503, timeout, retea), si dupa reincercare. Se poate reincerca mai tarziu."""


class PricingUnauthorized(PricingError):
    """401: secretul X-Sync-Secret lipseste sau e gresit. Problema de configurare."""


class PricingBadRequest(PricingError):
    """400 invalid_body: am trimis un corp gresit. E bug-ul nostru, nu al clientului."""

    def __init__(self, fields: list[str]):
        self.fields = list(fields)
        super().__init__(f"invalid_body: {', '.join(self.fields) or '?'}")


class PricingProtocolError(PricingError):
    """Raspuns neasteptat (status sau forma necunoscuta)."""
