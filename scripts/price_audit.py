"""CLI pentru auditul de paritate a preturilor (50 configuratii).

Exemple:
    python scripts/price_audit.py --replay tests/audit/fixtures/parity
    python scripts/price_audit.py --live --out docs/audits
    python scripts/price_audit.py --live --record tests/audit/fixtures/parity --out docs/audits
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import httpx

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ec_quote.audit.parity import (  # noqa: E402
    DEFAULT_AUDIT_COUNT,
    DEFAULT_AUDIT_SEED,
    ParityAuditReport,
    RateLimitedHttp,
    record_parity_fixtures,
    render_report_json,
    render_report_markdown,
    replay_parity_fixtures,
    verify_parity,
)
from ec_quote.pricing.client import CalculatorClient, load_vat_percent  # noqa: E402

TZ = ZoneInfo("Europe/Bucharest")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Audit paritate preturi calculator vs ec-quote.")
    parser.add_argument("--live", action="store_true", help="Interogheaza calculatorul real (cere CALCULATOR_SYNC_SECRET).")
    parser.add_argument("--record", type=Path, default=None, help="Director unde se salveaza fixture-urile sanitizate.")
    parser.add_argument("--replay", type=Path, default=None, help="Director cu fixture-uri salvate, rulate fara retea.")
    parser.add_argument("--out", type=Path, default=None, help="Director unde se scriu rapoartele JSON si Markdown.")
    parser.add_argument("--base-url", type=str, default=None, help="Suprascrie CALCULATOR_BASE_URL pentru --live.")
    parser.add_argument("--count", type=int, default=DEFAULT_AUDIT_COUNT, help="Numarul de configuratii (implicit 50).")
    parser.add_argument("--seed", type=int, default=DEFAULT_AUDIT_SEED, help="Seed determinist pentru esantionare.")
    return parser


def _write_reports(out_dir: Path, report: ParityAuditReport, forbidden_secrets: tuple[str, ...] = ()) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_text = render_report_json(report)
    md_text = render_report_markdown(report)
    for secret in forbidden_secrets:
        if secret and (secret in json_text or secret in md_text):
            raise RuntimeError("Secret detectat in raport; scriere oprita")
    (out_dir / "parity-report.json").write_text(json_text, encoding="utf-8")
    (out_dir / "parity-report.md").write_text(md_text, encoding="utf-8")


def _print_report_summary(report: ParityAuditReport, stream: Any) -> None:
    print(
        f"{report.consistent_count}/{report.total_count} identice "
        f"(pretuite: {report.priced_count}, nepretuite 422: {report.unpriced_count})",
        file=stream,
    )
    for mismatch in report.mismatches:
        print(
            f"DIFERENTA {mismatch.case_id} ({mismatch.config_summary}) | "
            f"camp={mismatch.field} | asteptat={mismatch.expected} | gasit={mismatch.found}",
            file=stream,
        )


def main(
    argv: Sequence[str] | None = None,
    *,
    env: Mapping[str, str] | None = None,
    http: Any = None,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
    now: datetime | None = None,
    stdout: Any = None,
    stderr: Any = None,
) -> int:
    out_stream = stdout if stdout is not None else sys.stdout
    err_stream = stderr if stderr is not None else sys.stderr
    environ = os.environ if env is None else env
    args = build_parser().parse_args(list(argv) if argv is not None else None)
    current_now = now if now is not None else datetime.now(TZ)

    if args.replay is not None and (args.live or args.record is not None):
        print("Eroare: --replay nu se poate combina cu --live sau --record.", file=err_stream)
        return 2
    if not args.live and args.replay is None:
        print("Eroare: alegeti --replay <director> sau --live.", file=err_stream)
        return 2

    vat: Decimal = load_vat_percent()

    if args.replay is not None:
        try:
            report = replay_parity_fixtures(args.replay, vat_percent=vat, now=current_now)
        except Exception as exc:
            print(f"Eroare la citirea fixture-urilor: {exc}", file=err_stream)
            return 1
        if args.out is not None:
            _write_reports(args.out, report)
        _print_report_summary(report, out_stream)
        return 0 if report.ok else 1

    # Mod --live
    secret = (environ.get("CALCULATOR_SYNC_SECRET") or "").strip()
    if not secret:
        print("Eroare: CALCULATOR_SYNC_SECRET lipseste; rularea --live este refuzata.", file=err_stream)
        return 1
    base_url = (args.base_url or environ.get("CALCULATOR_BASE_URL") or "").strip()
    if not base_url:
        print("Eroare: CALCULATOR_BASE_URL lipseste; rularea --live este refuzata.", file=err_stream)
        return 1

    owns_http = http is None
    raw_http = httpx.Client() if owns_http else http
    try:
        throttled = RateLimitedHttp(raw_http, min_interval_seconds=1.0, clock=clock, sleep=sleep)

        def factory(transport_http: Any) -> CalculatorClient:
            return CalculatorClient(base_url, secret, http=transport_http, vat_percent=vat)

        if args.record is not None:
            report = record_parity_fixtures(
                args.record,
                factory,
                throttled,
                count=args.count,
                seed=args.seed,
                vat_percent=vat,
                forbidden_secrets=(secret, base_url),
            )
        else:
            report = verify_parity(
                factory,
                throttled,
                count=args.count,
                seed=args.seed,
                vat_percent=vat,
                mode="live",
                now=current_now,
            )

        out_dir = args.out if args.out is not None else ROOT / "docs" / "audits"
        _write_reports(out_dir, report, forbidden_secrets=(secret,))
        _print_report_summary(report, out_stream)
        return 0 if report.ok else 1
    finally:
        if owns_http and hasattr(raw_http, "close"):
            raw_http.close()


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
