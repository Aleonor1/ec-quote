"""Scenariile din eval_cases.jsonl, jucate cu modelul fals. Lista lor: ec_quote/agent/scenarios.md."""
from __future__ import annotations

from pathlib import Path

import pytest

from ec_quote.agent import eval as harness

from .fakes import make_rules

CASES_PATH = Path(__file__).with_name("eval_cases.jsonl")
CASES = harness.load_cases(CASES_PATH)


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_scenario(case):
    assert harness.run_case(case, rules=make_rules()) == []


def test_every_scenario_is_listed_in_scenarios_md():
    listed = (Path(harness.__file__).with_name("scenarios.md")).read_text(encoding="utf-8")
    assert all(f"[{case['name']}]" in listed for case in CASES)
    assert len({case["name"] for case in CASES}) == len(CASES)


def test_eval_cli_runs_with_fake_model_and_skips_without_key(monkeypatch, capsys):
    assert harness.main(["--cases", str(CASES_PATH), "--fake"]) == 0
    assert f"{len(CASES)}/{len(CASES)} cazuri trecute" in capsys.readouterr().out

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert harness.main(["--cases", str(CASES_PATH)]) == 0
    assert "SKIP" in capsys.readouterr().out


def test_eval_reports_failures(tmp_path, capsys):
    broken = tmp_path / "cases.jsonl"
    broken.write_text(
        '// comentariu\n'
        '{"name": "suma_inventata", "steps": [{"turns": [{"in": "salut"}], "script": [{"text": "Buna ziua!"}], '
        '"expect": {"kind": "offer", "tools": ["get_price"], "no_tools": [], "handoff_reason": "complaint", '
        '"contains": ["pret"], "not_contains": ["buna"], "note_contains": ["x"], "can_link": true, '
        '"has_link": true, "lines": 2, "min_gaps": 1}}]}\n'
        '{"name": "fara_replici", "steps": [{"turns": [{"in": "salut"}], "script": [], "expect": {"kind": "reply"}}]}\n'
        '{"name": "link_fara_oferta", "steps": [{"link": true}]}\n', encoding="utf-8")
    assert harness.main(["--cases", str(broken), "--fake", "--only", "suma_inventata"]) == 1
    out = capsys.readouterr().out
    assert "FAIL suma_inventata" in out and "kind=reply" in out and "0/1" in out
    assert harness.main(["--cases", str(broken), "--fake"]) == 1
    out = capsys.readouterr().out
    assert "FAIL link_fara_oferta" in out and "FAIL fara_replici" in out


def test_check_flags_unsourced_amounts():
    from decimal import Decimal

    from ec_quote.contracts import AssistSuggestion

    suggestion = AssistSuggestion(suggestion_id="s", kind="reply", text="Costa 99 lei sau 10,00 lei.")
    failures = harness.check({"no_tools": ["get_price"]}, suggestion, ["get_price"], [Decimal("10")], 0)
    assert failures == ["unealta get_price nu trebuia chemata", "suma fara sursa in text: 99"]
