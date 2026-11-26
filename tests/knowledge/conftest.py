from __future__ import annotations

import json
from pathlib import Path

import pytest

from ec_quote.knowledge import KnowledgeBase

POLICY = {"min_score": 0.5, "max_answer_chars": 200, "max_query_chars": 300, "forbidden_words": ["garantat"]}
LEXICON = {
    "stopwords": ["la", "se", "si", "de"],
    "phrases": {"masina de spalat vase": "spalatvase"},
    "synonyms": {"apa": ["apa", "umezeala"], "spalatvase": ["dishwasher"], "flyer": ["flyere"]},
    "product_concepts": ["flyer"],
}


def verified(**changes) -> dict:
    entry = {
        "id": "rezistenta-apa", "question": "Sunt rezistente la apă?", "answer": "Da, sunt rezistente la apă.",
        "source": "pagina de test", "source_refs": ["test:pagina"], "status": "verified",
        "anchors": ["apa"], "variants": ["rezista la apa"], "keywords": ["apa"], "last_checked": "2026-11-26",
    }
    entry.update(changes)
    return entry


def open_question(**changes) -> dict:
    entry = {
        "id": "masina-spalat-vase", "question": "Rezistă în mașina de spălat vase?", "answer": "",
        "source": "", "status": "needs_owner", "anchors": ["spalatvase"],
        "variants": ["rezista la masina de spalat vase"], "last_checked": "2026-11-26",
        "owner_question": "Rezistă la mașina de spălat vase? (da / nu)",
    }
    entry.update(changes)
    return entry


@pytest.fixture
def write_kb(tmp_path: Path):
    """Scrie o baza mica intr-un director temporar si intoarce calea."""

    def _write(entries: list[dict] | None = None, *, policy: dict | None = None, lexicon: dict | None = None,
               contradictions: object = None, topic: str = "rezistenta", extra: dict[str, str] | None = None) -> Path:
        root = tmp_path / "knowledge"
        root.mkdir(exist_ok=True)
        (root / "_policy.json").write_text(json.dumps(policy if policy is not None else POLICY), encoding="utf-8")
        (root / "_lexicon.json").write_text(json.dumps(lexicon if lexicon is not None else LEXICON), encoding="utf-8")
        if contradictions is not None:
            (root / "_contradictions.json").write_text(json.dumps(contradictions), encoding="utf-8")
        body = {"topic": topic, "entries": entries if entries is not None else [verified(), open_question()]}
        (root / "rezistenta.json").write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
        for name, text in (extra or {}).items():
            (root / name).write_text(text, encoding="utf-8")
        return root

    return _write


@pytest.fixture(scope="session")
def kb() -> KnowledgeBase:
    """Baza reala din depozit."""
    return KnowledgeBase.from_dir()
