"""Cautarea: clasament pe formulari reale, prag, intrebari deschise, filtrare pe produs."""
from __future__ import annotations

import inspect
import json

import pytest

from ec_quote.contracts import KnowledgeEntry, KnowledgePort
from ec_quote.knowledge import AuthoredEntry, KnowledgeBase, default_knowledge_dir
from ec_quote.knowledge.text import Lexicon, edit_distance, normalize, stem, words
from tests.knowledge.conftest import open_question, verified
from tests.knowledge.phrasings import PHRASINGS


def test_the_table_is_large_enough():
    assert len(PHRASINGS) >= 40
    assert sum(expected is None for _, expected in PHRASINGS) >= 10


@pytest.mark.parametrize(("query", "expected"), PHRASINGS)
def test_ranking_on_customer_phrasings(kb, query, expected):
    found = kb.search(query)
    assert (found[0].id if found else None) == expected


def test_every_expected_id_exists_and_is_verified(kb):
    for _, expected in PHRASINGS:
        if expected is not None:
            assert kb.entry(expected).status == "verified"


def test_needs_owner_entries_are_never_returned(kb):
    open_ids = {entry.id for entry in kb.needs_owner()}
    assert open_ids
    for entry in kb.authored():
        for text in (entry.question, *entry.variants, *entry.keywords, entry.owner_question):
            for found in kb.search(text, limit=50):
                assert found.status == "verified"
                assert found.id not in open_ids
                assert found.answer


def test_an_open_question_blocks_a_weaker_verified_answer(kb):
    assert kb.search("rezista la apa?")[0].id == "rezistenta-apa"
    assert kb.search("stickerele rezista la apa si la masina de spalat vase?") == []
    blocked = kb.open_question("stickerele rezista la apa si la masina de spalat vase?")
    assert blocked is not None and blocked.id == "masina-spalat-vase" and blocked.answer == ""
    assert kb.open_question("rezista la apa?") is None
    assert kb.open_question("cat e ceasul") is None


def test_every_verified_entry_has_a_source_and_every_open_one_a_question(kb):
    for entry in kb.authored():
        if entry.status == "verified":
            assert entry.source.strip() and entry.source_refs and entry.answer.strip(), entry.id
            assert entry.last_checked
        else:
            assert entry.answer == "" and entry.owner_question.strip(), entry.id


def test_search_returns_plain_contract_entries(kb):
    found = kb.search("rezista la apa?", limit=1)
    assert len(found) == 1 and type(found[0]) is KnowledgeEntry
    assert found[0].source and found[0].status == "verified"
    assert found[0].applies_to and "Sticker Standard" in found[0].applies_to
    port: KnowledgePort = kb
    assert port.topics() == kb.topics()
    assert list(inspect.signature(KnowledgeBase.search).parameters)[1:3] == ["query", "limit"]


def test_limit_and_empty_queries(kb):
    assert kb.search("cat dureaza livrarea", limit=0) == []
    assert len(kb.search("cat dureaza livrarea", limit=1)) == 1
    assert len(kb.search("cat dureaza livrarea", limit=5)) >= 2
    assert kb.search("") == []
    assert kb.search("   ???  ") == []
    assert kb.search("si la de pe 100 5x5") == []
    assert kb.search("x" * 5000) == []


def test_topics_and_open_questions(kb):
    topics = kb.topics()
    assert topics == sorted(topics)
    assert {"rezistenta", "materiale", "livrare", "plata", "fisiere", "retur", "contact"} <= set(topics)
    assert "mostre" not in topics           # doar intrebari deschise: nimic de servit
    open_topics = {entry.topic for entry in kb.needs_owner()}
    assert "mostre" in open_topics
    assert all(entry.status == "needs_owner" and entry.answer == "" for entry in kb.needs_owner())
    with pytest.raises(KeyError):
        kb.entry("nu-exista")
    assert kb.contradictions() and kb.contradictions()[0].question


def test_applies_to_filters_by_product_or_material(kb):
    assert kb.search("rezista la apa?", applies_to="Sticker Standard")[0].id == "rezistenta-apa"
    assert kb.search("rezista la apa?", applies_to="Premium")[0].id == "rezistenta-apa"
    assert kb.search("rezista la apa?", applies_to="etichete transparente")[0].id == "rezistenta-apa"
    assert kb.search("rezista la apa?", applies_to="Flyere") == []
    assert kb.search("rezista la apa?", applies_to="  ")[0].id == "rezistenta-apa"
    # o intrare generala ramane disponibila pentru orice produs
    assert kb.search("pot plati cu cardul", applies_to="Flyere")[0].id == "metode-plata"
    assert kb.search("in cat timp sunt gata", applies_to="Flyere")[0].id == "termen-carti-flyere"
    assert all(e.id != "termen-carti-flyere" for e in kb.search("in cat timp sunt gata", applies_to="Sticker Standard"))


def test_an_entry_written_for_some_products_does_not_answer_for_another_named_in_the_query(kb):
    assert kb.search("flyerele rezista la apa?") == []
    assert all(e.id != "rezistenta-exterior" for e in kb.search("bannerele rezista la ploaie?"))
    assert kb.search("magnetii rezista la apa?")[0].id == "rezistenta-magneti"
    assert kb.search("stickerele personalizate premium rezista la apa?")[0].id == "rezistenta-apa"


def test_answers_carry_no_unflagged_amounts_and_stay_whatsapp_sized(kb):
    for entry in kb.authored():
        assert len(entry.answer) <= 420, entry.id
        for amount in entry.amounts:
            assert amount.source.strip(), entry.id
    priced = {entry.id for entry in kb.authored() if entry.amounts}
    assert priced == {"cost-livrare", "grafica-carti-flyere"}


def test_pinned_texts_of_the_liability_answers(kb):
    assert kb.entry("rezistenta-apa").answer == (
        "Da. Atât etichetele, cât și stickerele sunt printate UV și sunt rezistente la apă, "
        "la razele UV și la zgârieturi."
    )
    assert kb.entry("rezistenta-ulei").answer == "Da, materialul este rezistent la umezeală și ulei."
    assert kb.entry("finisaj").answer == "Finisajul este cu lac UV mat, fără laminare."
    assert kb.entry("cost-livrare").answer == (
        "Livrarea în România costă 25 lei și este gratuită la comenzile de peste 350 lei."
    )


def test_content_files_are_one_per_topic(kb):
    root = default_knowledge_dir()
    for path in root.glob("*.json"):
        if path.name.startswith("_"):
            continue
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["topic"] == path.stem
        assert all(isinstance(AuthoredEntry.model_validate({"topic": path.stem, **e}), AuthoredEntry)
                   for e in body["entries"])


# ---------- baza mica, pentru regulile de clasament ----------

def test_small_base_ranking_rules(write_kb):
    kb = KnowledgeBase.from_dir(write_kb([
        verified(),
        open_question(),
        verified(id="apa-flyere", question="Flyerele rezistă la apă?", variants=[], applies_to=["Flyere"],
                 answer="Flyerele sunt din hârtie."),
    ]))
    assert [e.id for e in kb.search("rezista la apa")] == ["rezistenta-apa", "apa-flyere"]
    assert [e.id for e in kb.search("flyere rezista la apa")] == ["apa-flyere", "rezistenta-apa"]
    # cu produsul cerut explicit, intrarea scrisa pentru el trece inaintea celei generale
    assert [e.id for e in kb.search("rezista la apa", applies_to="Flyere")] == ["apa-flyere", "rezistenta-apa"]
    assert kb.search("flyere", applies_to="Flyere") == []   # doar numele produsului nu este o intrebare
    assert kb.search("rezista la masina de spalat vase") == []
    assert kb.search("rezista la dishwasher") == []
    assert kb.search("rezista la benzina") == []          # fara ancora nu exista raspuns
    assert kb.rank("rezista la masina de spalat vase")[0].status == "needs_owner"
    assert kb.topics() == ["rezistenta"]
    assert [e.id for e in kb.needs_owner()] == ["masina-spalat-vase"]
    assert kb.contradictions() == []


def test_a_tie_between_an_open_question_and_an_answer_returns_nothing(write_kb):
    kb = KnowledgeBase.from_dir(write_kb([
        verified(),
        open_question(id="apa-deschisa", question="Sunt rezistente la apă?", anchors=["apa"],
                      variants=["rezista la apa"], keywords=["apa"]),
    ]))
    assert kb.search("rezista la apa") == []


# ---------- text ----------

@pytest.mark.parametrize("word", ["rezista", "rezistă", "rezistente", "rezistent", "rezistenta", "REZISTENȚI"])
def test_light_stemming_joins_the_forms_of_a_word(word):
    assert stem(words(word)[0]) == "rezist"


def test_normalize_words_and_stem_edges():
    assert normalize("  Mașină   de SPĂLAT\tvase ") == "masina de spalat vase"
    assert words("500 buc, 5x5 cm, A4!") == ["buc", "cm", "a4"]
    assert stem("apa") == "apa" and stem("livrarea") == "livr" and stem("cardul") == "card"


def test_edit_distance():
    assert edit_distance("transparente", "trasparente", 2) == 1
    assert edit_distance("card", "cardul", 1) == 2
    assert edit_distance("apa", "congelator", 2) == 3
    assert edit_distance("livrare", "factura", 1) == 2


def test_lexicon_concepts_phrases_synonyms_and_typos():
    lexicon = Lexicon(
        stopwords=frozenset({"la", "de", "se"}),
        phrases={"masina de spalat vase": "spalatvase"},
        synonyms={"apa": ["apa", "umezeala"], "frig": ["congelator", "frigider"]},
    )
    lexicon.learn("Aveți și transparente? Sticker.")
    assert lexicon.concepts("Rezistă la apă, la umezeală?") == ["rezist", "apa"]
    assert lexicon.concepts("la mașina de spălat vase") == ["spalatvase"]
    assert lexicon.concepts("congelatorul") == ["frig"]              # radacina unui sinonim
    assert lexicon.concepts("congelatr") == ["frig"]                 # greseala de tastare
    assert lexicon.concepts("trasparente") == ["transpar"]
    assert lexicon.concepts("transparente") == ["transpar"]
    assert lexicon.concepts("frigiderr umezeale") == ["frig", "apa"]
    assert lexicon.concepts("xyzqw") == ["xyzqw"]                    # necunoscut ramane ca atare
    assert Lexicon().concepts("Rezistă la apă") == ["rezist", "la", "apa"]


def test_ambiguous_typos_are_not_guessed():
    lexicon = Lexicon(synonyms={"hartie": ["carte"], "aliment": ["carne"]})
    assert lexicon.concepts("carpe") == ["carp"]
    assert lexicon.concepts("carnee") == ["aliment"]
