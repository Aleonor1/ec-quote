"""Teste pentru story-25: metrici pure de utilizare a sugestiilor."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from ec_quote.agent.store import InMemoryStore, LoggedMessage, Suggestion
from ec_quote.contracts import AssistSuggestion, FileVerdict, HandoffReason
from ec_quote.metrics import (
    DEFAULT_SIMILARITY_THRESHOLD,
    TZ,
    Outcome,
    SuggestionMetricRow,
    UsageMetricsConfig,
    classify_row_outcome,
    classify_text_outcome,
    compute_usage_metrics,
    normalize_whitespace,
    offer_amounts_changed,
    rows_from_store,
    text_similarity,
    to_bucharest,
)

BASE_CONFIG = UsageMetricsConfig(
    input_price_per_million=Decimal("15.00"),
    output_price_per_million=Decimal("75.00"),
    monthly_cost_ceiling=Decimal("10.00"),
    similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD,
)

OFFER_SAMPLE = (
    "Oferta dumneavoastră: Stickere Personalizate, circle, 5 x 5 cm, Vinil Alb Lucios.\n"
    "100 buc: 169,42 lei fără TVA (205,00 lei cu TVA)\n"
    "Alte cantități:\n"
    "- 200 buc: 297,52 lei fără TVA (360,00 lei cu TVA)\n"
    "Termen de producție: 2-4 zile lucrătoare.\n"
    "Ofertă valabilă până la 10.11.2026."
)


# ---------- AC4: 20 de perechi pe masura de similaritate si pragul unic ----------

SIMILARITY_20_PAIRS: list[tuple[str, str, str, Outcome]] = [
    # 1-4: neschimbate (identice sau doar spatii / linii noi diferite)
    (
        "identic_simplu",
        "Bună ziua! Cu ce dimensiune și cantitate vă putem ajuta?",
        "Bună ziua! Cu ce dimensiune și cantitate vă putem ajuta?",
        "unchanged",
    ),
    (
        "spatii_multiple",
        "Bună ziua!   Trimiteți grafica în PDF sau PNG.",
        "Bună ziua! Trimiteți grafica în PDF sau PNG.",
        "unchanged",
    ),
    (
        "linii_noi_normalizate",
        "Oferta dumneavoastră:\n\n100 buc: 205,00 lei cu TVA.",
        "Oferta dumneavoastră: 100 buc: 205,00 lei cu TVA.",
        "unchanged",
    ),
    (
        "spatii_capete",
        "  Mulțumim! Am primit fișierul vectorial.  ",
        "Mulțumim! Am primit fișierul vectorial.",
        "unchanged",
    ),
    # 5-8: greseala de tastare / diacritice / punctuatie reparata -> edited
    (
        "typo_cuvant",
        "Vă putem pregăti stickere rotunde de 5 x 5 cmm pe vinil alb lucios.",
        "Vă putem pregăti stickere rotunde de 5 x 5 cm pe vinil alb lucios.",
        "edited",
    ),
    (
        "diacritice_adaugate",
        "Buna ziua! Ce cantitate doriti pentru etichetele pe rola?",
        "Bună ziua! Ce cantitate doriți pentru etichetele pe rolă?",
        "edited",
    ),
    (
        "punctuatie_ajustata",
        "Putem tipări pe vinil transparent, aveți fișierul în format PDF?",
        "Putem tipări pe vinil transparent. Aveți fișierul în format PDF?",
        "edited",
    ),
    (
        "litera_mare_corectata",
        "vinilul alb mat rezistă la apă și la exterior.",
        "Vinilul alb mat rezistă la apă și la exterior.",
        "edited",
    ),
    # 9-12: formula de salut sau semnatura adaugata -> edited
    (
        "salut_adaugat_la_oferta",
        OFFER_SAMPLE,
        "Bună ziua!\n" + OFFER_SAMPLE,
        "edited",
    ),
    (
        "multumire_adaugata_la_final",
        "Pentru 100 buc de 5 x 5 cm avem nevoie de fișierul grafic în PDF sau SVG.",
        "Pentru 100 buc de 5 x 5 cm avem nevoie de fișierul grafic în PDF sau SVG. Mulțumim!",
        "edited",
    ),
    (
        "nume_client_adaugat",
        "Ne puteți confirma dacă doriți laminare mată sau lucioasă?",
        "Salut Andrei, ne puteți confirma dacă doriți laminare mată sau lucioasă?",
        "edited",
    ),
    (
        "inchidere_scurta_adaugata",
        OFFER_SAMPLE,
        OFFER_SAMPLE + "\nSpuneți-ne dacă doriți linkul de plată.",
        "edited",
    ),
    # 13-15: o linie de pret / cantitate scoasa din oferta -> edited
    (
        "linie_treapta_scoasa",
        OFFER_SAMPLE,
        (
            "Oferta dumneavoastră: Stickere Personalizate, circle, 5 x 5 cm, Vinil Alb Lucios.\n"
            "100 buc: 169,42 lei fără TVA (205,00 lei cu TVA)\n"
            "Termen de producție: 2-4 zile lucrătoare.\n"
            "Ofertă valabilă până la 10.11.2026."
        ),
        "edited",
    ),
    (
        "valabilitate_reformulata",
        OFFER_SAMPLE,
        OFFER_SAMPLE.replace("Ofertă valabilă până la 10.11.2026.", "Valabilă 7 zile."),
        "edited",
    ),
    (
        "suma_modificata_in_oferta",
        OFFER_SAMPLE,
        OFFER_SAMPLE.replace("205,00 lei cu TVA", "195,00 lei cu TVA"),
        "edited",
    ),
    # 16-20: raspuns complet diferit -> ignored
    (
        "apel_telefonic_in_loc_de_oferta",
        OFFER_SAMPLE,
        "Vă sun imediat să discutăm detaliile comenzii.",
        "ignored",
    ),
    (
        "intrebare_diferita_despre_adresa",
        "Ce dimensiune în centimetri doriți pentru stickerele rotunde?",
        "Îmi puteți lăsa adresa completă de livrare și CUI-ul firmei pentru factură?",
        "ignored",
    ),
    (
        "refuz_produs_inexistent",
        OFFER_SAMPLE,
        "Nu realizăm bannere stradale de 6 metri, doar etichete și stickere.",
        "ignored",
    ),
    (
        "confirmare_scurta_fara_legatura",
        "Pentru această dimensiune rezoluția fișierului este sub nivelul recomandat; aveți PDF vectorial?",
        "Am notat, pachetul pleacă astăzi prin curier.",
        "ignored",
    ),
    (
        "mesaj_gol_sau_simbol",
        "Cu ce cantitate doriți să începem oferta?",
        "Ok",
        "ignored",
    ),
]


def test_20_similarity_pairs_and_configurable_threshold():
    assert len(SIMILARITY_20_PAIRS) == 20
    for case_name, suggested, sent, expected_outcome in SIMILARITY_20_PAIRS:
        actual = classify_text_outcome(suggested, sent, similarity_threshold=DEFAULT_SIMILARITY_THRESHOLD)
        assert actual == expected_outcome, f"Esec pe perechea {case_name}: asteptat {expected_outcome}, primit {actual}"

    # Pragul este configurabil, nu o constanta ascunsa in comparatie.
    s1 = "Avem nevoie de dimensiunea în cm și cantitatea dorită."
    s2 = "Bună! Avem nevoie de dimensiunea în cm pentru comandă."
    ratio = text_similarity(s1, s2)
    assert 0.5 < ratio < 0.9
    assert classify_text_outcome(s1, s2, similarity_threshold=ratio - 0.01) == "edited"
    assert classify_text_outcome(s1, s2, similarity_threshold=min(ratio + 0.05, 0.99)) == "ignored"


def test_similarity_and_amount_helpers_edge_cases():
    assert text_similarity("", "") == 1.0
    assert text_similarity("ceva", "") == 0.0
    assert normalize_whitespace(" a\n\t b  c ") == "a b c"
    with pytest.raises(ValueError):
        classify_text_outcome("a", "b", similarity_threshold=0.0)
    with pytest.raises(ValueError):
        classify_text_outcome("a", "b", similarity_threshold=1.5)

    # AC5: amounts_changed detecteaza sume lipsa, sume schimbate si sume pastrate intact.
    assert not offer_amounts_changed(OFFER_SAMPLE, "Bună ziua!\n" + OFFER_SAMPLE)
    assert offer_amounts_changed(OFFER_SAMPLE, OFFER_SAMPLE.replace("- 200 buc: 297,52 lei fără TVA (360,00 lei cu TVA)\n", ""))
    assert offer_amounts_changed(OFFER_SAMPLE, OFFER_SAMPLE.replace("205,00 lei", "195,00 lei"))

    # AC6: needs_human si none nu devin niciodata ignored, chiar daca au text draft sau sunt inlocuite.
    nh = SuggestionMetricRow(
        suggestion_id="s-nh",
        kind="needs_human",
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=TZ),
        suggestion_text="Ne pare rău pentru situația creată.",
        replaced_by_newer=True,
        handoff_reason=HandoffReason.COMPLAINT,
    )
    assert classify_row_outcome(nh) is None

    empty_reply = SuggestionMetricRow(
        suggestion_id="s-empty",
        kind="reply",
        created_at=datetime(2026, 11, 2, 10, 0, tzinfo=TZ),
        suggestion_text="   ",
    )
    assert classify_row_outcome(empty_reply) is None


# ---------- Fixture determinista de 40 de conversatii (AC1..AC10) ----------

def _build_40_conversations_fixture() -> list[SuggestionMetricRow]:
    """Construieste 40 de conversatii in perioada [2026-11-01, 2026-11-11) + 2 in afara perioadei."""
    base_day = datetime(2026, 11, 1, 10, 0, tzinfo=TZ)

    # Distributie exacta a timpilor pana la sugestie pe cele 38 de sugestii non-none:
    # [5]*4 (cu sent_at lipsa) + [15]*8 + [45]*8 + [120]*5 + [240]*5 + [420]*4 + [900]*4 = 38 valori
    tts_schedule: list[tuple[float, bool]] = (
        [(5.0, True)] * 4
        + [(15.0, False)] * 8
        + [(45.0, False)] * 8
        + [(120.0, False)] * 5
        + [(240.0, False)] * 5
        + [(420.0, False)] * 4
        + [(900.0, False)] * 4
    )
    assert len(tts_schedule) == 38

    # Latente backend pe cele 40 de conversatii: [1.2]*20 + [2.5]*16 + [6.0]*4 = 40 valori
    backend_schedule: list[float] = [1.2] * 20 + [2.5] * 16 + [6.0] * 4
    assert len(backend_schedule) == 40

    specs: list[dict] = []

    # 14 oferte: 5 unchanged, 6 edited (4 fara schimbare sume, 2 cu schimbare sume), 2 ignored, 1 pending
    for i in range(5):
        specs.append({
            "kind": "offer",
            "suggestion_text": OFFER_SAMPLE,
            "next_outgoing_text": OFFER_SAMPLE if i % 2 == 0 else OFFER_SAMPLE.replace("\n", "  "),
            "payment_link_created": True,
            "file_verdict": FileVerdict.OK,
        })
    for i in range(4):
        specs.append({
            "kind": "offer",
            "suggestion_text": OFFER_SAMPLE,
            "next_outgoing_text": "Bună ziua!\n" + OFFER_SAMPLE,
            "file_verdict": FileVerdict.OK if i < 3 else FileVerdict.WEAK,
        })
    specs.append({
        "kind": "offer",
        "suggestion_text": OFFER_SAMPLE,
        "next_outgoing_text": OFFER_SAMPLE.replace("- 200 buc: 297,52 lei fără TVA (360,00 lei cu TVA)\n", ""),
        "file_verdict": FileVerdict.WEAK,
    })
    specs.append({
        "kind": "offer",
        "suggestion_text": OFFER_SAMPLE,
        "next_outgoing_text": OFFER_SAMPLE.replace("205,00 lei cu TVA", "195,00 lei cu TVA"),
        "file_verdict": FileVerdict.WEAK,
    })
    for _ in range(2):
        specs.append({
            "kind": "offer",
            "suggestion_text": OFFER_SAMPLE,
            "next_outgoing_text": "Vă sun imediat să stabilim detaliile pe telefon.",
        })
    specs.append({
        "kind": "offer",
        "suggestion_text": OFFER_SAMPLE,
        "next_outgoing_text": None,
        "replaced_by_newer": False,
    })

    # 10 reply: 4 unchanged, 2 edited, 2 ignored (superseded), 2 pending
    reply_txt = "Vinilul alb lucios este rezistent la umezeală și ulei, potrivit pentru ambalaje."
    for _ in range(4):
        specs.append({"kind": "reply", "suggestion_text": reply_txt, "next_outgoing_text": reply_txt})
    for _ in range(2):
        specs.append({"kind": "reply", "suggestion_text": reply_txt, "next_outgoing_text": "Bună! " + reply_txt})
    for _ in range(2):
        specs.append({
            "kind": "reply",
            "suggestion_text": reply_txt,
            "next_outgoing_text": None,
            "replaced_by_newer": True,
            "guard_rejections": ("claim",),
        })
    for _ in range(2):
        specs.append({"kind": "reply", "suggestion_text": reply_txt, "next_outgoing_text": None})

    # 8 question: 3 unchanged, 2 edited, 2 ignored, 1 pending
    q_txt = "Ce dimensiune în cm și ce cantitate doriți pentru stickere?"
    for _ in range(3):
        specs.append({"kind": "question", "suggestion_text": q_txt, "next_outgoing_text": q_txt})
    for _ in range(2):
        specs.append({"kind": "question", "suggestion_text": q_txt, "next_outgoing_text": "Salut! " + q_txt})
    for _ in range(2):
        specs.append({
            "kind": "question",
            "suggestion_text": q_txt,
            "next_outgoing_text": "Trimiteți CUI-ul pentru factură.",
            "guard_rejections": ("amount",),
        })
    specs.append({
        "kind": "question",
        "suggestion_text": q_txt,
        "next_outgoing_text": None,
        "guard_rejections": ("claim", "duration"),
    })

    # 6 needs_human: 2 not_in_calculator, 1 value_over_threshold, 1 complaint, 1 file_unusable, 1 customer_asked
    nh_reasons = [
        (HandoffReason.NOT_IN_CALCULATOR, 1, None),
        (HandoffReason.NOT_IN_CALCULATOR, 1, None),
        (HandoffReason.VALUE_OVER_THRESHOLD, 0, None),
        (HandoffReason.COMPLAINT, 0, None),
        (HandoffReason.FILE_UNUSABLE, 0, FileVerdict.UNUSABLE),
        (HandoffReason.CUSTOMER_ASKED, 0, FileVerdict.UNUSABLE),
    ]
    for reason, calc_fail, f_verdict in nh_reasons:
        specs.append({
            "kind": "needs_human",
            "suggestion_text": "Ne pare rău pentru situație." if reason == HandoffReason.COMPLAINT else "",
            "handoff_reason": reason,
            "calculator_failures": calc_fail,
            "file_verdict": f_verdict,
            "replaced_by_newer": True,
        })

    # 2 none
    for _ in range(2):
        specs.append({"kind": "none", "suggestion_text": ""})

    assert len(specs) == 40

    rows: list[SuggestionMetricRow] = []
    tts_iter = iter(tts_schedule)
    for idx, spec in enumerate(specs, start=1):
        created_at = base_day + timedelta(hours=idx * 5)
        b_lat = backend_schedule[idx - 1]
        staff = "ana" if idx <= 25 else "mihai"

        if spec["kind"] != "none":
            delta_s, is_missing = next(tts_iter)
            if is_missing:
                cust_sent = None
                first_seen = created_at - timedelta(seconds=delta_s)
            else:
                cust_sent = created_at - timedelta(seconds=delta_s)
                first_seen = cust_sent + timedelta(seconds=1)
        else:
            cust_sent = None
            first_seen = None

        # Folosim request/response timestamps pe jumatate din randuri si backend_latency_s pe cealalta.
        if idx % 2 == 0:
            req_at = created_at - timedelta(seconds=b_lat)
            resp_at = created_at
            direct_lat = None
        else:
            req_at = None
            resp_at = None
            direct_lat = b_lat

        # Cateva timestamp-uri in UTC pentru a verifica conversia la Europe/Bucharest.
        created_final = created_at.astimezone(timezone.utc) if idx % 5 == 0 else created_at

        rows.append(
            SuggestionMetricRow(
                suggestion_id=f"sug-{idx:02d}",
                conversation_key=f"whatsapp:4070000{idx:04d}",
                kind=spec["kind"],
                created_at=created_final,
                customer_sent_at=cust_sent,
                first_seen_at=first_seen,
                backend_latency_s=direct_lat,
                request_received_at=req_at,
                response_sent_at=resp_at,
                suggestion_text=spec.get("suggestion_text", ""),
                next_outgoing_text=spec.get("next_outgoing_text"),
                replaced_by_newer=spec.get("replaced_by_newer", False),
                handoff_reason=spec.get("handoff_reason"),
                requested_by=staff,
                payment_link_created=spec.get("payment_link_created", False),
                guard_rejections=spec.get("guard_rejections", ()),
                calculator_failures=spec.get("calculator_failures", 0),
                file_verdict=spec.get("file_verdict"),
                input_tokens=2500,
                output_tokens=500,
            )
        )

    # 2 randuri in afara ferestrei [2026-11-01 00:00, 2026-11-11 00:00):
    rows.append(
        SuggestionMetricRow(
            suggestion_id="sug-before",
            conversation_key="whatsapp:40700009991",
            kind="reply",
            created_at=datetime(2026, 10, 31, 23, 59, 59, tzinfo=TZ),
            customer_sent_at=datetime(2026, 10, 31, 23, 59, 50, tzinfo=TZ),
            suggestion_text="In afara perioadei",
            requested_by="ana",
            input_tokens=99999,
            output_tokens=99999,
        )
    )
    rows.append(
        SuggestionMetricRow(
            suggestion_id="sug-on-end",
            conversation_key="whatsapp:40700009992",
            kind="reply",
            created_at=datetime(2026, 11, 11, 0, 0, 0, tzinfo=TZ),
            customer_sent_at=datetime(2026, 11, 10, 23, 59, 50, tzinfo=TZ),
            suggestion_text="Chiar pe capatul deschis period_end",
            requested_by="mihai",
            payment_link_created=True,
            input_tokens=99999,
            output_tokens=99999,
        )
    )
    return rows


def test_40_conversations_fixture_pins_every_aggregate():
    rows = _build_40_conversations_fixture()
    period_start = datetime(2026, 11, 1, 0, 0, tzinfo=TZ)
    period_end = datetime(2026, 11, 11, 0, 0, tzinfo=TZ)  # exact 10 zile din 30 in noiembrie 2026

    report = compute_usage_metrics(rows, period_start, period_end, BASE_CONFIG)

    assert report.total_suggestions == 40
    assert len(report.classified_rows) == 40

    # AC1: timp pana la sugestie pe cele 38 de sugestii efective (fara `none`).
    tts = report.time_to_suggestion
    assert tts.count == 38
    assert tts.missing_sent_at_count == 4
    assert tts.median_s == 45.0
    assert tts.p90_s == 900.0
    assert tts.share_under_60s == pytest.approx(20 / 38)
    assert tts.share_under_300s == pytest.approx(30 / 38)

    # AC2: latenta backend separata.
    bl = report.backend_latency
    assert bl.count == 40
    assert bl.median_s == pytest.approx(1.85)
    assert bl.p90_s == pytest.approx(2.5)
    assert bl.max_s == pytest.approx(6.0)

    # AC3, AC5, AC6, AC8: distributia pe tipuri, rezultate, handoff, sume modificate, garda, fisiere.
    assert report.suggestions_by_kind == {
        "reply": 10,
        "question": 8,
        "offer": 14,
        "needs_human": 6,
        "none": 2,
    }
    assert report.outcomes == {
        "unchanged": 12,
        "edited": 10,
        "ignored": 6,
        "pending": 4,
    }
    assert report.needs_human_by_reason == {
        "complaint": 1,
        "customer_asked": 1,
        "file_unusable": 1,
        "not_in_calculator": 2,
        "value_over_threshold": 1,
    }
    assert report.offers_suggested == 14
    assert report.edited_offers_amounts_changed == 2
    assert report.payment_links_created == 5
    assert report.guard_rejections_by_rule == {"amount": 2, "claim": 3, "duration": 1}
    assert report.calculator_failures == 2
    assert report.file_verdicts_by_level == {"ok": 8, "unusable": 2, "weak": 3}

    # AC7: defalcarea pe persoana contine numai numarul de sugestii cerute, fara rezultate pe om.
    assert report.requests_by_staff == {"ana": 25, "mihai": 15}
    assert not hasattr(report, "outcomes_by_staff")

    # AC9: cost model si proiectie la final de luna (10 zile din 30 -> factor 3x).
    mc = report.model_cost
    assert mc.total_input_tokens == 100_000
    assert mc.total_output_tokens == 20_000
    assert mc.total_cost == Decimal("3.00")
    assert mc.projected_month_end_cost == Decimal("9.00")
    assert mc.monthly_ceiling == Decimal("10.00")
    assert mc.over_ceiling is False
    assert mc.ceiling_share == Decimal("0.9000")


# ---------- Configurare din rules dict, cazuri goale, decembrie si adaptorul peste store ----------

def test_config_from_rules_and_december_projection_and_empty_period():
    cfg = UsageMetricsConfig.from_rules(
        {
            "model_input_price_per_million": "3.00",
            "model_output_price_per_million": "15.00",
            "model_monthly_cost_ceiling": "5.00",
            "suggestion_similarity_threshold": 0.65,
        }
    )
    assert cfg.similarity_threshold == pytest.approx(0.65)

    nested_cfg = UsageMetricsConfig.from_rules(
        {
            "model_cost": {
                "input_price_per_million": "3.00",
                "output_price_per_million": "15.00",
                "monthly_cost_ceiling": "0",
            }
        }
    )
    assert nested_cfg.monthly_cost_ceiling == Decimal("0")

    for bad_rules in (
        {},
        {"model_input_price_per_million": "TBD", "model_output_price_per_million": "1", "model_monthly_cost_ceiling": "1"},
        {"model_input_price_per_million": 3.0, "model_output_price_per_million": "1", "model_monthly_cost_ceiling": "1"},
        {"model_input_price_per_million": "-1", "model_output_price_per_million": "1", "model_monthly_cost_ceiling": "1"},
        {"model_input_price_per_million": "abc", "model_output_price_per_million": "1", "model_monthly_cost_ceiling": "1"},
        {
            "model_input_price_per_million": "1",
            "model_output_price_per_million": "1",
            "model_monthly_cost_ceiling": "1",
            "suggestion_similarity_threshold": "invalid",
        },
        {
            "model_input_price_per_million": "1",
            "model_output_price_per_million": "1",
            "model_monthly_cost_ceiling": "1",
            "model_cost": "not-a-dict",
            "suggestion_similarity_threshold": 0,
        },
    ):
        with pytest.raises(ValueError):
            UsageMetricsConfig.from_rules(bad_rules)

    with pytest.raises(ValueError):
        UsageMetricsConfig(
            input_price_per_million=Decimal("-1"),
            output_price_per_million=Decimal("1"),
            monthly_cost_ceiling=Decimal("1"),
        )

    # Perioada invalida (end <= start) si datetimes naive convertite la Europe/Bucharest.
    start_dec = datetime(2026, 12, 1, 0, 0)
    end_dec = datetime(2027, 1, 1, 0, 0)
    assert to_bucharest(start_dec).tzinfo == TZ
    with pytest.raises(ValueError):
        compute_usage_metrics([], end_dec, start_dec, nested_cfg)

    empty_rep = compute_usage_metrics([], start_dec, end_dec, nested_cfg)
    assert empty_rep.total_suggestions == 0
    assert empty_rep.time_to_suggestion.median_s is None
    assert empty_rep.backend_latency.median_s is None
    assert empty_rep.model_cost.total_cost == Decimal("0.00")
    assert empty_rep.model_cost.ceiling_share is None


def test_rows_from_store_links_by_chat_order_without_copying_messages():
    store = InMemoryStore()
    ch, key = "whatsapp", "40700001234"
    t0 = datetime(2026, 11, 5, 10, 0, tzinfo=TZ)

    # Mesaj 1 client (fara sent_at pe pagina -> marcat missing_sent_at in meta), apoi sugestie inlocuita fara raspuns.
    store.append_message(ch, key, LoggedMessage(direction="in", text="Salut", at=t0, meta={"id": "m1", "sent_at": None}))
    s1 = Suggestion(
        id="s1",
        channel=ch,
        key=key,
        status="superseded",
        created_at=t0 + timedelta(seconds=8),
        basis_message_id="m1",
        suggestion=AssistSuggestion(suggestion_id="s1", kind="question", text="Ce produs doriți?"),
    )
    store.save_suggestion(s1)

    # Mesaj 2 client, sugestie s2, urmata de mesajul colegului (editat usor) si link de plata creat.
    store.append_message(
        ch,
        key,
        LoggedMessage(direction="in", text="100 stickere 5x5", at=t0 + timedelta(seconds=20), meta={"id": "m2"}),
    )
    s2 = Suggestion(
        id="s2",
        channel=ch,
        key=key,
        status="linked",
        created_at=t0 + timedelta(seconds=35),
        basis_message_id="m2",
        suggestion=AssistSuggestion(suggestion_id="s2", kind="offer", text=OFFER_SAMPLE, payment_url="https://pay.test/1"),
        linked_by="ana",
        linked_at=t0 + timedelta(seconds=50),
    )
    store.save_suggestion(s2)
    # Mesaj intermediar fara id si mesaj de la client inainte de raspunsul colegului.
    store.append_message(ch, key, LoggedMessage(direction="in", text="nota fara id", at=t0 + timedelta(seconds=40), meta={}))
    store.append_message(
        ch,
        key,
        LoggedMessage(direction="staff", text="Bună ziua!\n" + OFFER_SAMPLE, at=t0 + timedelta(seconds=60), meta={"id": "m3"}),
    )

    # Sugestie fara basis_message_id in jurnal (inainte de ultima sugestie activa).
    s_unlinked = Suggestion(
        id="s-unlinked",
        channel=ch,
        key=key,
        status="pending",
        created_at=t0 + timedelta(seconds=70),
        basis_message_id="inexistent",
        suggestion=AssistSuggestion(suggestion_id="s-unlinked", kind="none", text=""),
    )
    store.save_suggestion(s_unlinked)

    # Mesaj cu missing_sent_at=True si sugestie activa la final (pending).
    store.append_message(
        ch,
        key,
        LoggedMessage(direction="in", text="Multumesc", at=t0 + timedelta(seconds=75), meta={"id": "m4", "missing_sent_at": True}),
    )
    s3 = Suggestion(
        id="s3",
        channel=ch,
        key=key,
        status="pending",
        created_at=t0 + timedelta(seconds=90),
        basis_message_id="m4",
        suggestion=AssistSuggestion(suggestion_id="s3", kind="reply", text="Răspuns în așteptare."),
    )
    store.save_suggestion(s3)

    rows = rows_from_store(store, ch, key)
    assert len(rows) == 4
    rep = compute_usage_metrics(rows, t0 - timedelta(minutes=1), t0 + timedelta(hours=1), BASE_CONFIG)
    assert rep.outcomes == {"unchanged": 0, "edited": 1, "ignored": 1, "pending": 1}
    assert rep.time_to_suggestion.missing_sent_at_count == 2  # s1 (sent_at=None) si s3 (missing_sent_at=True)
    assert rep.payment_links_created == 1
    assert rep.requests_by_staff == {"ana": 1}

    # AC11: obiectul Suggestion din store nu a stocat textul mesajului trimis de om.
    persisted = store.get_suggestion("s2")
    assert persisted is not None
    assert "Bună ziua!" not in persisted.model_dump_json()


def test_rules_json_and_live_assist_api_feed_usage_metrics(tmp_path):
    from fastapi.testclient import TestClient

    from ec_quote.agent import ModelReply, Rules
    from ec_quote.api.app import create_app
    from ec_quote.config import load_settings
    from tests.agent.fakes import Harness

    cfg = UsageMetricsConfig.from_rules(Rules.load().raw)
    assert cfg.input_price_per_million == Decimal("15")
    assert cfg.output_price_per_million == Decimal("75")
    assert cfg.monthly_cost_ceiling == Decimal("500")
    assert cfg.similarity_threshold == pytest.approx(0.6)

    harness = Harness(tmp_path, ModelReply(text="Bună ziua! Ce dimensiune și cantitate doriți?"))
    now_box = [datetime(2026, 11, 26, 10, 0, tzinfo=TZ)]
    mono_box = [100.0]

    def fake_mono() -> float:
        mono_box[0] += 0.25
        return mono_box[0]

    settings = load_settings(
        {
            "EC_QUOTE_INBOUND_SECRET": "inbound-secret-test-1234567890",
            "EC_QUOTE_ASSIST_TOKENS": "ioana:assist-token-test-1234567890",
            "EC_QUOTE_DATA_DIR": str(tmp_path),
        },
        require_integrations=False,
    )
    app = create_app(harness.engine, settings, clock=lambda: now_box[0], monotonic=fake_mono)
    with TestClient(app) as client:
        resp = client.post(
            "/v1/assist/suggest",
            headers={"X-EcQuote-Assist-Token": "assist-token-test-1234567890"},
            json={
                "chat": {"key": "40722123456", "name": "Maria", "phone": "+40722123456"},
                "messages": [{"id": "m_live_1", "direction": "in", "text": "Salut, vreau etichete", "sent_at": None}],
            },
        )
        assert resp.status_code == 200

    rows = rows_from_store(harness.store, "whatsapp", "40722123456")
    assert len(rows) == 1
    rep = compute_usage_metrics(rows, now_box[0] - timedelta(hours=1), now_box[0] + timedelta(hours=1), cfg)
    assert rep.total_suggestions == 1
    assert rep.requests_by_staff == {"ioana": 1}
    assert rep.time_to_suggestion.missing_sent_at_count == 1
    assert rep.backend_latency.count == 1
    assert rep.backend_latency.median_s > 0
