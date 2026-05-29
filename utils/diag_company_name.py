"""
get_company_name() 분기 경로 진단 도구.

사용 예 (프로젝트 루트에서):
  python utils/diag_company_name.py --predict
  python utils/diag_company_name.py --live
  python utils/diag_company_name.py --live --ticker TSLA
"""

from __future__ import annotations

import argparse
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils import portfolio  # noqa: E402
from utils.portfolio import get_company_name  # noqa: E402
from utils.product_master import get_product, load_product_master  # noqa: E402

Source = Literal["product_master", "ticker_fallback"]


@dataclass
class PredictResult:
    ticker: str
    source: Source
    name_preview: str
    in_master: bool
    master_name: str
    note: str = ""


@dataclass
class LiveResult:
    ticker: str
    name: str
    source: Source
    note: str = ""


def predict_source(ticker: str) -> PredictResult:
    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str) or {}
    master_name = str(product_info.get("name", "") or "").strip()
    in_master = bool(product_info)

    if master_name:
        return PredictResult(
            ticker=ticker_str,
            source="product_master",
            name_preview=master_name,
            in_master=in_master,
            master_name=master_name,
        )

    return PredictResult(
        ticker=ticker_str,
        source="ticker_fallback",
        name_preview=ticker_str,
        in_master=in_master,
        master_name=master_name,
        note="product_master name 없음 -> ticker 반환",
    )


def _collect_tickers(from_csv: bool, ticker: str | None) -> list[str]:
    if ticker:
        return [ticker.strip().upper()]

    tickers: set[str] = set(load_product_master().keys())

    if from_csv or not tickers:
        csv_path = PROJECT_ROOT / "data" / "trade_history.csv"
        if csv_path.exists():
            import pandas as pd

            df = pd.read_csv(csv_path)
            tickers.update(str(t).strip().upper() for t in df["ticker"].unique())

    return sorted(tickers)


def run_live(ticker: str) -> LiveResult:
    portfolio._NAME_CACHE.clear()
    name = get_company_name(ticker)
    ticker_str = str(ticker).strip().upper()

    product_info = get_product(ticker_str) or {}
    master_name = str(product_info.get("name", "") or "").strip()
    if master_name:
        return LiveResult(ticker=ticker_str, name=name, source="product_master")
    return LiveResult(
        ticker=ticker_str,
        name=name,
        source="ticker_fallback",
        note="product_master name 없음 -> ticker 반환",
    )


def _print_predict_table(results: list[PredictResult]) -> None:
    print("\n=== PREDICT (no network) ===")
    print(f"{'ticker':<12} {'source':<16} {'in_master':<10} {'name':<30} note")
    print("-" * 90)
    for r in results:
        print(
            f"{r.ticker:<12} {r.source:<16} {str(r.in_master):<10} "
            f"{r.name_preview[:28]:<30} {r.note}"
        )

    counts = Counter(r.source for r in results)
    print("\nSummary:")
    for src, cnt in sorted(counts.items()):
        print(f"  {src}: {cnt}")


def _print_live_table(results: list[LiveResult]) -> None:
    print("\n=== LIVE (actual get_company_name) ===")
    print(f"{'ticker':<12} {'source':<16} {'name':<30} note")
    print("-" * 80)
    for r in results:
        print(f"{r.ticker:<12} {r.source:<16} {r.name[:28]:<30} {r.note}")

    counts = Counter(r.source for r in results)
    print("\nSummary:")
    for src, cnt in sorted(counts.items()):
        print(f"  {src}: {cnt}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose get_company_name() code paths")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--predict", action="store_true", help="Predict path without API calls")
    mode.add_argument("--live", action="store_true", help="Run get_company_name")
    parser.add_argument("--ticker", help="Single ticker to test")
    parser.add_argument("--from-csv", action="store_true", help="Include trade_history.csv tickers")
    args = parser.parse_args()

    tickers = _collect_tickers(from_csv=args.from_csv, ticker=args.ticker)
    if not tickers:
        print("No tickers found.")
        return 1

    print(f"Tickers to check: {len(tickers)}")

    if args.predict:
        _print_predict_table([predict_source(t) for t in tickers])
        return 0

    results = [run_live(t) for t in tickers]
    _print_live_table(results)

    fallback = [r for r in results if r.source == "ticker_fallback"]
    if fallback:
        print("\n[!] product_master name missing for:")
        for r in fallback:
            print(f"  - {r.ticker}")
    else:
        print("\n[OK] All tickers resolved via product_master.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
