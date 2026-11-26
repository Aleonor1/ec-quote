"""Baza de cunostinte reala (`knowledge/`) impreuna cu verificarile de text ale motorului."""
from __future__ import annotations

import pytest

from ec_quote.agent.engine import _catalog_percents, _catalog_terms
from ec_quote.agent.guard import check_text, money_mentions
from ec_quote.pricing.fake import FAKE_CATALOG

from .helpers import CHAT, build, close, customer, script, suggest


@pytest.fixture
def ctx(tmp_path):
    built = build(tmp_path)
    yield built
    close(built)


def ask(ctx, question: str, *replies: str, query: str | None = None) -> dict:
    customer(ctx, question)
    script(ctx, ("search_knowledge", {"query": query or question}), *replies)
    return suggest(ctx)


def found(ctx, query: str, *needles: str):
    """Intrarea verificata gasita prin cautare, nu dupa id."""
    entries = ctx.engine.knowledge.search(query)
    assert entries, query
    entry = next((e for e in entries if all(n in e.answer for n in needles)), None)
    assert entry is not None, (query, [e.id for e in entries])
    return entry


def test_resistance_wording_of_a_returned_entry_passes(ctx):
    entry = found(ctx, "sunt rezistente la apa", "apă", "UV", "zgârieturi")
    answer = ask(ctx, "Sunt rezistente la apa?", entry.answer)
    assert answer["kind"] == "reply" and answer["text"] == entry.answer

    # Aceeasi afirmatie, fara ca intrarea sa fi fost intoarsa in runda, este blocata.
    customer(ctx, "si la soare?")
    script(ctx, entry.answer, entry.answer, entry.answer)
    blocked = suggest(ctx)
    assert blocked["kind"] == "needs_human" and blocked["text"] == ""

    # Ce nu scrie in intrare nu trece nici dupa cautare.
    extra = ask(ctx, "rezista la apa?", entry.answer + " Rezistă și la congelator.", entry.answer)
    assert extra["text"] == entry.answer


def test_published_amounts_of_a_returned_entry_pass(ctx):
    entry = found(ctx, "cat costa livrarea", "lei")
    published = [a for a in money_mentions(entry.answer) if a is not None]
    assert len(published) >= 2
    assert {a for amount in ctx.engine.knowledge.entry(entry.id).amounts
            for a in money_mentions(amount.text)} == set(published)

    answer = ask(ctx, "Cat costa livrarea?", entry.answer)
    assert answer["kind"] == "reply" and answer["text"] == entry.answer

    wrong = entry.answer.replace(f"{published[0]} lei", "19 lei")
    assert wrong != entry.answer
    corrected = ask(ctx, "cat e transportul?", wrong, entry.answer, query="cat costa livrarea")
    assert corrected["text"] == entry.answer


def test_published_production_term_of_a_returned_entry_passes(ctx):
    entry = found(ctx, "cat dureaza livrarea", "zile lucrătoare")
    answer = ask(ctx, "In cat timp ajunge comanda?", entry.answer, query="cat dureaza livrarea")
    assert answer["kind"] == "reply" and "zile lucrătoare" in answer["text"]

    promised = ask(ctx, "se poate mai repede?", "Da, o putem livra în 1 zi.", entry.answer, query="cat dureaza livrarea")
    assert promised["text"] == entry.answer


def test_open_owner_question_reaches_the_staff_note(ctx):
    opened = ctx.engine.knowledge.open_question("rezista la congelator")
    assert opened is not None and ctx.engine.knowledge.search("rezista la congelator") == []
    miss = ask(ctx, "Rezista la congelator?", "Verificăm și revenim.", query="rezista la congelator")
    assert miss["kind"] == "needs_human"
    assert miss["note_for_staff"].startswith("Nu avem un răspuns aprobat pentru: Rezista la congelator?")
    owner_question = ctx.engine.knowledge.entry(opened.id).owner_question or opened.question
    assert owner_question in miss["note_for_staff"]
    assert "congelator" not in miss["text"]
    gaps = ctx.engine.knowledge_gaps()
    assert [(g.key, g.query) for g in gaps] == [(CHAT, "rezista la congelator")]


def test_every_verified_answer_passes_the_guard_when_it_was_returned(ctx):
    engine = ctx.engine
    verified = [e for e in engine.knowledge.authored() if e.status == "verified"]
    assert len(verified) > 20
    blocked = {}
    for entry in verified:
        problems = check_text(
            entry.answer, allowed_amounts=engine._published_amounts(entry.id),
            allowed_percents=[engine.rules.vat_percent, *_catalog_percents(FAKE_CATALOG)],
            approved_claims=engine.rules.approved_material_claims, catalog_terms=_catalog_terms(FAKE_CATALOG),
            allowed_terms=[engine.rules.production_term_standard], sources=[f"{entry.question} {entry.answer}"])
        if problems:
            blocked[entry.id] = problems
    assert blocked == {}


def test_product_scoped_search_falls_back_when_the_catalog_name_is_unknown(ctx):
    customer(ctx, "stickerele pe vinil rezista la apa?")
    script(ctx, ("search_knowledge", {"query": "rezista la apa", "product_or_material": "Vinil Alb Lucios"}),
           found(ctx, "rezista la apa", "apă").answer)
    assert suggest(ctx)["kind"] == "reply"
