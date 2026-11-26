from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from ec_quote.agent import AnthropicModel, ModelError, Rules, build_engine, model_id_from_env
from ec_quote.agent import engine as engine_module
from ec_quote.agent.guard import check_text, money_mentions, parse_amount
from ec_quote.agent.offer import format_money, format_number
from ec_quote.agent.prompts import build_system_prompt
from ec_quote.agent.rules import to_local

from .fakes import (
    TZ, FakeCheckout, FakeCrm, FakeFiles, FakeHandoff, FakeMockup, FakePricing, ScriptedModel, make_rules,
)


def test_rules_load_from_repo_config_and_injected_path(tmp_path, monkeypatch):
    rules = Rules.load()
    assert rules.handoff_value_threshold_ron_ex_vat == Decimal("3000")
    assert isinstance(rules.vat_percent, Decimal) and rules.business_days == (1, 2, 3, 4, 5)

    custom = tmp_path / "rules.json"
    custom.write_text(json.dumps({**rules.raw, "offer_validity_days": 3, "production_term_urgent": "24 de ore"}))
    assert Rules.load(custom).offer_validity_days == 3
    monkeypatch.setenv("EC_QUOTE_RULES_PATH", str(custom))
    loaded = Rules.load()
    assert loaded.production_term(urgent=True) == "24 de ore"
    assert loaded.production_term(urgent=False) == loaded.production_term_standard


def test_business_hours_and_next_opening():
    rules = make_rules()
    assert rules.is_business_hours(datetime(2026, 11, 26, 9, 0, tzinfo=TZ))
    assert not rules.is_business_hours(datetime(2026, 11, 26, 18, 0, tzinfo=TZ))
    assert not rules.is_business_hours(datetime(2026, 11, 28, 12, 0, tzinfo=TZ))
    assert rules.next_business_open(datetime(2026, 11, 27, 18, 5, tzinfo=TZ)) == datetime(2026, 11, 30, 9, 0, tzinfo=TZ)
    # Fara fus orar: considerat ora Romaniei; UTC este convertit.
    assert to_local(datetime(2026, 11, 26, 10, 0)).utcoffset().total_seconds() == 7200
    assert rules.is_business_hours(datetime.fromisoformat("2026-11-26T07:30:00+00:00"))
    with pytest.raises(ValueError):
        make_rules(business_hours={"start": "09:00", "end": "18:00", "days": []}).next_business_open(
            datetime(2026, 11, 26, 10, 0, tzinfo=TZ))


def test_money_parsing_and_formatting():
    assert parse_amount("1.234,56") == Decimal("1234.56")
    assert parse_amount("1 234,5") == Decimal("1234.5")
    assert parse_amount("1234.56") == Decimal("1234.56")
    assert parse_amount("1.234") == Decimal("1234")
    assert parse_amount("abc") is None
    assert money_mentions("costă 1.234,56 lei sau RON 99 ori 5€, la 500 de etichete de 5 cm") == [
        Decimal("1234.56"), Decimal("99"), Decimal("5")]
    assert format_money(Decimal("1234567.5")) == "1.234.567,50"
    assert format_money(Decimal("-12")) == "-12,00"
    assert format_number(Decimal("5.50")) == "5,5" and format_number(Decimal("10")) == "10"


def test_guard_rules():
    def problems(text, amounts=(), percents=()):
        return check_text(text, allowed_amounts=amounts, allowed_percents=percents,
                          approved_claims=["rezistenta la umezeala si ulei", "lac UV mat", "fara laminare"],
                          catalog_terms=["Vinyl laminat"], allowed_terms=["3-5 zile lucrătoare"])

    assert problems("Totalul este 302,50 lei.", amounts=[Decimal("302.50")]) == []
    assert problems("Totalul este 302,49 lei.", amounts=[Decimal("302.50")])
    assert problems("Costă 20 EUR.", amounts=[Decimal("20")])  # numai lei
    assert problems("Aveți 15% reducere.", percents=[Decimal("10")])
    assert problems("Reducerea de cantitate este 10%.", percents=[Decimal("10")]) == []
    assert problems("Este gata în 24 de ore.")
    assert problems("Termenul este de 3-5 zile lucrătoare.") == []
    assert problems("Materialul Vinyl laminat are lac UV mat, fără laminare.") == []
    assert problems("Este garantat 5 ani și certificat alimentar.")
    assert problems("Rezistent la umezeală și ulei.") == []
    assert problems("Rezistent la umezeală, ulei și foc.")


def test_system_prompt_takes_numbers_from_rules():
    prompt = build_system_prompt(make_rules(max_clarifying_questions=4))
    assert "cel mult 4 întrebări" in prompt and "„lac UV mat\"" in prompt
    assert chr(0x2014) not in prompt and chr(0x2013) not in prompt


class _Block(SimpleNamespace):
    pass


def _fake_client(response, record):
    def create(**kwargs):
        record.append(kwargs)
        if isinstance(response, Exception):
            raise response
        return response

    messages = SimpleNamespace(create=create)
    return SimpleNamespace(messages=messages, beta=SimpleNamespace(messages=messages))


def test_anthropic_model_wrapper(monkeypatch):
    monkeypatch.delenv("EC_QUOTE_MODEL", raising=False)
    assert model_id_from_env() == "claude-opus-5-5"
    monkeypatch.setenv("EC_QUOTE_MODEL", "claude-sonnet-5-5")

    content = [_Block(type="thinking", thinking=""), _Block(type="text", text="Salut"),
               _Block(type="tool_use", id="tu_1", name="get_price", input={"quantity": 5})]
    record: list = []
    model = AnthropicModel(client=_fake_client(SimpleNamespace(stop_reason="tool_use", content=content), record))
    reply = model.complete(system=[{"type": "text", "text": "s"}], tools=[], messages=[{"role": "user", "content": "x"}])

    assert reply.text == "Salut" and reply.tool_calls[0].input == {"quantity": 5}
    assert reply.raw_content is content and reply.stop_reason == "tool_use"
    sent = record[0]
    assert sent["model"] == "claude-sonnet-5-5" and sent["output_config"] == {"effort": "medium"}
    assert sent["fallbacks"] == "default" and sent["betas"] == ["server-side-fallback-2026-07-01"]
    assert "thinking" not in sent and "tool_choice" not in sent and "temperature" not in sent

    plain: list = []
    refusal = SimpleNamespace(stop_reason="refusal", content=[])
    reply = AnthropicModel(client=_fake_client(refusal, plain), model="m", fallbacks=False).complete(
        system=[], tools=[], messages=[])
    assert reply.stop_reason == "refusal" and "fallbacks" not in plain[0]

    with pytest.raises(ModelError):
        AnthropicModel(client=_fake_client(RuntimeError("429"), [])).complete(system=[], tools=[], messages=[])


def test_build_engine_wires_sqlite_under_data_dir(tmp_path):
    engine = build_engine(
        pricing=FakePricing(), files=FakeFiles(), mockup=FakeMockup(), checkout=FakeCheckout(), crm=FakeCrm(),
        handoff=FakeHandoff(), model=ScriptedModel(), rules=make_rules(), data_dir=tmp_path)
    assert (tmp_path / "conversations.sqlite3").exists()
    assert engine.rules.shadow_mode is False
    engine.store.close()


def test_catalog_in_unknown_shape_defers_to_calculator():
    choices = engine_module.LineChoices(product_id="p", material_name="m", shape="s", width_cm=Decimal("1"),
                                        height_cm=Decimal("1"), quantity=1)
    assert engine_module._match_catalog({"altceva": 1}, choices) == (choices, None)
    assert engine_module._product_title({}, "p") == ""
