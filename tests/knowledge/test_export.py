"""Exportul intrebarilor pentru owner."""
from __future__ import annotations

from ec_quote.knowledge import load_content
from ec_quote.knowledge import export_questions
from tests.knowledge.conftest import open_question, verified

CONTRADICTION = {"contradictions": [{
    "id": "termen", "topic": "termene", "summary": "Site-ul spune una, calculatorul alta.",
    "sources": ["site:/a", "repo:b"], "question": "Care este termenul corect?",
}]}


def test_render_lists_open_questions_grouped_by_topic_and_contradictions(write_kb):
    root = write_kb([verified(), open_question(source="Nicio sursă."), open_question(id="alt", source="")],
                    contradictions=CONTRADICTION)
    text = export_questions.render(load_content(root))
    assert text.startswith("# Întrebări pentru owner\n")
    assert "Stare la 2026-11-26: 1 răspunsuri verificate, 2 întrebări deschise, 1 contradicții între surse." in text
    assert "### Rezistența materialelor" in text
    assert "1. Rezistă la mașina de spălat vase? (da / nu) (`masina-spalat-vase`)" in text
    assert "   - Clientul întreabă: „Rezistă în mașina de spălat vase?”" in text
    assert "   - Ce am găsit: Nicio sursă." in text
    assert "2. Rezistă la mașina de spălat vase? (da / nu) (`alt`)" in text
    assert "1. Care este termenul corect? (`termen`, Termene și urgențe)" in text
    assert "   - Surse: site:/a; repo:b" in text
    assert "Da, sunt rezistente la apă." not in text      # raspunsurile verificate nu apar aici


def test_render_without_contradictions_and_with_an_unknown_topic(write_kb):
    text = export_questions.render(load_content(write_kb()))
    assert "Nicio contradicție găsită." in text
    assert export_questions._title("ambalare") == "Ambalare"


def test_main_writes_then_check_passes_then_detects_drift(write_kb, tmp_path, capsys):
    root = write_kb()
    out = tmp_path / "docs" / "intrebari.md"
    assert export_questions.main(["--knowledge-dir", str(root), "--out", str(out), "--check"]) == 1
    assert export_questions.main(["--knowledge-dir", str(root), "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == export_questions.render(load_content(root))
    assert not out.with_suffix(".md.tmp").exists()
    assert export_questions.main(["--knowledge-dir", str(root), "--out", str(out), "--check"]) == 0
    out.write_text("altceva", encoding="utf-8")
    assert export_questions.main(["--knowledge-dir", str(root), "--out", str(out), "--check"]) == 1
    assert "nu este la zi" in capsys.readouterr().err


def test_the_committed_document_is_up_to_date():
    assert export_questions.default_output().name == "intrebari-pentru-owner.md"
    assert export_questions.main(["--check"]) == 0


def test_the_committed_document_has_no_dashes_or_emojis():
    text = export_questions.default_output().read_text(encoding="utf-8")
    assert "—" not in text and "–" not in text
    assert "needs_owner" not in text
