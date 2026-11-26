"""Validarea stricta: orice abatere opreste incarcarea."""
from __future__ import annotations

import json

import pytest

from ec_quote.knowledge import KnowledgeError, load_content
from tests.knowledge.conftest import LEXICON, POLICY, open_question, verified


def test_a_valid_base_loads(write_kb):
    content = load_content(write_kb())
    assert [entry.id for entry in content.entries] == ["rezistenta-apa", "masina-spalat-vase"]
    assert content.entries[0].topic == "rezistenta"
    assert content.contradictions == []


@pytest.mark.parametrize(
    ("entries", "message"),
    [
        ([verified(), verified()], "id duplicat"),
        ([verified(id="Rezistenta Apa")], "id invalid"),
        ([verified(source="")], "nu are sursa"),
        ([verified(source_refs=[])], "nu are sursa"),
        ([verified(answer="")], "nu are raspuns"),
        ([verified(answer="Rezistența este garantată? Da, garantat.")], "cuvant interzis"),
        ([verified(answer="Costă 25 lei.")], "fara sursa in `amounts`"),
        ([verified(answer="Costă 1.250,50 RON.")], "fara sursa in `amounts`"),
        ([verified(answer="Reducere de 10% la tot.")], "fara sursa in `amounts`"),
        ([verified(answer="Costă 25 lei.", amounts=[{"text": "25 lei", "source": ""}])], "nu are sursa"),
        ([verified(amounts=[{"text": "25 lei", "source": "test:tarif"}])], "nu apare in raspuns"),
        ([verified(answer="Da — sunt rezistente.")], "em dash"),
        ([verified(answer="Termen de 2–10 zile.")], "em dash"),
        ([verified(answer="Da, sunt rezistente \U0001F600")], "emoji"),
        ([verified(answer="Da ✅")], "emoji"),
        ([verified(answer="Rezistenţa este bună.")], "sedila"),
        ([verified(answer="Minimul este {{min}} bucăți.")], "substituent"),
        ([verified(answer="Da. " * 80)], "peste limita"),
        ([verified(question=" ")], "lipseste intrebarea"),
        ([verified(question="Rezistă — la apă?")], "em dash"),
        ([verified(variants=["rezista \U0001F4A7"])], "emoji"),
        ([verified(anchors=[])], "lipsesc ancorele"),
        ([verified(last_checked="ieri")], "last_checked"),
        ([verified(owner_question="De ce?")], "nu are intrebare pentru owner"),
        ([verified(status="draft")], "status"),
        ([verified(surprise=1)], "surprise"),
        ([verified(topic="livrare")], "difera de al fisierului"),
        (["nu sunt obiect"], "trebuie sa fie un obiect"),
        ([open_question(answer="Da, rezistă.")], "nu are voie sa aiba raspuns"),
        ([open_question(owner_question="")], "lipseste intrebarea pentru owner"),
        ([open_question(owner_question="Rezistă?\nSigur?")], "pe un rand"),
        ([open_question(owner_question="Rezistă — sau nu?")], "em dash"),
        ([], "nicio intrare"),
    ],
)
def test_invalid_entries_fail_loading(write_kb, entries, message):
    with pytest.raises(KnowledgeError, match=message):
        load_content(write_kb(entries))


def test_a_published_amount_passes_only_with_its_source(write_kb):
    entry = verified(answer="Livrarea costă 25 lei.", amounts=[{"text": "25 LEI", "source": "test:tarif"}])
    content = load_content(write_kb([entry]))
    assert content.entries[0].amounts[0].source == "test:tarif"


def test_forbidden_words_are_checked_in_answers_not_in_customer_phrasings(write_kb):
    content = load_content(write_kb([verified(variants=["e garantat ca rezista la apa"])]))
    assert content.entries[0].variants == ["e garantat ca rezista la apa"]


def test_duplicate_ids_across_files_fail(write_kb):
    other = json.dumps({"topic": "livrare", "entries": [verified()]})
    with pytest.raises(KnowledgeError, match="id duplicat, apare si in livrare.json"):
        load_content(write_kb(extra={"livrare.json": other}))


@pytest.mark.parametrize(
    ("name", "text", "message"),
    [
        ("livrare.json", "{nu e json", "nu este JSON valid"),
        ("livrare.json", "[]", "asteptam un obiect"),
        ("livrare.json", json.dumps({"topic": "plata", "entries": []}), "numele fisierului"),
    ],
)
def test_malformed_topic_files_fail(write_kb, name, text, message):
    with pytest.raises(KnowledgeError, match=message):
        load_content(write_kb(extra={name: text}))


def test_missing_directory_and_missing_support_files_fail(write_kb, tmp_path):
    with pytest.raises(KnowledgeError, match="directorul bazei de cunostinte lipseste"):
        load_content(tmp_path / "nu-exista")
    root = write_kb()
    (root / "_policy.json").unlink()
    with pytest.raises(KnowledgeError, match="_policy.json: fisierul lipseste"):
        load_content(root)


@pytest.mark.parametrize(
    ("policy", "message"),
    [
        ({"min_score": 0.5}, "_policy.json"),
        ({**POLICY, "min_score": 0}, "praguri"),
        ({**POLICY, "max_answer_chars": 0}, "praguri"),
    ],
)
def test_invalid_policy_fails(write_kb, policy, message):
    with pytest.raises(KnowledgeError, match=message):
        load_content(write_kb(policy=policy))


@pytest.mark.parametrize(
    ("lexicon", "message"),
    [
        ([], "trebuie sa fie un obiect"),
        ({**LEXICON, "stopwords": {}}, "stopwords este lista"),
        ({**LEXICON, "synonyms": {"apa": "umezeala"}}, "trebuie sa fie o lista"),
        ({**LEXICON, "synonyms": {"apa": ["Apă"]}}, "fara diacritice"),
        ({**LEXICON, "synonyms": {"apa": ["ud"], "frig": ["ud"]}, "product_concepts": []}, "doua concepte"),
        ({**LEXICON, "phrases": {"Mașina de spălat": "spalatvase"}}, "expresia"),
        ({**LEXICON, "stopwords": ["umezeala"]}, "si cuvant ignorat, si sinonim"),
        ({**LEXICON, "product_concepts": ["banner"]}, "product_concepts"),
    ],
)
def test_invalid_lexicon_fails(write_kb, lexicon, message):
    with pytest.raises(KnowledgeError, match=message):
        load_content(write_kb(lexicon=lexicon))


def _contradiction(**changes) -> dict:
    item = {"id": "termen", "topic": "termene", "summary": "Site-ul spune una, calculatorul alta.",
            "sources": ["site:/a", "repo:b"], "question": "Care este termenul corect?"}
    item.update(changes)
    return item


def test_contradictions_load(write_kb):
    content = load_content(write_kb(contradictions={"contradictions": [_contradiction()]}))
    assert content.contradictions[0].id == "termen"


@pytest.mark.parametrize(
    ("contradictions", "message"),
    [
        ([], "lipseste lista"),
        ({"contradictions": [_contradiction(), _contradiction()]}, "id duplicat"),
        ({"contradictions": [_contradiction(sources=["site:/a"])]}, "cel putin doua surse"),
        ({"contradictions": [_contradiction(summary="A — B")]}, "em dash"),
        ({"contradictions": [{"id": "x"}]}, "Field required"),
    ],
)
def test_invalid_contradictions_fail(write_kb, contradictions, message):
    with pytest.raises(KnowledgeError, match=message):
        load_content(write_kb(contradictions=contradictions))
