"""Erorile tipizate ale modulului de mockup."""
from __future__ import annotations


class MockupError(Exception):
    """Baza tuturor erorilor din ec_quote.mockup."""


class UnsupportedDesignError(MockupError):
    """Designul nu este un raster PNG/JPEG/WEBP lizibil."""


class TemplateError(MockupError):
    """Sablon invalid: manifest gresit, fisier lipsa sau dimensiuni nepotrivite."""


class NoTemplatesError(TemplateError):
    """Directorul de sabloane nu contine niciun sablon valid."""


class OfferImageError(MockupError):
    """Imaginea de oferta nu poate fi construita din datele primite."""
