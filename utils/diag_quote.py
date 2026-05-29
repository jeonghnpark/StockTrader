"""
get_quote / prefetch_quotes API 호출 횟수 진단.

프로젝트 루트에서:
  python utils/diag_quote.py
  python utils/diag_quote.py --ticker TSLA --ticker NVDA
"""

from __future__ import annotations

import argparse
import sys
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from utils import portfolio  # noqa: E402
from utils.portfolio import (  # noqa: E402
    get_current_price,
    get_previous_close_price,
    prefetch_quotes,
)
from utils.product_master import load_product_master  # noqa: E402


class ApiCallCounter:
    t1101 = 0
    t2101 = 0
    g3106 = 0

    def reset(self) -> None:
        self.t1101 = 0
        self.t2101 = 0
        self.g3106 = 0

    @property
    def total(self) -> int:
        return self.t1101 + self.t2101 + self.g3106


def _clear_caches() -> None:
    portfolio._QUOTE_CACHE.clear()
    portfolio._LS_T1101_CACHE.clear()
    portfolio._LS_T2101_CACHE.clear()
    portfolio._LS_G3106_CACHE.clear()
    portfolio._LS_G3101_CACHE.clear()


@contextmanager
def _track_api_calls(counter: ApiCallCounter):
    def wrap(name: str, original):
        def wrapper(*args, **kwargs):
            setattr(counter, name, getattr(counter, name) + 1)
            return original(*args, **kwargs)

        return wrapper

    with patch.object(
        portfolio,
        "_get_ls_t1101_cached",
        wrap("t1101", portfolio._get_ls_t1101_cached),
    ), patch.object(
        portfolio,
        "_get_ls_t2101_cached",
        wrap("t2101", portfolio._get_ls_t2101_cached),
    ), patch.object(
        portfolio,
        "_get_ls_g3106_cached",
        wrap("g3106", portfolio._get_ls_g3106_cached),
    ):
        yield


def run_scenario(tickers: list[str], label: str) -> None:
    n = len(tickers)

    counter_old = ApiCallCounter()
    _clear_caches()
    with _track_api_calls(counter_old):
        for t in tickers:
            get_current_price(t)
            get_previous_close_price(t)

    counter_new = ApiCallCounter()
    _clear_caches()
    with _track_api_calls(counter_new):
        quotes = prefetch_quotes(tickers)
        for t in tickers:
            cur, prev = quotes[t]
            assert cur >= 0 and prev >= 0

    print(f"\n=== {label} ({n} tickers) ===")
    print(
        f"  OLD (get_current + get_previous each): API calls = {counter_old.total} "
        f"(t1101={counter_old.t1101} t2101={counter_old.t2101} g3106={counter_old.g3106})"
    )
    print(
        f"  NEW (prefetch_quotes):                 API calls = {counter_new.total} "
        f"(t1101={counter_new.t1101} t2101={counter_new.t2101} g3106={counter_new.g3106})"
    )
    if counter_new.total <= n:
        print("  [OK] New path: at most 1 API call per ticker.")
    else:
        print("  [!] New path: more API calls than tickers.")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", action="append", help="Ticker(s) to test")
    args = parser.parse_args()

    if args.ticker:
        tickers = [t.strip().upper() for t in args.ticker]
    else:
        tickers = sorted(load_product_master().keys())[:5]

    if not tickers:
        print("No tickers.")
        return 1

    run_scenario(tickers, "sample")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
