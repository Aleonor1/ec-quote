"""Contractele comune ale ec-quote. Fiecare modul implementeaza un port de aici.

Reguli (aceleasi ca in ec-agency):
- banii sunt Decimal, niciodata float; preturile vin numai din calculator;
- ora (Europe/Bucharest) se primeste ca parametru, nu se citeste in functii pure;
- orice acces la retea trece printr-un client injectabil (teste fara retea);
- numerele de politica vin din config/rules.json, nu din cod.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Literal, Protocol

from pydantic import BaseModel, Field

Channel = Literal["whatsapp", "site"]  # "whatsapp" = conversatie din WhatsApp Web, asistata de extensie


# ---------- pret ----------

class LineChoices(BaseModel):
    """Alegerile unei linii, 1:1 cu CalculatorChoices din calculator-app (POST /api/sync/line)."""

    product_id: str
    material_name: str
    shape: str
    width_cm: Decimal
    height_cm: Decimal
    quantity: int
    add_ons: dict[str, str] = Field(default_factory=dict)
    adhesive: Literal["standard", "strong"] = "standard"
    white_print: bool = False
    cut: Literal["none", "double", "back"] = "none"
    urgent: bool = False
    file_editing: Literal["none", "upscale", "vectorize"] = "none"
    instructions: str = ""


class LineProperty(BaseModel):
    name: str
    value: str


class PriceQuote(BaseModel):
    """Pretul exact de pe site pentru o linie. total este cu TVA, ca pe site."""

    choices: LineChoices
    total: Decimal
    total_ex_vat: Decimal
    unit_price: Decimal
    discount_percent: Decimal
    cap_quantity: int | None = None
    breakdown: dict
    properties: list[LineProperty]


class Unpriced(BaseModel):
    """Calculatorul nu poate pretui linia. reason este codul 422 al calculatorului."""

    reason: str
    details: dict = Field(default_factory=dict)


class TierOffer(BaseModel):
    quantity: int
    total: Decimal
    total_ex_vat: Decimal
    unit_price: Decimal


class PricingPort(Protocol):
    def catalog(self) -> dict:
        """Configuratia calculatorului (GET /api/sync/calculator-config), cu cache."""

    def get_price(self, choices: LineChoices) -> PriceQuote | Unpriced: ...

    def get_price_tiers(self, choices: LineChoices, count: int) -> list[TierOffer]:
        """Urmatoarele `count` trepte de cantitate peste cea ceruta, pretuite de calculator."""


# ---------- fisier ----------

class FileVerdict(str, Enum):
    OK = "ok"
    WEAK = "weak"          # se poate tipari, dar clientul trebuie anuntat
    UNUSABLE = "unusable"  # cerem alt fisier sau propunem vectorizare


class FileReport(BaseModel):
    kind: Literal["vector", "raster", "mixed", "unknown"]
    mime: str
    width_px: int | None = None
    height_px: int | None = None
    dpi_at_size: Decimal | None = None   # la dimensiunea finala ceruta
    has_transparency: bool | None = None
    color_mode: str | None = None        # RGB, CMYK, L, ...
    pages: int | None = None
    verdict: FileVerdict
    problems: list[str] = Field(default_factory=list)  # coduri stabile, nu text pentru client


class FilePort(Protocol):
    def check_file(self, path: str, width_cm: Decimal, height_cm: Decimal) -> FileReport: ...


# ---------- mockup si imaginea de oferta ----------

class MockupResult(BaseModel):
    template_id: str
    image_path: str


class OfferLine(BaseModel):
    label: str
    quantity: int
    total_ex_vat: Decimal
    total: Decimal
    unit_price: Decimal
    highlighted: bool = False


class MockupPort(Protocol):
    def make_mockup(self, design_path: str, context_hint: str, out_dir: str) -> MockupResult:
        """Compoziteaza designul pe un sablon foto ales dupa context (borcan, pahar, cutie...)."""

    def make_offer_image(
        self, mockup_path: str | None, lines: list[OfferLine], production_term: str,
        valid_until: datetime, out_dir: str,
    ) -> str:
        """O singura imagine: mockup + tabel de pret fara si cu TVA, termen, valabilitate."""


# ---------- checkout, CRM, predare ----------

class Checkout(BaseModel):
    draft_order_id: str
    invoice_url: str
    total: Decimal


class Contact(BaseModel):
    channel: Channel
    key: str                    # wa_id (cifre) sau id-ul sesiunii de chat
    phone: str | None = None
    name: str | None = None
    email: str | None = None
    ad_source: str | None = None  # sursa reclamei, pentru raportul ec-agency


class CheckoutPort(Protocol):
    def create_checkout(self, quote: PriceQuote, contact: Contact, artwork_url: str | None,
                        valid_until: datetime) -> Checkout: ...


class CrmPort(Protocol):
    def upsert_lead(self, contact: Contact, summary: str, quote: PriceQuote | None,
                    checkout: Checkout | None, status: str) -> str:
        """Intoarce id-ul lead-ului din CRM."""


class HandoffReason(str, Enum):
    NOT_IN_CALCULATOR = "not_in_calculator"
    VALUE_OVER_THRESHOLD = "value_over_threshold"
    SPECIAL_TERMS = "special_terms"       # reducere, termen sub standard, facturare speciala
    COMPLAINT = "complaint"
    OFFER_LIMIT = "offer_limit"
    OFFER_REJECTED = "offer_rejected"
    FILE_UNUSABLE = "file_unusable"
    CUSTOMER_ASKED = "customer_asked"
    NOT_UNDERSTOOD = "not_understood"


class HandoffPort(Protocol):
    def handoff(self, contact: Contact, reason: HandoffReason, summary: str, now: datetime) -> None: ...


# ---------- conversatie ----------

class Attachment(BaseModel):
    path: str            # fisier local, deja descarcat de stratul de canal
    mime: str
    filename: str | None = None
    public_url: str | None = None


class InboundMessage(BaseModel):
    contact: Contact
    message_id: str | None = None   # id stabil al mesajului, pentru deduplicare
    text: str = ""
    button_id: str | None = None
    attachments: list[Attachment] = Field(default_factory=list)
    received_at: datetime
    from_staff: bool = False   # mesaj trimis de un om din aplicatia WhatsApp: conversatia trece pe manual


class Button(BaseModel):
    id: str
    title: str   # cel mult 20 de caractere (limita WhatsApp)


class OutboundAction(BaseModel):
    """Ce are de trimis canalul. Canalul nu decide nimic, doar livreaza."""

    kind: Literal["text", "buttons", "image", "handoff", "pending_approval"]
    text: str = ""
    buttons: list[Button] = Field(default_factory=list)
    image_path: str | None = None
    handoff_reason: HandoffReason | None = None
    approval_id: str | None = None   # mod umbra: oferta asteapta aprobarea unui om


class Engine(Protocol):
    def handle(self, message: InboundMessage) -> list[OutboundAction]: ...

    def approve(self, approval_id: str, approved_by: str, now: datetime,
                edited_text: str | None = None) -> list[OutboundAction]:
        """Mod umbra: omul aproba oferta pregatita; intoarce actiunile de trimis."""

    def reject(self, approval_id: str, rejected_by: str, now: datetime) -> None: ...


# ---------- mod asistat (extensia Chrome pentru WhatsApp Web) ----------
# Extensia citeste conversatia deschisa si cere o sugestie. Nimic nu pleaca automat:
# omul insereaza textul in caseta WhatsApp si apasa el Trimite.

class AssistMessage(BaseModel):
    id: str                               # id-ul mesajului din WhatsApp Web (stabil)
    direction: Literal["in", "out"]       # in = client, out = noi (om)
    text: str = ""
    sent_at: datetime | None = None
    attachments: list[Attachment] = Field(default_factory=list)


class AssistSuggestion(BaseModel):
    suggestion_id: str
    kind: Literal["reply", "question", "offer", "needs_human", "none"]
    text: str = ""                        # textul propus, gata de inserat
    options: list[str] = Field(default_factory=list)   # variante scurte de raspuns asteptate de la client
    image_path: str | None = None         # imaginea de oferta / mockup, de atasat manual
    note_for_staff: str = ""              # de ce (ex. peste prag, fisier slab); nu se trimite clientului
    handoff_reason: HandoffReason | None = None
    offer_lines: list[OfferLine] = Field(default_factory=list)
    can_create_payment_link: bool = False
    payment_url: str | None = None


class AssistEngine(Protocol):
    def suggest(self, contact: Contact, messages: list[AssistMessage], now: datetime) -> AssistSuggestion:
        """Primeste conversatia vizibila (idempotent dupa id-urile mesajelor) si intoarce sugestia curenta."""

    def create_payment_link(self, suggestion_id: str, staff: str, now: datetime,
                            edited_text: str | None = None) -> AssistSuggestion:
        """Omul accepta oferta: creeaza Draft Order si intoarce textul final cu linkul de plata."""


# ---------- baza de cunostinte (intrebari despre materiale, livrare, plata, fisiere...) ----------
# Raspunsurile vin numai din intrari aprobate. Ce nu e in baza nu se afirma: merge la om.

class KnowledgeEntry(BaseModel):
    id: str
    topic: str                      # materiale, rezistenta, livrare, plata, fisiere, comanda, mostre...
    question: str                   # intrebarea canonica
    answer: str                     # raspunsul aprobat, in romana, gata de adaptat ca ton
    applies_to: list[str] = Field(default_factory=list)   # produse / materiale; gol = general
    source: str = ""                # de unde vine (pagina, document), pentru verificare
    status: Literal["verified", "needs_owner"] = "needs_owner"


class KnowledgePort(Protocol):
    def search(self, query: str, limit: int = 5) -> list[KnowledgeEntry]:
        """Doar intrarile `verified`. Lista goala inseamna: nu stim, intreaba un om."""

    def topics(self) -> list[str]: ...
