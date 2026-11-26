from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest

from ec_quote.agent import ApprovalError, SqliteStore
from ec_quote.contracts import AssistEngine, Engine, FileVerdict, HandoffReason, Unpriced

from .fakes import LINE, THURSDAY_10, Harness, call, calls, offer_script, say

REQUEST = "vreau 500 etichete rotunde de 5 cm pentru borcane"
KEY = ("whatsapp", "40700000001")


def test_engine_implements_both_protocols(tmp_path):
    engine = Harness(tmp_path).engine
    for protocol in (AssistEngine, Engine):
        assert all(callable(getattr(engine, name)) for name in vars(protocol) if not name.startswith("_"))


def test_resending_same_transcript_is_idempotent(tmp_path):
    h = Harness(tmp_path, call("ask_customer", text="Ce diametru doriți?", kind="clarify", buttons=["3 cm", "5 cm"]))
    first = h.suggest("vreau etichete rotunde")
    assert first.kind == "question" and first.options == ["3 cm", "5 cm"]
    assert first.text == "Ce diametru doriți?\nVariante: 3 cm, 5 cm."

    again = h.suggest(now=THURSDAY_10 + timedelta(minutes=3))
    assert again == first
    assert len(h.model.calls) == 1
    assert len(h.store.recent_messages(*KEY, 10)) == 1
    assert h.state().questions_asked == 1


def test_staff_message_is_context_and_measures_usefulness(tmp_path):
    h = Harness(tmp_path, say("Bună ziua! Ce dimensiune și ce cantitate doriți?"))
    first = h.suggest("buna ziua")
    assert first.kind == "reply"

    h.say("out", "Bună ziua! Ce dimensiune și ce cantitate doriți?")
    assert h.suggest().kind == "none"            # ultimul mesaj este al nostru
    assert h.state().status == "collecting"      # nu exista mod manual in modul asistat
    assert h.handoff.calls == []

    h.model.add(say("Mulțumim! Revenim imediat cu oferta."))
    second = h.suggest("5 cm, 500 bucati")
    assert second.kind == "reply" and len(h.model.calls) == 2
    turn_text = h.model.calls[1]["messages"][0]["content"][0]["text"]
    assert "[coleg" in turn_text and "Mod asistat" in turn_text
    assert turn_text.count("5 cm, 500 bucati") == 1

    h.say("out", "Multumim, revenim imediat cu oferta dvs.")
    h.model.add(say("Cu plăcere!"))
    h.suggest("ok")
    h.say("out", "Va sunam noi maine.")
    h.suggest()
    metrics = h.engine.assist_metrics(*KEY)
    assert [item["outcome"] for item in metrics["items"]] == ["exact", "edited", "ignored"]
    assert (metrics["suggestions"], metrics["exact"], metrics["edited"], metrics["ignored"]) == (3, 1, 1, 1)
    assert metrics["avg_latency_s"] == 0 and metrics["unanswered"] == 0


def test_empty_transcript_and_last_out_return_none(tmp_path):
    h = Harness(tmp_path)
    assert h.engine.suggest(h.contact(), [], THURSDAY_10).kind == "none"
    h.say("in", "salut")
    h.say("out", "Buna ziua")
    assert h.suggest().kind == "none"
    assert h.model.calls == []


def test_history_first_time_and_out_of_order(tmp_path):
    h = Harness(tmp_path, say("Ce cantitate doriți?"))
    late = h.say("in", "rotunde de 5 cm", at=THURSDAY_10 + timedelta(minutes=5))
    h.say("out", "Buna ziua, cu ce va ajutam?", at=THURSDAY_10 + timedelta(minutes=1))
    h.say("in", "buna, vreau etichete", at=THURSDAY_10)
    suggestion = h.engine.suggest(h.contact(), list(h.transcript) + [late], THURSDAY_10 + timedelta(minutes=6))
    assert suggestion.kind == "reply"
    turn_text = h.model.calls[0]["messages"][0]["content"][0]["text"]
    assert turn_text.index("buna, vreau etichete") < turn_text.index("Buna ziua, cu ce va ajutam?")
    assert turn_text.rstrip().endswith("<mesaj_client>rotunde de 5 cm</mesaj_client>")
    assert h.engine.assist_metrics(*KEY)["items"][0]["latency_s"] == 60


def test_offer_without_link_then_create_payment_link(tmp_path):
    h = Harness(tmp_path, *offer_script(), shadow_mode=True)
    offer = h.suggest(REQUEST, mime="image/png")

    assert offer.kind == "offer" and offer.can_create_payment_link and offer.payment_url is None
    assert "500 buc: 250,00 lei fără TVA (302,50 lei cu TVA)" in offer.text
    assert "pay.example" not in offer.text and "asistentul automat" not in offer.text
    assert offer.image_path.endswith("offer.png")
    assert [line.quantity for line in offer.offer_lines] == [500, 1000, 1500]
    assert h.checkout.calls == [] and h.handoff.calls == []
    assert h.state().status == "collecting"

    linked = h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10 + timedelta(minutes=2))
    assert linked.suggestion_id == offer.suggestion_id and linked.payment_url == "https://pay.example/1"
    assert linked.text.startswith(offer.text) and linked.text.endswith("https://pay.example/1")
    assert linked.can_create_payment_link is False
    assert h.checkout.calls[0][2] == "https://cdn.example/logo.png"
    assert h.state().status == "offer_sent" and h.crm.statuses[-1] == "offer_sent"
    assert h.crm.calls[-1]["checkout"].invoice_url == "https://pay.example/1"

    # Al doilea clic nu creeaza inca o comanda; retrimiterea conversatiei intoarce oferta cu link.
    assert h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10) == linked
    assert len(h.checkout.calls) == 1
    assert h.suggest() == linked

    # Clientul cere din nou linkul: acelasi link, fara alta comanda.
    h.say("out", linked.text)
    h.model.add(call("create_checkout", quote_ids=["q1"], summary="retrimitere"))
    resent = h.suggest("imi mai dati o data linkul?")
    assert resent.kind == "offer" and resent.payment_url == "https://pay.example/1"
    assert "https://pay.example/1" in resent.text and len(h.checkout.calls) == 1
    assert h.engine.assist_metrics(*KEY)["links_created"] == 1


def test_create_payment_link_with_edited_text_and_total_check(tmp_path):
    h = Harness(tmp_path, *offer_script())
    offer = h.suggest(REQUEST)
    h.checkout.total_override = Decimal("1.00")
    with pytest.raises(ApprovalError):
        h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10)
    h.checkout.total_override = None
    linked = h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10, edited_text="Oferta, cum am vorbit.")
    assert linked.text.startswith("Oferta, cum am vorbit.\nLink de plată pentru 500 buc: https://pay.example/")


def test_superseded_expired_and_unknown_suggestions_are_refused(tmp_path):
    h = Harness(tmp_path, *offer_script())
    old = h.suggest(REQUEST)
    h.model.add(call("get_price", **{**LINE, "quantity": 1000}),
                call("create_checkout", quote_ids=["q2"], summary="1000 buc"))
    new = h.suggest("de fapt vreau 1000")
    assert new.kind == "offer" and "1.000 buc: 500,00 lei fără TVA" in new.text

    with pytest.raises(ApprovalError, match="inlocuita"):
        h.engine.create_payment_link(old.suggestion_id, "ana", THURSDAY_10)
    with pytest.raises(ApprovalError, match="necunoscuta"):
        h.engine.create_payment_link("nu-exista", "ana", THURSDAY_10)
    with pytest.raises(ApprovalError, match="expirat"):
        h.engine.create_payment_link(new.suggestion_id, "ana", THURSDAY_10 + timedelta(days=9))
    assert h.checkout.calls == []

    # O sugestie expirata nu mai este intoarsa ca valabila: se reface.
    h.model.add(call("create_checkout", quote_ids=["q2"], summary="1000 buc"))
    refreshed = h.suggest(now=THURSDAY_10 + timedelta(days=9))
    assert refreshed.suggestion_id != new.suggestion_id and refreshed.kind == "offer"

    question = Harness(tmp_path, call("ask_customer", text="Ce cantitate?", kind="clarify"))
    asked = question.suggest("etichete")
    with pytest.raises(ApprovalError, match="nu are o oferta"):
        question.engine.create_payment_link(asked.suggestion_id, "ana", THURSDAY_10)


def test_over_threshold_is_needs_human_with_price_for_staff_only(tmp_path):
    h = Harness(tmp_path, call("get_price", **{**LINE, "quantity": 10000}),
                call("create_checkout", quote_ids=["q1"], summary="x"))
    suggestion = h.suggest("vreau 10000 etichete rotunde de 5 cm")

    assert suggestion.kind == "needs_human"
    assert suggestion.handoff_reason == HandoffReason.VALUE_OVER_THRESHOLD
    assert suggestion.text == ""  # niciun pret propus clientului
    assert "peste pragul de 3.000,00 lei fără TVA" in suggestion.note_for_staff
    assert "5.000,00 lei fără TVA (6.050,00 lei cu TVA)" in suggestion.note_for_staff
    assert suggestion.offer_lines[0].total_ex_vat == Decimal("5000.00")
    assert suggestion.can_create_payment_link is True
    assert len(h.model.calls) == 1 and h.state().quotes == {}
    assert h.handoff.calls == [] and h.state().status == "collecting"

    linked = h.engine.create_payment_link(suggestion.suggestion_id, "ana", THURSDAY_10)
    assert "10.000 buc: 5.000,00 lei fără TVA" in linked.text and linked.payment_url


def test_unpriced_reason_becomes_helpful_suggestion(tmp_path):
    h = Harness(tmp_path, call("get_price", **{**LINE, "quantity": 10}), call("get_price", **{**LINE, "quantity": 25}),
                call("send_price_comparison", quote_ids=["q1"],
                     intro="Comanda minimă este de 25 de bucăți. Prețul pentru această cantitate:"))
    h.pricing.min_quantity = 25
    suggestion = h.suggest("vreau 10 etichete rotunde de 5 cm")
    import json
    fed_back = json.loads(h.model.calls[1]["messages"][-1]["content"][0]["content"])
    assert fed_back["reason"] == "quantity_below_minimum" and "25 buc" in fed_back["hint"]
    assert suggestion.kind == "reply"
    assert suggestion.text.splitlines()[0].startswith("Comanda minimă este de 25")
    assert "12,50 lei fără TVA (15,12 lei cu TVA), 0,60 lei/buc cu TVA" in suggestion.text

    h2 = Harness(tmp_path, call("get_price", **LINE), call("handoff", reason="not_in_calculator", summary="fara pret"))
    h2.pricing.unpriced = Unpriced(reason="no_price")
    blocked = h2.suggest("etichete speciale")
    assert blocked.kind == "needs_human" and blocked.handoff_reason == HandoffReason.NOT_IN_CALCULATOR
    assert "nu există în calculator" in blocked.note_for_staff and "fara pret" in blocked.note_for_staff


def test_explicit_human_and_robot_questions_are_decided_by_code(tmp_path):
    h = Harness(tmp_path)
    human = h.suggest("Vreau să vorbesc cu un om, vă rog")
    assert human.kind == "needs_human" and human.handoff_reason == HandoffReason.CUSTOMER_ASKED
    assert "a cerut explicit" in human.note_for_staff and "09:00" not in human.text + human.note_for_staff
    robot = Harness(tmp_path).suggest("vorbesc cu un robot?")
    assert robot.kind == "needs_human" and "robot" in robot.note_for_staff and robot.text == ""
    assert h.model.calls == [] and h.handoff.calls == []
    # "ai" din romana nu este o intrebare despre inteligenta artificiala.
    plain = Harness(tmp_path, say("Da, avem. Ce dimensiune doriți?"))
    assert plain.suggest("ai etichete rotunde?").kind == "reply"


def test_price_guard_is_as_strict_in_assisted_mode(tmp_path):
    h = Harness(tmp_path, say("Costă cam 199 lei."), say("Vă pregătim imediat oferta exactă."))
    suggestion = h.suggest(REQUEST)
    assert suggestion.kind == "reply" and suggestion.text == "Vă pregătim imediat oferta exactă."

    stubborn = Harness(tmp_path, say("Costă 199 lei."), say("Costă 150 RON."), say("Vă facem 15% reducere."))
    blocked = stubborn.suggest(REQUEST)
    assert blocked.kind == "needs_human" and blocked.handoff_reason == HandoffReason.NOT_UNDERSTOOD
    assert "lei" not in blocked.text and "Verificările au blocat textul" in blocked.note_for_staff

    question = Harness(tmp_path, call("ask_customer", text="Doriți varianta de 50 lei?", kind="clarify"),
                       call("send_price_comparison", quote_ids=["q9"]),
                       call("ask_customer", text="Ce dimensiune doriți?", kind="clarify"))
    assert question.suggest("etichete").text == "Ce dimensiune doriți?"


def test_question_cap_is_guidance_not_a_stop(tmp_path):
    h = Harness(tmp_path, max_clarifying_questions=1)
    h.model.add(call("ask_customer", text="Ce formă doriți?", kind="clarify"))
    assert h.suggest("etichete").note_for_staff == ""
    h.model.add(call("ask_customer", text="Ce dimensiune doriți?", kind="clarify"))
    second = h.suggest("rotunde")
    assert second.kind == "question" and second.text == "Ce dimensiune doriți?"
    assert "S-au pus deja 1 întrebări de clarificare" in second.note_for_staff

    h.model.add(call("ask_customer", text="Îmi puteți spune ce doriți?", kind="not_understood"))
    assert "nu a înțeles" in h.suggest("asdf").note_for_staff
    h.model.add(call("ask_customer", text="Puteți reformula?", kind="not_understood"))
    last = h.suggest("qwer")
    assert last.kind == "needs_human" and last.text == "Puteți reformula?"


def test_weak_and_unusable_files(tmp_path):
    h = Harness(tmp_path, call("check_file", width_cm=5, height_cm=5), *offer_script())
    h.files.verdict = FileVerdict.WEAK
    weak = h.suggest(REQUEST, mime="image/jpeg", filename="poza.jpg")
    assert weak.kind == "offer" and "Notă: fișierul trimis se poate tipări" in weak.text
    assert "Fișierul clientului: calitate slabă, se poate tipări (low_dpi)." in weak.note_for_staff


def test_unusable_file_becomes_needs_human_with_draft(tmp_path):
    h = Harness(tmp_path, call("check_file", width_cm=5, height_cm=5),
                call("ask_customer", text="Ne puteți trimite logoul în format vectorial, ca document?", kind="file"))
    h.files.verdict = FileVerdict.UNUSABLE
    first = h.suggest(REQUEST, mime="image/png", filename="mic.png")
    assert first.kind == "question" and "inutilizabil la tipar" in first.note_for_staff
    assert h.state().questions_asked == 0

    h.model.add(call("check_file", width_cm=5, height_cm=5))
    second = h.suggest("poftim altul", mime="image/png", filename="mic2.png")
    assert second.kind == "needs_human" and second.handoff_reason == HandoffReason.FILE_UNUSABLE
    assert second.text.startswith("Fișierul trimis nu poate fi folosit")
    assert "după 2 încercări" in second.note_for_staff


def test_voice_and_unsupported_attachments(tmp_path):
    h = Harness(tmp_path)
    voice = h.suggest(mime="audio/ogg", filename="ptt.ogg")
    assert voice.kind == "question" and "mesajele vocale" in voice.text and "mesaj vocal" in voice.note_for_staff
    video = Harness(tmp_path).suggest(mime="video/mp4", filename="clip.mp4")
    assert "PDF, AI, SVG" in video.text
    assert h.model.calls == [] and h.state().design is None
    # Acelasi comportament in modul autonom.
    from ec_quote.contracts import Attachment, Contact, InboundMessage
    site = Harness(tmp_path)
    actions = site.engine.handle(InboundMessage(
        contact=Contact(channel="site", key="s1"), received_at=THURSDAY_10,
        attachments=[Attachment(path="/tmp/a.ogg", mime="audio/ogg")]))
    assert "mesajele vocale" in actions[0].text


def test_knowledge_answer_is_traceable_to_returned_entries(tmp_path):
    h = Harness(tmp_path, call("search_knowledge", query="rezista la apa", product_or_material="Vinyl alb"),
                say("Da, etichetele din vinyl rezistă la apă și la umezeală."))
    answer = h.suggest("rezista la apa?")
    assert answer.kind == "reply" and "rezistă la apă" in answer.text
    assert h.knowledge.queries == ["rezista la apa Vinyl alb"]
    entries = h.model.calls[1]["messages"][-1]["content"][0]["content"]
    assert '"id": "k1"' in entries and "k3" not in entries
    assert "Subiecte in baza de cunostinte: livrare, rezistenta." in h.model.calls[0]["messages"][0]["content"][0]["text"]

    # O categorie care nu apare in intrarile intoarse este blocata, chiar daca s-a cautat.
    h2 = Harness(tmp_path, call("search_knowledge", query="rezista la apa"),
                 say("Da, rezistă la apă, la soare și la congelator."), say("Da, etichetele din vinyl rezistă la apă."))
    assert h2.suggest("rezista?").text == "Da, etichetele din vinyl rezistă la apă."
    assert "soare, congelator" in h2.model.calls[2]["messages"][-1]["content"][0]["text"]

    # Sumele si termenele din intrare pot fi repetate; altele nu.
    h3 = Harness(tmp_path, call("search_knowledge", query="livrarea dureaza"),
                 say("Livrarea durează 1-2 zile lucrătoare, iar transportul costă 25 lei."),
                 say("Livrarea durează 1-2 zile lucrătoare, iar transportul costă 20 lei."))
    assert "20 lei" in h3.suggest("cat costa livrarea?").text


def test_knowledge_miss_is_recorded_and_needs_human(tmp_path):
    h = Harness(tmp_path, call("search_knowledge", query="microunde"), say("Verificăm și revenim."))
    miss = h.suggest("se pot pune la microunde?", now=THURSDAY_10)
    assert miss.kind == "needs_human"
    assert miss.note_for_staff == "Nu avem un răspuns aprobat pentru: se pot pune la microunde?"
    assert miss.text == "Verificăm acest detaliu și revenim imediat cu un răspuns."
    gaps = h.engine.knowledge_gaps()
    assert [(g.question, g.query) for g in gaps] == [("se pot pune la microunde?", "microunde")]
    assert h.engine.knowledge_gaps(THURSDAY_10 + timedelta(hours=1)) == []

    # Oferta merge mai departe; intrebarea ramasa fara raspuns apare in nota pentru om.
    h.model.add(call("search_knowledge", query="congelator"), *offer_script())
    mixed = h.suggest("ok. 500 etichete rotunde 5 cm, rezista la congelator?")
    assert mixed.kind == "offer" and "Nu avem un răspuns aprobat pentru: ok. 500 etichete" in mixed.note_for_staff
    assert len(h.engine.knowledge_gaps()) == 2

    # Fara baza de cunostinte configurata, cautarea este tot o lipsa; in modul autonom merge la om.
    site = Harness(tmp_path, call("search_knowledge", query="microunde"), say("Verificăm."))
    site.engine.knowledge = None
    actions = site.send("merge la microunde?")
    assert actions[0].handoff_reason == HandoffReason.NOT_UNDERSTOOD
    assert "Nu avem un răspuns aprobat" in site.handoff.calls[0][2]


def test_comparisons_tiers_options_and_promo(tmp_path):
    h = Harness(tmp_path, calls(("get_price", {**LINE, "quantity": 100}), ("get_price", LINE),
                                ("get_price", {**LINE, "urgent": True})),
                call("send_price_comparison", quote_ids=["q1", "q2", "q3"], intro="Iată variantele:",
                     closing="Pe care o preferați?", include_tiers=True))
    h.pricing.promo_percent = 5
    reply = h.suggest("cat costa 100 si 500, si cu urgenta?")
    rows = reply.text.splitlines()
    assert rows[0] == "Iată variantele:" and rows[-1] == "Pe care o preferați?"
    assert rows[1] == "Etichete autocolante, Rotund, 5 x 5 cm, Vinyl alb:"
    assert rows[2] == "1. 100 buc: 50,00 lei fără TVA (60,50 lei cu TVA), 0,60 lei/buc cu TVA"
    assert rows[3] == "Prețul include promoția activă de 5%."
    assert rows[6].startswith("3. 500 buc, regim de urgență: 375,00 lei fără TVA (453,75 lei cu TVA)")
    assert "Cantități mai mari:" in rows and "- 200 buc: 100,00 lei fără TVA (121,00 lei cu TVA), 0,60 lei/buc cu TVA" in rows
    assert reply.kind == "reply" and len(reply.offer_lines) == 3 and not reply.can_create_payment_link
    assert h.pricing.tier_calls[0][0].quantity == 100

    # Acelasi instrument in modul autonom trimite textul direct.
    site = Harness(tmp_path, call("get_price", **LINE), call("send_price_comparison", quote_ids=["q1"]))
    assert site.send("pret cu tva?")[0].text.startswith("500 buc, Etichete autocolante")


def test_multi_product_offer_sums_with_decimal_and_has_no_auto_link(tmp_path):
    second = {"product_id": "gid://shopify/Product/2", "material_name": "Vinyl alb", "shape": "Contur",
              "width_cm": 6, "height_cm": 6, "quantity": 100}
    script = [calls(("get_price", LINE), ("get_price", second)),
              call("create_checkout", quote_ids=["q1", "q2"], summary="etichete si stickere")]
    h = Harness(tmp_path, *script)
    offer = h.suggest("500 etichete rotunde 5 cm si 100 stickere contur 6 cm")
    assert offer.kind == "offer" and len(offer.offer_lines) == 2 and offer.can_create_payment_link is False
    assert "1. 500 buc, Etichete autocolante, Rotund, 5 x 5 cm, Vinyl alb: 250,00 lei fără TVA" in offer.text
    assert "Total: 300,00 lei fără TVA (363,00 lei cu TVA)" in offer.text
    assert "manual" in offer.note_for_staff
    with pytest.raises(ApprovalError):
        h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10)

    # Suma liniilor peste prag: decide codul.
    h.pricing.unit = Decimal("4.00")
    h.model.add(*[calls(("get_price", LINE), ("get_price", {**second, "quantity": 300})),
                  call("create_checkout", quote_ids=["q3", "q4"], summary="mai mult")])
    big = h.suggest("de fapt mai multe")
    assert big.kind == "needs_human" and big.handoff_reason == HandoffReason.VALUE_OVER_THRESHOLD
    assert "Total calculator: 3.200,00 lei fără TVA" in big.note_for_staff and big.can_create_payment_link is False

    site = Harness(tmp_path, *script)
    assert site.send("doua produse")[0].handoff_reason == HandoffReason.SPECIAL_TERMS


def test_discount_request_shows_calculator_price_to_staff(tmp_path):
    h = Harness(tmp_path, *offer_script())
    h.suggest(REQUEST)
    h.model.add(call("handoff", reason="special_terms", summary="cere 15% discount"))
    asked = h.suggest("imi faceti un discount?")
    assert asked.kind == "needs_human" and asked.handoff_reason == HandoffReason.SPECIAL_TERMS
    assert "Preț calculator pentru 500 buc: 250,00 lei fără TVA (302,50 lei cu TVA)." in asked.note_for_staff
    assert "cere 15% discount" in asked.note_for_staff and "lei" not in asked.text


def test_other_languages_and_no_reply(tmp_path):
    h = Harness(tmp_path, call("get_price", **LINE),
                call("create_checkout", quote_ids=["q1"], summary="500 labels", language="en"))
    offer = h.suggest("How much for 500 round labels 5 cm?")
    assert "Your quote:" in offer.text and "500 pcs: 250,00 lei excl. VAT (302,50 lei incl. VAT)" in offer.text
    linked = h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10)
    assert "Payment link for 500 pcs: https://pay.example/1" in linked.text

    hu = Harness(tmp_path, call("get_price", **LINE),
                 call("send_price_comparison", quote_ids=["q1"], language="hu"))
    assert "lej ÁFA nélkül" in hu.suggest("Mennyibe kerül 500 db?").text

    spam = Harness(tmp_path, call("no_reply", reason="spam"))
    nothing = spam.suggest("castiga bani rapid")
    assert nothing.kind == "none" and "spam" in nothing.note_for_staff
    site = Harness(tmp_path, call("no_reply", reason="spam"))
    assert site.send("castiga bani rapid") == []


def test_daily_cap_and_technical_failures_become_notes(tmp_path):
    h = Harness(tmp_path, *offer_script(), max_offers_per_contact_per_day=1)
    h.suggest(REQUEST)
    h.model.add(call("get_price", **{**LINE, "quantity": 600}), call("create_checkout", quote_ids=["q2"], summary="s"))
    capped = h.suggest("si pentru 600?")
    assert capped.kind == "needs_human" and capped.handoff_reason == HandoffReason.OFFER_LIMIT
    assert "numărul maxim de oferte" in capped.note_for_staff

    down = Harness(tmp_path)
    down.pricing.fail_catalog = True
    assert "catalogul calculatorului este indisponibil" in down.suggest("salut").note_for_staff
    broken = Harness(tmp_path, RuntimeError("api jos"))
    assert broken.suggest("salut").kind == "needs_human"
    refused = Harness(tmp_path)
    from ec_quote.agent import ModelReply
    refused.model.add(ModelReply(stop_reason="refusal"))
    assert refused.suggest("salut").kind == "needs_human"


def test_assisted_flow_on_sqlite(tmp_path):
    store = SqliteStore(tmp_path / "db" / "c.sqlite3")
    h = Harness(tmp_path, call("search_knowledge", query="microunde"), *offer_script(), store=store)
    offer = h.suggest(REQUEST)
    assert h.suggest() == offer
    linked = h.engine.create_payment_link(offer.suggestion_id, "ana", THURSDAY_10)
    assert store.get_suggestion(offer.suggestion_id).status == "linked"
    assert store.get_suggestion("x") is None
    assert [s.suggestion for s in store.list_suggestions(*KEY)] == [linked]
    assert len(store.list_gaps()) == 1 and store.list_gaps(THURSDAY_10 + timedelta(days=1)) == []
    store.close()
