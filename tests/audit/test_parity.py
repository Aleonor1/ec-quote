"""Teste pentru story-6: auditul de paritate a preturilor pe 50 de configuratii."""
from __future__ import annotations

import io
import json
import shutil
import socket
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

import scripts.price_audit as price_audit_cli
from ec_quote.audit import (
    PLACEHOLDER_BASE_URL,
    PLACEHOLDER_CDN_URL,
    RateLimitedHttp,
    dumps_exact_json,
    record_parity_fixtures,
    render_report_json,
    render_report_markdown,
    replay_parity_fixtures,
    sample_configurations,
    verify_parity,
)
from ec_quote.contracts import LineChoices
from ec_quote.pricing.client import CONFIG_PATH, LINE_PATH, CalculatorClient, choices_to_body, find_product
from ec_quote.pricing.fake import FAKE_CATALOG, FAKE_SECRET, STICKER_ID, FakeCalculator

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "parity"


# ---------- AC1: esantionare determinista si acoperire completa a catalogului ----------

def test_sampler_is_deterministic_and_covers_all_catalog_axes():
    first = sample_configurations(FAKE_CATALOG, count=50, seed=42)
    second = sample_configurations(FAKE_CATALOG, count=50, seed=42)
    different_seed = sample_configurations(FAKE_CATALOG, count=50, seed=99)

    assert len(first) == 50
    assert first == second
    assert first != different_seed
    assert len({json.dumps(choices_to_body(c), sort_keys=True) for c in first}) == 50

    # Fiecare kind din catalog este prezent.
    catalog_kinds = {p["kind"] for p in FAKE_CATALOG["products"]}
    sampled_kinds = {find_product(FAKE_CATALOG, c.product_id)["kind"] for c in first}
    assert sampled_kinds == catalog_kinds

    # Cel putin 3 materiale distincte.
    materials = {c.material_name for c in first}
    assert len(materials) >= 3

    # Dimensiuni preset si custom, inclusiv minCm si maxCm.
    has_preset = False
    has_custom = False
    has_min_custom = False
    has_max_custom = False
    on_tier = 0
    between_tiers = 0
    at_product_min = 0
    at_product_max = 0

    for c in first:
        prod = find_product(FAKE_CATALOG, c.product_id)
        presets = {
            (Decimal(str(s["widthCm"])), Decimal(str(s["heightCm"])))
            for s in prod["sizesByShape"].get(c.shape, [])
        }
        presets |= {(h, w) for w, h in presets}
        if (c.width_cm, c.height_cm) in presets:
            has_preset = True
        else:
            has_custom = True
            custom = prod["customSize"]
            min_cm = Decimal(str(custom["minCm"]))
            max_cm = Decimal(str(custom["maxCm"]))
            if (c.width_cm, c.height_cm) == (min_cm, min_cm):
                has_min_custom = True
            if (c.width_cm, c.height_cm) == (max_cm, max_cm):
                has_max_custom = True

        tiers = sorted(int(t["quantity"]) for t in prod["quantity"]["tiers"])
        if c.quantity in tiers:
            on_tier += 1
        elif any(lo < c.quantity < hi for lo, hi in zip(tiers, tiers[1:])):
            between_tiers += 1
        if c.quantity == int(prod["quantity"]["min"]):
            at_product_min += 1
        if c.quantity == int(prod["quantity"]["max"]):
            at_product_max += 1

    assert has_preset and has_custom and has_min_custom and has_max_custom
    assert on_tier >= 5
    assert between_tiers >= 5
    assert at_product_min >= 1
    assert at_product_max >= 1

    # Fiecare optiune permisa de catalog este pornita in cel putin 3 configuratii.
    assert sum(1 for c in first if c.adhesive == "strong") >= 3
    assert sum(1 for c in first if c.white_print) >= 3
    assert sum(1 for c in first if c.cut == "double") >= 3
    assert sum(1 for c in first if c.cut == "back") >= 3
    assert sum(1 for c in first if c.urgent) >= 3
    assert sum(1 for c in first if c.file_editing != "none") >= 3
    assert sum(1 for c in first if bool(c.add_ons)) >= 3


def test_sampler_validates_inputs_and_handles_small_counts():
    with pytest.raises(ValueError):
        sample_configurations(FAKE_CATALOG, count=0)
    with pytest.raises(ValueError):
        sample_configurations({"products": []}, count=5)
    small = sample_configurations(FAKE_CATALOG, count=5, seed=42)
    assert len(small) == 5
    larger = sample_configurations(FAKE_CATALOG, count=80, seed=42)
    assert len(larger) == 80

    no_opts_catalog = {
        "settings": {
            "adhesive": {"enabled": False},
            "whitePrint": {"enabled": False},
            "doubleCut": {"enabled": False},
            "backCut": {"enabled": False},
            "urgency": {"enabled": False},
            "fileEditing": {"enabled": False},
        },
        "products": [
            {
                "id": STICKER_ID,
                "title": "Unic",
                "kind": "sticker",
                "shapes": ["circle"],
                "materials": [{"name": "Vinil Alb Lucios"}],
                "sizes": {"equal": [{"widthCm": 5, "heightCm": 5}]},
                "sizesByShape": {},
                "customSize": {"enabled": False, "minCm": 5, "maxCm": 5},
                "addOnGroups": [{"name": "", "choices": []}],
                "options": {},
                "quantity": {"tiers": [], "min": 50, "default": 50, "max": 50},
            }
        ],
    }
    padded = sample_configurations(no_opts_catalog, count=4, seed=1)
    assert len(padded) == 4


# ---------- AC2, AC3, AC4, AC5, AC9: replay pe cele 50 de fixture-uri fara retea ----------

def test_replay_50_fixtures_without_network(monkeypatch):
    def _forbid_socket(*_args, **_kwargs):
        raise AssertionError("Niciun apel de retea nu este permis in testul de replay")

    monkeypatch.setattr(socket, "create_connection", _forbid_socket)

    report = replay_parity_fixtures(FIXTURE_DIR, vat_percent=Decimal("21"))
    assert report.ok
    assert report.total_count == 50
    assert report.consistent_count == 50
    assert report.priced_count + report.unpriced_count == 50
    assert report.priced_count >= 45
    assert report.unpriced_count >= 1  # Hârtie Kraft -> 422 no_price verificat consistent
    assert report.unpriced_by_reason.get("no_price", 0) >= 1
    assert report.mismatches == []

    # Fixture-urile nu contin niciun secret si niciun alt host decat placeholder-ul.
    for json_file in FIXTURE_DIR.glob("*.json"):
        raw = json_file.read_text(encoding="utf-8")
        assert FAKE_SECRET not in raw
        assert "calculator.test" not in raw
        assert "cdn.test" not in raw
        assert PLACEHOLDER_BASE_URL in raw or PLACEHOLDER_CDN_URL in raw


# ---------- AC6: CLI --replay iese cu 0 pe 50/50 si cu 1 la modificare de 0.01 ----------

def test_cli_replay_passes_and_detects_one_cent_tamper(tmp_path):
    out_buf, err_buf = io.StringIO(), io.StringIO()
    report_dir = tmp_path / "reports"
    code = price_audit_cli.main(
        ["--replay", str(FIXTURE_DIR), "--out", str(report_dir)],
        stdout=out_buf,
        stderr=err_buf,
    )
    assert code == 0
    stdout_txt = out_buf.getvalue()
    assert "50/50 identice" in stdout_txt
    assert (report_dir / "parity-report.json").is_file()
    assert (report_dir / "parity-report.md").is_file()
    assert "\u2014" not in (report_dir / "parity-report.md").read_text(encoding="utf-8")

    # Copiem fixture-urile si schimbam un singur total inregistrat cu +0.01.
    tampered_dir = tmp_path / "tampered"
    shutil.copytree(FIXTURE_DIR, tampered_dir)
    target_case = tampered_dir / "case-01.json"
    doc = json.loads(target_case.read_text(encoding="utf-8"), parse_float=Decimal)
    original_total = Decimal(str(doc["response"]["total"]))
    shifted_total = original_total + Decimal("0.01")
    doc["response"]["total"] = shifted_total
    target_case.write_text(dumps_exact_json(doc, indent=2) + "\n", encoding="utf-8")

    out_bad, err_bad = io.StringIO(), io.StringIO()
    bad_code = price_audit_cli.main(["--replay", str(tampered_dir)], stdout=out_bad, stderr=err_bad)
    bad_txt = out_bad.getvalue()
    assert bad_code == 1
    assert "49/50 identice" in bad_txt
    assert "case-01" in bad_txt
    assert "total" in bad_txt
    assert str(original_total) in bad_txt
    assert str(shifted_total) in bad_txt


# ---------- AC7: --live refuza fara secret, limiteaza la 1 cerere/s, nu scrie secretul ----------

def test_cli_live_refuses_without_secret_or_base_url(tmp_path):
    called = False

    def _never_called(*_a, **_kw):
        nonlocal called
        called = True
        raise AssertionError("Nu trebuie apelat HTTP fara secret")

    out_buf, err_buf = io.StringIO(), io.StringIO()
    code = price_audit_cli.main(
        ["--live", "--out", str(tmp_path)],
        env={"CALCULATOR_BASE_URL": "https://live.example.invalid"},
        http=_never_called,
        stdout=out_buf,
        stderr=err_buf,
    )
    assert code == 1 and not called
    assert "CALCULATOR_SYNC_SECRET" in err_buf.getvalue()

    err_url = io.StringIO()
    code_url = price_audit_cli.main(
        ["--live", "--out", str(tmp_path)],
        env={"CALCULATOR_SYNC_SECRET": "super-secret-live-token-value"},
        http=_never_called,
        stdout=io.StringIO(),
        stderr=err_url,
    )
    assert code_url == 1 and not called
    assert "CALCULATOR_BASE_URL" in err_url.getvalue()
    assert "super-secret-live-token-value" not in err_url.getvalue()


def test_cli_live_rate_limits_one_req_per_second_and_never_writes_secret(tmp_path):
    secret_val = "live-sync-secret-never-leak-999"
    fake = FakeCalculator(secret=secret_val)
    fake_http = fake.http()

    now_val = 100.0
    slept: list[float] = []

    def fake_clock() -> float:
        return now_val

    def fake_sleep(seconds: float) -> None:
        nonlocal now_val
        slept.append(seconds)
        now_val += seconds

    rec_dir = tmp_path / "recorded"
    out_dir = tmp_path / "out"
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()

    code = price_audit_cli.main(
        ["--live", "--count", "6", "--seed", "7", "--record", str(rec_dir), "--out", str(out_dir)],
        env={"CALCULATOR_SYNC_SECRET": secret_val, "CALCULATOR_BASE_URL": "https://real-calc.example.com"},
        http=fake_http,
        clock=fake_clock,
        sleep=fake_sleep,
        stdout=stdout_buf,
        stderr=stderr_buf,
    )
    assert code == 0
    assert "6/6 identice" in stdout_buf.getvalue()
    assert len(slept) == len(fake.requests) - 1
    assert all(abs(s - 1.0) < 1e-9 for s in slept)

    for folder in (rec_dir, out_dir):
        for file_path in folder.iterdir():
            content = file_path.read_text(encoding="utf-8")
            assert secret_val not in content
            if folder == rec_dir:
                assert "real-calc.example.com" not in content
                assert PLACEHOLDER_BASE_URL in content


def test_cli_argument_validation_and_missing_fixture_handling(tmp_path):
    err1 = io.StringIO()
    assert price_audit_cli.main([], stdout=io.StringIO(), stderr=err1) == 2
    err2 = io.StringIO()
    assert price_audit_cli.main(["--replay", str(FIXTURE_DIR), "--live"], stdout=io.StringIO(), stderr=err2) == 2
    err3 = io.StringIO()
    assert price_audit_cli.main(["--replay", str(tmp_path / "inexistent")], stdout=io.StringIO(), stderr=err3) == 1

    # Mod --live fara --record (doar raport in --out).
    secret_val = "live-secret-no-record-123"
    fake = FakeCalculator(secret=secret_val)
    out_dir = tmp_path / "live_only_out"
    clock_t = [0.0]

    def adv_sleep(sec: float) -> None:
        clock_t[0] += sec

    code = price_audit_cli.main(
        ["--live", "--count", "3", "--out", str(out_dir)],
        env={"CALCULATOR_SYNC_SECRET": secret_val, "CALCULATOR_BASE_URL": "https://calc.test"},
        http=fake.http(),
        clock=lambda: clock_t[0],
        sleep=adv_sleep,
        stdout=io.StringIO(),
        stderr=io.StringIO(),
    )
    assert code == 0
    assert (out_dir / "parity-report.json").is_file()
    assert (out_dir / "parity-report.md").is_file()


# ---------- AC8: numar ostil float-ului (1234.565) purtat exact in Decimal ----------

def test_subcent_1234_565_survives_exact_and_fails_if_parsed_via_float(tmp_path):
    fixture_dir = tmp_path / "float_trap"
    fixture_dir.mkdir()
    (fixture_dir / "catalog.json").write_text(
        dumps_exact_json({"url": PLACEHOLDER_BASE_URL + CONFIG_PATH, "catalog": FAKE_CATALOG}, indent=2),
        encoding="utf-8",
    )
    sample = LineChoices(
        product_id=STICKER_ID,
        material_name="Vinil Alb Mat",
        shape="circle",
        width_cm=Decimal("5"),
        height_cm=Decimal("5"),
        quantity=2000,
    )
    case_doc = {
        "case_id": "case-01",
        "url": PLACEHOLDER_BASE_URL + LINE_PATH,
        "choices": json.loads(sample.model_dump_json(), parse_float=Decimal),
        "request": choices_to_body(sample),
        "status_code": 200,
        "response": {
            "status": "priced",
            "total": Decimal("1234.565"),
            "base": Decimal("1100.1"),
            "unitPrice": Decimal("0.6173"),
            "capQuantity": None,
            "pricingPath": "A",
            "flatBaselinePct": 0,
            "breakdown": {
                "tablePrice": Decimal("0.3"),
                "fullPrice": Decimal("1500"),
                "discountPercent": Decimal("52.5"),
            },
            "properties": [
                {"name": "Dimensiune", "value": "5 x 5 CM"},
                {"name": "_calculator_price", "value": "1234.565"},
                {"name": "_product_gid", "value": STICKER_ID},
            ],
        },
        "recorded": {
            "status": "priced",
            "total": "1234.565",
            "total_ex_vat": "1020.30",
            "unit_price": "0.6173",
        },
        "tiers": [],
    }
    (fixture_dir / "case-01.json").write_text(dumps_exact_json(case_doc, indent=2), encoding="utf-8")

    # Cu clientul real (parse_float=Decimal), 1234.565 trece intact.
    report = replay_parity_fixtures(fixture_dir, vat_percent=Decimal("21"))
    assert report.ok
    assert report.cases[0].total == Decimal("1234.565")
    assert str(report.cases[0].total) == "1234.565"

    # Daca un client defect parseaza prin float (fara parse_float=Decimal / Decimal.from_float), testul pica!
    class FloatParsingClient(CalculatorClient):
        @staticmethod
        def _parse(text: str, exact_numbers: bool) -> Any:
            parsed = json.loads(text)  # trece numerele prin float!
            if isinstance(parsed, dict) and isinstance(parsed.get("total"), float):
                parsed["total"] = Decimal(parsed["total"])
            return parsed

    broken = replay_parity_fixtures(
        fixture_dir,
        vat_percent=Decimal("21"),
        client_builder=lambda url, sec, http, vat: FloatParsingClient(url, sec, http=http, vat_percent=vat),
    )
    assert not broken.ok
    mismatch_fields = {m.field for m in broken.mismatches}
    assert "float_leak" in mismatch_fields or "total" in mismatch_fields


# ---------- AC5 + cazuri limita de eroare si raportare ----------

def test_422_reason_mismatch_and_report_rendering(tmp_path):
    fixture_dir = tmp_path / "unpriced_mismatch"
    fixture_dir.mkdir()
    (fixture_dir / "catalog.json").write_text(
        dumps_exact_json({"url": PLACEHOLDER_BASE_URL + CONFIG_PATH, "catalog": FAKE_CATALOG}, indent=2),
        encoding="utf-8",
    )
    sample = LineChoices(
        product_id=STICKER_ID,
        material_name="Hârtie Kraft",
        shape="circle",
        width_cm=Decimal("5"),
        height_cm=Decimal("5"),
        quantity=2000,
    )
    doc = {
        "case_id": "case-01",
        "url": PLACEHOLDER_BASE_URL + LINE_PATH,
        "choices": json.loads(sample.model_dump_json(), parse_float=Decimal),
        "request": choices_to_body(sample),
        "status_code": 422,
        "response": {"status": "unpriced", "reason": "no_price"},
        "recorded": {"status": "unpriced", "reason": "custom_size_disabled"},
        "tiers": [],
    }
    (fixture_dir / "case-01.json").write_text(dumps_exact_json(doc, indent=2), encoding="utf-8")

    report = replay_parity_fixtures(fixture_dir, vat_percent=Decimal("21"))
    assert not report.ok
    assert report.unpriced_count == 1
    assert report.mismatches[0].field == "reason"
    assert report.mismatches[0].expected == "custom_size_disabled"
    assert report.mismatches[0].found == "no_price"

    md = render_report_markdown(report)
    js = json.loads(render_report_json(report))
    assert "Diferente gasite" in md and "custom_size_disabled" in md
    assert js["ok"] is False and js["unpriced_count"] == 1


def test_exact_json_serializer_rejects_non_finite_and_unknown_types():
    assert dumps_exact_json({"a": [True, False, None, 3, 1.5, Decimal("10.25")], "gol": {}, "lista": []})
    with pytest.raises(ValueError):
        dumps_exact_json(Decimal("NaN"))
    with pytest.raises(TypeError):
        dumps_exact_json(object())


def test_rate_limited_http_skips_sleep_when_enough_time_passed():
    clock_val = [10.0]
    sleeps: list[float] = []

    def send(_method: str, _url: str, **_kw: Any) -> Any:
        class R:
            status_code = 200
            text = "{}"
        return R()

    rl = RateLimitedHttp(send, min_interval_seconds=1.0, clock=lambda: clock_val[0], sleep=sleeps.append)
    rl.request("GET", "https://x")
    clock_val[0] += 2.5
    rl.request("GET", "https://x")
    assert sleeps == []


def test_record_refuses_if_secret_somehow_appears_in_payload(tmp_path):
    fake = FakeCalculator()
    rec_target = tmp_path / "overwrite_check"
    rec_target.mkdir()
    (rec_target / "case-99.json").write_text("{}", encoding="utf-8")
    record_parity_fixtures(
        rec_target,
        lambda h: CalculatorClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        count=1,
        seed=1,
    )
    assert not (rec_target / "case-99.json").exists()

    with pytest.raises(RuntimeError):
        record_parity_fixtures(
            tmp_path / "leak_check",
            lambda h: CalculatorClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
            fake.http(),
            count=1,
            seed=1,
            forbidden_secrets=("Vinil",),  # apare in catalog -> declanseaza garda anti-scurgere
        )


def test_verify_parity_detects_all_downstream_and_quote_defects(monkeypatch, tmp_path):
    from ec_quote.audit import parity as parity_mod
    from ec_quote.contracts import LineProperty, OfferLine, PriceQuote, TierOffer, Unpriced

    sample = LineChoices(
        product_id=STICKER_ID,
        material_name="Vinil Alb Mat",
        shape="circle",
        width_cm=Decimal("5"),
        height_cm=Decimal("5"),
        quantity=100,
    )
    fake = FakeCalculator()

    # Client defect care distorsioneaza ex_vat, unit_price, _calculator_price si treptele.
    class SkewedClient(CalculatorClient):
        def get_price(self, ch: LineChoices):
            res = super().get_price(ch)
            if isinstance(res, PriceQuote) and ch.quantity == 100:
                return res.model_copy(
                    update={
                        "total_ex_vat": Decimal("10.00"),
                        "unit_price": Decimal("9.99"),
                        "properties": [LineProperty(name="_calculator_price", value="nu-e-numar")],
                    }
                )
            if ch.quantity == 200:
                return Unpriced(reason="no_price")
            return res

        def get_price_tiers(self, ch: LineChoices, count: int):
            return [
                TierOffer(quantity=99, total=Decimal("1"), total_ex_vat=Decimal("1"), unit_price=Decimal("1")),
                TierOffer(quantity=200, total=Decimal("1"), total_ex_vat=Decimal("1"), unit_price=Decimal("1")),
                TierOffer(quantity=300, total=Decimal("1"), total_ex_vat=Decimal("1"), unit_price=Decimal("1")),
            ]

    rep = verify_parity(
        lambda h: SkewedClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        configurations=[sample],
        recorded_expectations={"case-01": {"status": "unpriced", "reason": "no_price"}},
    )
    fields = {m.field for m in rep.mismatches}
    assert {
        "recorded.status",
        "total_ex_vat",
        "total_ex_vat_plus_vat",
        "unit_price",
        "properties._calculator_price",
        "tier[99].quantity",
        "tier[200].status",
        "tier[300].amounts",
    } <= fields

    # Defecte in offer_line, offer_text, offer_image si shopify.priceOverride.
    monkeypatch.setattr(
        parity_mod.offer_module,
        "build_lines",
        lambda *_a, **_kw: [
            OfferLine(label="100 buc", quantity=100, total_ex_vat=Decimal("1"), total=Decimal("2"), unit_price=Decimal("0.02"), highlighted=True)
        ],
    )
    monkeypatch.setattr(parity_mod, "_check_shopify_draft_override", lambda *_a: (Decimal("0.01"), Decimal("0.01")))
    rep_down = verify_parity(
        lambda h: CalculatorClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        configurations=[sample],
    )
    down_fields = {m.field for m in rep_down.mismatches}
    assert {"offer_line.amounts", "offer_text.amounts", "offer_image.amounts", "shopify.priceOverride"} <= down_fields

    # 422 in care un client defect intoarce motiv gresit sau PriceQuote in loc de Unpriced.
    unpriced_sample = sample.model_copy(update={"material_name": "Hârtie Kraft"})

    class WrongUnpricedClient(CalculatorClient):
        def get_price(self, ch: LineChoices):
            res = super().get_price(ch)
            if isinstance(res, Unpriced):
                return Unpriced(reason="alt_motiv")
            return res

    rep_422 = verify_parity(
        lambda h: WrongUnpricedClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        configurations=[unpriced_sample],
    )
    assert not rep_422.ok and rep_422.mismatches[0].field == "reason"

    # Client care intoarce PriceQuote pe 422 si Unpriced pe 200, sau nu face apel HTTP.
    quote_obj = fake.client().get_price(sample)

    class InvertedClient(CalculatorClient):
        def get_price(self, ch: LineChoices):
            super().get_price(ch)
            return quote_obj if ch.material_name == "Hârtie Kraft" else Unpriced(reason="fals")

    rep_inv = verify_parity(
        lambda h: InvertedClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        configurations=[unpriced_sample, sample],
    )
    assert [m.field for m in rep_inv.mismatches] == ["status", "status"]

    class SilentClient(CalculatorClient):
        def get_price(self, ch: LineChoices):
            return Unpriced(reason="fara_http")

    rep_silent = verify_parity(
        lambda h: SilentClient(PLACEHOLDER_BASE_URL, FAKE_SECRET, http=h, vat_percent=Decimal("21")),
        fake.http(),
        configurations=[sample],
    )
    assert rep_silent.mismatches[0].field == "http_response"

    # Lipsa catalog.json sau case-*.json in replay_parity_fixtures.
    empty_dir = tmp_path / "empty_replay"
    empty_dir.mkdir()
    with pytest.raises(FileNotFoundError):
        replay_parity_fixtures(empty_dir)
    (empty_dir / "catalog.json").write_text(dumps_exact_json(FAKE_CATALOG), encoding="utf-8")
    with pytest.raises(FileNotFoundError):
        replay_parity_fixtures(empty_dir)

