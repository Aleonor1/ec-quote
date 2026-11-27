"""Retentia datelor (purge) si verificarea documentului docs/privacy.md (story-13 AC 11 & 12)."""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from ec_quote.agent.rules import Rules
from ec_quote.agent.store import (
    Approval,
    ConversationState,
    InMemoryStore,
    KnowledgeGap,
    LoggedMessage,
    SqliteStore,
    Suggestion,
)
from ec_quote.contracts import (
    AssistSuggestion,
    Attachment,
    Contact,
    HandoffReason,
    LineChoices,
    LineProperty,
    OfferLine,
    PriceQuote,
)
from tests.agent.fakes import RULES_DATA

TZ = ZoneInfo("Europe/Bucharest")
NOW = datetime(2026, 11, 26, 12, 0, tzinfo=TZ)
OLD_KEY = "40700001111"
NEW_KEY = "40700002222"


def _quote(total: str = "302.50", ex_vat: str = "250.00") -> PriceQuote:
    choices = LineChoices(
        product_id="gid://shopify/Product/1",
        material_name="Vinyl alb",
        shape="Rotund",
        width_cm=Decimal("5"),
        height_cm=Decimal("5"),
        quantity=500,
        instructions="Text privat pe eticheta",
    )
    return PriceQuote(
        choices=choices,
        total=Decimal(total),
        total_ex_vat=Decimal(ex_vat),
        unit_price=Decimal("0.61"),
        discount_percent=Decimal("10"),
        breakdown={"promoPercent": 0},
        properties=[LineProperty(name="Cantitate", value="500 buc")],
    )


def _line() -> OfferLine:
    return OfferLine(
        label="500 buc",
        quantity=500,
        total_ex_vat=Decimal("250.00"),
        total=Decimal("302.50"),
        unit_price=Decimal("0.61"),
        highlighted=True,
    )


def _seed(store, data_dir: Path, key: str, moment: datetime, prefix: str) -> tuple[Path, Path]:
    inbound_file = data_dir / "conversations" / "whatsapp" / key / "inbound" / f"{prefix}.png"
    inbound_file.parent.mkdir(parents=True, exist_ok=True)
    inbound_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    out_file = data_dir / "out" / "whatsapp" / key / f"{prefix}-offer.png"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_bytes(b"\x89PNG\r\n\x1a\n")

    quote = _quote()
    line = _line()
    state = ConversationState(
        channel="whatsapp",
        key=key,
        contact=Contact(channel="whatsapp", key=key, phone=f"+{key}", name=f"Client {prefix}", email=f"{prefix}@ex.ro"),
        status="offer_sent",
        quotes={"q1": quote},
        design=Attachment(path=str(inbound_file), mime="image/png", filename=f"{prefix}.png",
                          public_url=f"https://cdn.test/{prefix}.png"),
        mockup_path=str(out_file),
        summary=f"Rezumat privat {prefix}",
        assist_seen=["m1"],
        payment_links={"q1": f"https://shop.test/pay/{prefix}"},
        last_message_at=moment,
        first_inbound_at=moment,
    )
    store.save(state)
    store.claim_inbound("whatsapp", key, f"in-{prefix}")
    store.append_message("whatsapp", key, LoggedMessage(direction="in", text=f"Mesaj privat {prefix}", at=moment))
    store.add_gap(KnowledgeGap(channel="whatsapp", key=key, question=f"Intrebare privata {prefix}",
                               query="rezistenta", at=moment))
    store.save_suggestion(Suggestion(
        id=f"sug-{prefix}",
        channel="whatsapp",
        key=key,
        status="linked",
        created_at=moment,
        basis_message_id="m1",
        suggestion=AssistSuggestion(
            suggestion_id=f"sug-{prefix}",
            kind="offer",
            text=f"Oferta privata {prefix}",
            options=["500 buc"],
            image_path=str(out_file),
            note_for_staff=f"Nota privata {prefix}",
            handoff_reason=HandoffReason.VALUE_OVER_THRESHOLD,
            offer_lines=[line],
            can_create_payment_link=False,
            payment_url=f"https://shop.test/pay/{prefix}",
        ),
        quotes=[quote],
        offer_text=f"Oferta privata {prefix}",
        valid_until=moment + timedelta(days=7),
        artwork_url=f"https://cdn.test/{prefix}.png",
        latency_s=4.5,
        outcome="exact",
        linked_by="ana",
        linked_at=moment,
    ))
    store.save_approval(Approval(
        id=f"ap-{prefix}",
        channel="whatsapp",
        key=key,
        status="approved",
        created_at=moment,
        quote=quote,
        lines=[line],
        offer_text=f"Oferta aprobata {prefix}",
        image_path=str(out_file),
        artwork_url=f"https://cdn.test/{prefix}.png",
        valid_until=moment + timedelta(days=7),
        summary=f"Rezumat aprobare {prefix}",
        decided_by="ana",
        decided_at=moment,
        human_changed=False,
    ))
    return inbound_file, out_file


def test_rules_retention_days_loading_and_validation():
    repo_rules = Rules.load()
    assert repo_rules.retention_days == 90
    assert Rules.from_dict({**RULES_DATA, "retention_days": "45"}).retention_days == 45

    undecided = Rules.from_dict({**RULES_DATA, "retention_days": "DECIZIE_DESCHISA"})
    assert undecided.retention_days == "DECIZIE_DESCHISA"

    for invalid in (0, -10, True, False, "90zile", ""):
        with pytest.raises(ValueError, match="retention_days"):
            Rules.from_dict({**RULES_DATA, "retention_days": invalid})


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_purge_refuses_when_retention_is_open_decision_or_invalid(tmp_path, kind):
    store = InMemoryStore() if kind == "memory" else SqliteStore(tmp_path / "c.sqlite3")
    try:
        with pytest.raises(ValueError, match="DECIZIE_DESCHISA"):
            store.purge(NOW, "DECIZIE_DESCHISA", data_dir=tmp_path)
        for bad in (0, -1, True, "abc"):
            with pytest.raises(ValueError):
                store.purge(NOW, bad, data_dir=tmp_path)
    finally:
        if hasattr(store, "close"):
            store.close()


@pytest.mark.parametrize("kind", ["memory", "sqlite"])
def test_purge_deletes_old_pii_and_files_while_keeping_offer_metrics(tmp_path, kind):
    data_dir = tmp_path / "data"
    store = InMemoryStore() if kind == "memory" else SqliteStore(data_dir / "conversations.sqlite3")
    try:
        old_at = NOW - timedelta(days=91)
        new_at = NOW - timedelta(days=10)
        old_in, old_out = _seed(store, data_dir, OLD_KEY, old_at, "vechi")
        new_in, new_out = _seed(store, data_dir, NEW_KEY, new_at, "nou")

        counts = store.purge(NOW, 90, data_dir=data_dir)
        assert counts["messages_deleted"] == 1
        assert counts["gaps_deleted"] == 1
        assert counts["conversations_anonymized"] == 1
        assert counts["suggestions_anonymized"] == 1
        assert counts["approvals_anonymized"] == 1
        assert counts["files_deleted"] >= 2

        anon_key = "anon_" + hashlib.sha256(OLD_KEY.encode("utf-8")).hexdigest()[:24]

        # Conversatia veche nu mai exista sub cheia originala, ci anonimizata fara date personale.
        assert store.load("whatsapp", OLD_KEY) is None
        anon_state = store.load("whatsapp", anon_key)
        assert anon_state is not None
        assert anon_state.contact.name is None and anon_state.contact.phone is None and anon_state.contact.email is None
        assert anon_state.summary == "" and anon_state.design is None and anon_state.mockup_path is None
        assert anon_state.payment_links == {} and anon_state.quotes["q1"].choices.instructions == ""
        assert anon_state.quotes["q1"].total == Decimal("302.50")
        assert store.recent_messages("whatsapp", OLD_KEY, 10) == []
        assert store.recent_messages("whatsapp", anon_key, 10) == []
        assert [g.key for g in store.list_gaps()] == [NEW_KEY]

        # Sugestia si aprobarea veche pastreaza cifrele, statusul si metricile, fara texte/fisiere/cheie.
        sug = store.get_suggestion("sug-vechi")
        assert sug is not None and sug.key == anon_key
        assert sug.offer_text == "" and sug.artwork_url is None and sug.basis_message_id is None
        assert sug.suggestion.text == "" and sug.suggestion.note_for_staff == ""
        assert sug.suggestion.image_path is None and sug.suggestion.payment_url is None
        assert sug.suggestion.kind == "offer"
        assert sug.suggestion.handoff_reason == HandoffReason.VALUE_OVER_THRESHOLD
        assert sug.suggestion.offer_lines[0].total == Decimal("302.50")
        assert sug.quotes[0].total == Decimal("302.50") and sug.quotes[0].choices.instructions == ""
        assert sug.status == "linked" and sug.outcome == "exact" and sug.latency_s == 4.5 and sug.linked_by == "ana"
        assert [s.id for s in store.list_suggestions("whatsapp", anon_key)] == ["sug-vechi"]

        ap = store.get_approval("ap-vechi")
        assert ap is not None and ap.key == anon_key
        assert ap.offer_text == "" and ap.summary == "" and ap.image_path is None and ap.artwork_url is None
        assert ap.quote.total == Decimal("302.50") and ap.lines[0].total == Decimal("302.50")
        assert ap.status == "approved" and ap.decided_by == "ana" and ap.human_changed is False

        # Fisierele vechi sunt sterse; conversatia si fisierele recente raman neatinse.
        assert not old_in.exists() and not old_out.exists()
        assert new_in.exists() and new_out.exists()
        recent = store.load("whatsapp", NEW_KEY)
        assert recent is not None and recent.contact.name == "Client nou"
        assert len(store.recent_messages("whatsapp", NEW_KEY, 10)) == 1

        # A doua rulare la acelasi moment este idempotenta (nu re-hashuieste cheia anonimizata).
        orphan = data_dir / "conversations" / "whatsapp" / "orfan" / "vechi.png"
        orphan.parent.mkdir(parents=True, exist_ok=True)
        orphan.write_bytes(b"\x89PNG\r\n\x1a\n")
        import os as _os
        old_ts = (NOW - timedelta(days=120)).timestamp()
        _os.utime(orphan, (old_ts, old_ts))

        # Testam si apelul implicit purge(now) fara retention_days sau data_dir explicite.
        again = store.purge(NOW, data_dir=data_dir)
        assert again["conversations_anonymized"] == 0
        assert again["files_deleted"] >= 1 and not orphan.exists()
        assert store.load("whatsapp", anon_key) is not None
        assert store.purge(NOW)["conversations_anonymized"] == 0

        # Stergere mesaje vechi cand conversatia nu are ConversationState salvat sau are quote fara instructiuni.
        store.append_message("whatsapp", "doar-mesaj", LoggedMessage(direction="in", text="vechi", at=old_at))
        plain_quote = _quote().model_copy(update={
            "choices": _quote().choices.model_copy(update={"instructions": ""}),
        })
        store.save(ConversationState(
            channel="whatsapp", key=anon_key, contact=Contact(channel="whatsapp", key=anon_key),
            quotes={"q1": plain_quote}, last_message_at=old_at,
        ))
        extra = store.purge(NOW, 90)
        assert extra["messages_deleted"] == 1
        assert store.recent_messages("whatsapp", "doar-mesaj", 5) == []

        # Stergere la cererea clientului pentru conversatia recenta.
        deleted = store.purge_contact("whatsapp", NEW_KEY, data_dir=data_dir)
        assert deleted["conversations_anonymized"] == 1
        assert store.load("whatsapp", NEW_KEY) is None
        assert not new_in.exists() and not new_out.exists()
    finally:
        if hasattr(store, "close"):
            store.close()


def test_privacy_doc_covers_all_story_13_fields_without_em_dashes():
    doc_path = Path(__file__).resolve().parents[2] / "docs" / "privacy.md"
    assert doc_path.is_file()
    text = doc_path.read_text(encoding="utf-8")

    # Sub o pagina, romana clara, fara linii de pauza (em/en dash).
    assert len(text.splitlines()) <= 65
    assert len(text) <= 4500
    assert chr(0x2014) not in text and chr(0x2013) not in text

    required_terms = (
        "/v1/assist/suggest",
        "key",
        "name",
        "id",
        "direction",
        "text",
        "sent_at",
        "quoted_text",
        "attachments",
        "unuploaded_attachments",
        "X-EcQuote-Extension-Version",
        "X-EcQuote-Assist-Token",
        "HTTPS",
        "chrome.storage.local",
        "retention_days",
        "DECIZIE_DESCHISA",
        "Anthropic",
        "EC_QUOTE_ASSIST_TOKENS",
        "purge_contact",
    )
    for term in required_terms:
        assert term in text, f"Lipseste termenul obligatoriu din docs/privacy.md: {term}"
