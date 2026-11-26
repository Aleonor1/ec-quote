"""Definitiile uneltelor expuse modelului. Lista este fixa si ordonata, ca prefixul sa ramana in cache."""
from __future__ import annotations

from ec_quote.contracts import HandoffReason

# Motivele pe care le poate alege modelul; restul sunt decise numai de cod.
MODEL_HANDOFF_REASONS = [
    HandoffReason.NOT_IN_CALCULATOR.value,
    HandoffReason.SPECIAL_TERMS.value,
    HandoffReason.COMPLAINT.value,
    HandoffReason.CUSTOMER_ASKED.value,
    HandoffReason.NOT_UNDERSTOOD.value,
]

_LINE_PROPERTIES = {
    "product_id": {"type": "string", "description": "Id-ul produsului, exact ca in catalog."},
    "material_name": {"type": "string", "description": "Numele materialului, exact ca in catalog."},
    "shape": {"type": "string", "description": "Forma, exact ca in catalog."},
    "width_cm": {"type": "number", "description": "Latimea in centimetri."},
    "height_cm": {"type": "number", "description": "Inaltimea in centimetri."},
    "quantity": {"type": "integer", "minimum": 1},
    "add_ons": {
        "type": "array",
        "description": "Optiuni suplimentare din catalog (grupul si alegerea).",
        "items": {
            "type": "object",
            "properties": {"group": {"type": "string"}, "choice": {"type": "string"}},
            "required": ["group", "choice"],
            "additionalProperties": False,
        },
    },
    "adhesive": {"type": "string", "enum": ["standard", "strong"]},
    "white_print": {"type": "boolean"},
    "cut": {"type": "string", "enum": ["none", "double", "back"]},
    "urgent": {"type": "boolean", "description": "Numai daca urgenta este activa in catalog si clientul o cere."},
    "file_editing": {"type": "string", "enum": ["none", "upscale", "vectorize"]},
}


def _tool(name: str, description: str, properties: dict, required: list[str]) -> dict:
    return {
        "name": name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
    }


TOOLS: list[dict] = sorted([
    _tool(
        "find_products",
        "Cauta produse in catalogul calculatorului dupa cuvinte din titlu. Intoarce id-ul, formele, "
        "materialele si limitele de dimensiune. Foloseste-l cand nu esti sigur ce produs se potriveste.",
        {"query": {"type": "string", "description": "Cuvinte cheie, de exemplu: etichete rola, stickere."}},
        ["query"],
    ),
    _tool(
        "get_price",
        "Pretul exact de pe site pentru o linie. Intoarce quote_id si pretul, sau status unpriced cu motivul "
        "calculatorului. Cheama-l cand ai produsul, forma, dimensiunea, cantitatea si materialul.",
        _LINE_PROPERTIES,
        ["product_id", "material_name", "shape", "width_cm", "height_cm", "quantity"],
    ),
    _tool(
        "get_price_tiers",
        "Urmatoarele trepte de cantitate pentru o oferta deja pretuita, ca alternative in oferta. "
        "Numarul de trepte este stabilit de sistem.",
        {"quote_id": {"type": "string"}},
        ["quote_id"],
    ),
    _tool(
        "check_file",
        "Verifica fisierul trimis de client pentru tipar la dimensiunea finala. Intoarce verdictul "
        "(ok, weak, unusable) si codurile problemelor.",
        {"width_cm": {"type": "number"}, "height_cm": {"type": "number"}},
        ["width_cm", "height_cm"],
    ),
    _tool(
        "make_mockup",
        "Pune designul clientului pe o fotografie potrivita contextului. Necesita un fisier de la client.",
        {"context_hint": {"type": "string", "description": "Unde se aplica eticheta: borcan, sticla, cutie, pahar."}},
        ["context_hint"],
    ),
    _tool(
        "create_checkout",
        "Incheie ofertarea pentru un quote_id: sistemul compune oferta (imagine, pret fara si cu TVA, termen, "
        "valabilitate, link de plata) si o trimite. Dupa acest apel runda se incheie.",
        {
            "quote_id": {"type": "string"},
            "summary": {"type": "string", "description": "Rezumat scurt al comenzii, pentru CRM."},
        },
        ["quote_id", "summary"],
    ),
    _tool(
        "upsert_lead",
        "Actualizeaza lead-ul din CRM cu un rezumat scurt al cererii si, daca le-ai aflat, numele si emailul.",
        {
            "summary": {"type": "string"},
            "name": {"type": "string"},
            "email": {"type": "string"},
        },
        ["summary"],
    ),
    _tool(
        "handoff",
        "Preda conversatia unui coleg. Sistemul anunta clientul; dupa acest apel runda se incheie.",
        {
            "reason": {"type": "string", "enum": MODEL_HANDOFF_REASONS},
            "summary": {"type": "string", "description": "Ce doreste clientul si de ce este nevoie de un om."},
        },
        ["reason", "summary"],
    ),
    _tool(
        "ask_customer",
        "Trimite clientului o intrebare scurta sau cere-i alt fisier. Dupa acest apel runda se incheie. "
        "kind: clarify pentru un detaliu lipsa, not_understood cand nu intelegi cererea, "
        "file pentru a cere alt fisier.",
        {
            "text": {"type": "string"},
            "buttons": {
                "type": "array",
                "description": "Cel mult 3 variante, fiecare de cel mult 20 de caractere.",
                "items": {"type": "string"},
            },
            "kind": {"type": "string", "enum": ["clarify", "not_understood", "file"]},
        },
        ["text", "kind"],
    ),
], key=lambda tool: tool["name"])

TOOL_NAMES = frozenset(tool["name"] for tool in TOOLS)
