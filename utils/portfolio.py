import logging
import os
import time

import pandas as pd
import yfinance as yf

from utils import ls_t1101, ls_t2101
from utils.product_master import get_product

CSV_FILE = "data/trade_history.csv"
_NAME_CACHE = {}  # 종목명 캐싱용 딕셔너리
# LS t1101 응답 캐시 (동일 종목 연속 조회·Streamlit 재실행 시 과도한 API 방지)
_LS_T1101_CACHE = {}  # shcode -> (monotonic_ts, outblock dict | None)
_LS_T1101_CACHE_TTL_SEC = 60.0

logger = logging.getLogger(__name__)

# 노출통화: 환율(USD/KRW) 리스크 기준 — 거래 결제 통화(currency)와 별개
EXPOSURE_CURRENCY_OPTIONS = ("KRW", "USD")
# 자산군 (향후개발계획 1.2)
ASSET_CLASS_OPTIONS = ("지수형", "개별주식", "채권형", "선물")
# 기존 매매 마이그레이션 시 기본값 (요청사항)
LEGACY_DEFAULT_EXPOSURE_CURRENCY = "KRW"
LEGACY_DEFAULT_ASSET_CLASS = "지수형"
# 신규 매매 입력 시 자산군 기본값
NEW_TRADE_DEFAULT_ASSET_CLASS = "개별주식"


def _normalize_exposure_currency(val):
    if val is None or pd.isna(val):
        return LEGACY_DEFAULT_EXPOSURE_CURRENCY
    s = str(val).strip().upper()
    return "USD" if s == "USD" else "KRW"


def _normalize_asset_class(val):
    if val is None or pd.isna(val):
        return LEGACY_DEFAULT_ASSET_CLASS
    s = str(val).strip()
    return s if s in ASSET_CLASS_OPTIONS else LEGACY_DEFAULT_ASSET_CLASS




def _apply_futures_trade(q_old, cost_basis_krw, dq, price, multiplier=1.0):
    """
    선물: 매수 +dq(롱), 매도 -dq(숏). 양방향 포지션 가능.
    수량은 이미 multiplier가 반영된 상태.
    비용 계산: (거래량 × 가격)
    Returns: (new_quantity, new_cost_krw, realized_pnl_krw)
    """
    # 입력된 수량에 승수를 곱해서 실제 수량으로 변환
    dq_actual = dq * multiplier
    realized = 0.0
    
    if abs(q_old) < 1e-12:
        # 포지션이 없던 상태 → 새로 오픈
        return dq_actual, dq_actual * price, realized
    
    avg = cost_basis_krw / q_old
    
    if q_old * dq_actual > 0:
        # 같은 방향 추가 (롱에 롱 추가, 숏에 숏 추가)
        return q_old + dq_actual, cost_basis_krw + dq_actual * price, realized
    
    # 반대 방향 거래 (기존 포지션을 청산하는 경우)
    c = min(abs(q_old), abs(dq_actual))
    if q_old > 0:
        # 롱 포지션 청산 (매도)
        realized += (price - avg) * c
    else:
        # 숏 포지션 청산 (매수로 청산)
        realized += (avg - price) * c
    
    q_new = q_old + dq_actual
    if abs(q_new) < 1e-12:
        # 포지션 전부 청산
        return 0.0, 0.0, realized
    
    if (q_new > 0) == (q_old > 0):
        # 같은 방향으로 남음 (롱 또는 숏)
        return q_new, avg * q_new, realized
    
    # 반대 방향 포지션으로 전환
    return q_new, q_new * price, realized


def _is_future_ticker(ticker):
    """선물 여부 판별 (8자리 코드 or product_master에서 asset_class='선물')"""
    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str)
    return (product_info and product_info.get("asset_class") == "선물") or len(ticker_str) == 8




def load_trade_history():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(
            columns=[
                "date",
                "account",
                "ticker",
                "tradeType",
                "quantity",
                "price",
                "currency",
                "fx_krw_per_usd",
                "exposure_currency",
                "asset_class",
            ]
        )

    df = pd.read_csv(CSV_FILE)

    changed = False
    # 기존 데이터에 currency 컬럼이 없는 경우 추가 (기본값 USD)
    if "currency" not in df.columns:
        df["currency"] = "USD"
        changed = True

    # 기존 데이터에 account 컬럼이 없는 경우 추가 (기본값 기본계좌)
    if "account" not in df.columns:
        df["account"] = "기본계좌"
        changed = True

    # 매매 시점 USD/KRW 환율 (1 USD당 원화). KRW 거래는 1.0
    if "fx_krw_per_usd" not in df.columns:
        df["fx_krw_per_usd"] = pd.NA
        df.loc[df["currency"] == "KRW", "fx_krw_per_usd"] = 1.0
        changed = True

    if "exposure_currency" not in df.columns:
        df["exposure_currency"] = LEGACY_DEFAULT_EXPOSURE_CURRENCY
        changed = True
    if "asset_class" not in df.columns:
        df["asset_class"] = LEGACY_DEFAULT_ASSET_CLASS
        changed = True

    if "exposure_currency" in df.columns and df["exposure_currency"].isna().any():
        df["exposure_currency"] = df["exposure_currency"].fillna(
            LEGACY_DEFAULT_EXPOSURE_CURRENCY
        )
        changed = True
    if "asset_class" in df.columns and df["asset_class"].isna().any():
        df["asset_class"] = df["asset_class"].fillna(LEGACY_DEFAULT_ASSET_CLASS)
        changed = True

    if changed:
        df.to_csv(CSV_FILE, index=False)

    return df


def _normalize_fx_for_row(currency, fx_krw_per_usd, spot_fallback):
    """저장/표시용 환율. KRW는 1, USD는 입력값(없으면 조회 시점 환율로 대체)."""
    if currency == "KRW":
        return 1.0
    if fx_krw_per_usd is None or pd.isna(fx_krw_per_usd):
        return float(spot_fallback)
    return float(fx_krw_per_usd)


def add_trade(
    date,
    account,
    ticker,
    tradeType,
    quantity,
    price,
    currency="KRW",
    fx_krw_per_usd=None,
    exposure_currency=None,
    asset_class=None,
):
    df = load_trade_history()
    spot = get_exchange_rate()
    fx = _normalize_fx_for_row(currency, fx_krw_per_usd, spot)
    exp = _normalize_exposure_currency(exposure_currency)
    ac = _normalize_asset_class(asset_class or NEW_TRADE_DEFAULT_ASSET_CLASS)
    new_row = pd.DataFrame(
        [
            {
                "date": date,
                "account": account,
                "ticker": ticker.upper(),
                "tradeType": tradeType,
                "quantity": float(quantity),
                "price": float(price),
                "currency": currency,
                "fx_krw_per_usd": fx,
                "exposure_currency": exp,
                "asset_class": ac,
            }
        ]
    )
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)


def update_trade(
    index,
    date,
    account,
    ticker,
    tradeType,
    quantity,
    price,
    currency,
    fx_krw_per_usd=None,
    exposure_currency=None,
    asset_class=None,
):
    df = load_trade_history()
    if 0 <= index < len(df):
        spot = get_exchange_rate()
        fx = _normalize_fx_for_row(currency, fx_krw_per_usd, spot)
        exp = _normalize_exposure_currency(exposure_currency)
        ac = _normalize_asset_class(asset_class)
        df.loc[index, "date"] = date
        df.loc[index, "account"] = account
        df.loc[index, "ticker"] = ticker.upper()
        df.loc[index, "tradeType"] = tradeType
        df.loc[index, "quantity"] = float(quantity)
        df.loc[index, "price"] = float(price)
        df.loc[index, "currency"] = currency
        df.loc[index, "fx_krw_per_usd"] = fx
        df.loc[index, "exposure_currency"] = exp
        df.loc[index, "asset_class"] = ac
        df.to_csv(CSV_FILE, index=False)
        return True
    return False


def delete_trade(index):
    df = load_trade_history()
    if 0 <= index < len(df):
        df = df.drop(index)
        df.to_csv(CSV_FILE, index=False)
        return True
    return False


def _ls_shcode_from_ticker(ticker):
    """LS증권 6자리 종목코드. 국내 주식은 정수 문자열, ETF/ETN 등은 영숫자 혼합 6자리."""
    t = str(ticker).strip().upper()
    # 6자리 영숫자 (ETF 등) 또는 1~6자리 숫자 (일반 주식)
    if t.isalnum() and len(t) == 6:
        return t
    if t.isdigit() and 1 <= len(t) < 6:
        return t.zfill(6)
    return None


def _ls_price_to_float(outblock):
    if not outblock:
        return 0.0
    p = outblock.get("price")
    if p is None or p == "":
        return 0.0
    try:
        return float(str(p).replace(",", "").strip())
    except ValueError:
        return 0.0


def _ls_previous_close_to_float(outblock):
    """t1101 응답에서 전일 종가(jnilclose) 추출"""
    if not outblock:
        return 0.0
    p = outblock.get("jnilclose")
    if p is None or p == "":
        return 0.0
    try:
        return float(str(p).replace(",", "").strip())
    except ValueError:
        return 0.0


def _get_ls_t1101_cached(shcode):
    """t1101 호출 결과 캐시(짧은 TTL). 가격·종목명 조회를 한 번으로 묶기 위함.

    get_current_with_fallback()을 사용하여 자동 재시도 지원:
    1차 시도: shcode 그대로
    2차 시도: shcode.KS (일부 ETF 등이 필요)
    """
    now = time.monotonic()
    if shcode in _LS_T1101_CACHE:
        ts, data = _LS_T1101_CACHE[shcode]
        if now - ts < _LS_T1101_CACHE_TTL_SEC:
            return data

    data = ls_t1101.get_current_with_fallback(shcode)
    _LS_T1101_CACHE[shcode] = (now, data)
    return data


_LS_T2101_CACHE = {}  # shcode -> (monotonic_ts, outblock dict | None)


def _get_ls_t2101_cached(shcode):
    now = time.monotonic()
    if shcode in _LS_T2101_CACHE:
        ts, data = _LS_T2101_CACHE[shcode]
        if now - ts < _LS_T1101_CACHE_TTL_SEC:
            return data

    data = ls_t2101.get_future_current_price(shcode)
    _LS_T2101_CACHE[shcode] = (now, data)
    return data


def get_current_price(ticker):
    """현재가 조회. 국내: LS API → .KS 재시도 → 해외(yfinance)"""

    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str)
    is_future = (product_info and product_info.get("asset_class") == "선물") or len(
        ticker_str
    ) == 8

    if is_future:
        ob = _get_ls_t2101_cached(ticker_str)
        price = _ls_price_to_float(ob)
        if price > 0:
            return price

    shcode = _ls_shcode_from_ticker(ticker_str)
    if shcode:
        ob = _get_ls_t1101_cached(shcode)
        price = _ls_price_to_float(ob)
        if price > 0:  # 성공
            return price
        # LS API 실패 → 해외주식으로 처리

    try:
        # print(f"{ticker_str} is being retrieved from yfinance (LS API failed)")
        stock = yf.Ticker(ticker_str)
        todays_data = stock.history(period="1d")
        if not todays_data.empty:
            return float(todays_data["Close"].iloc[0])
        return 0.0
    except Exception as e:
        logger.warning("Error fetching price for %s: %s", ticker_str, e)
        return 0.0


def get_previous_close_price(ticker):
    """전일 종가 반환. 국내: LS API → .KS 재시도 → 해외(yfinance)"""

    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str)
    is_future = (product_info and product_info.get("asset_class") == "선물") or len(
        ticker_str
    ) == 8

    if is_future:
        ob = _get_ls_t2101_cached(ticker_str)
        price = _ls_previous_close_to_float(ob)
        if price > 0:
            return price

    shcode = _ls_shcode_from_ticker(ticker_str)
    if shcode:
        ob = _get_ls_t1101_cached(shcode)
        price = _ls_previous_close_to_float(ob)
        if price > 0:  # 성공
            return price
        # LS API 실패 → 해외주식으로 처리

    # yfinance로 해외주식 전일 종가 조회
    try:
        stock = yf.Ticker(ticker_str)
        hist = stock.history(period="5d")  # 5일 데이터로 전일자 가져오기
        if len(hist) >= 2:
            return float(hist["Close"].iloc[-2])  # 최신 바로 이전이 전일자
        return 0.0
    except Exception as e:
        logger.warning("Error fetching previous close for %s: %s", ticker_str, e)
        return 0.0


def get_company_name(ticker):
    """종목 코드로 회사 이름. product_master → 국내: LS API → .KS 재시도 → 해외(yfinance) → 코드 반환"""

    if ticker in _NAME_CACHE:
        return _NAME_CACHE[ticker]

    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str)
    
    # 1. product_master.json에서 name 필드 확인 (최우선)
    if product_info and product_info.get("name"):
        name = str(product_info["name"]).strip()
        if name:
            _NAME_CACHE[ticker] = name
            return name

    is_future = (product_info and product_info.get("asset_class") == "선물") or len(
        ticker_str
    ) == 8

    if is_future:
        ob = _get_ls_t2101_cached(ticker_str)
        if ob and ob.get("hname"):
            name = str(ob["hname"]).strip()
            _NAME_CACHE[ticker] = name
            return name

    shcode = _ls_shcode_from_ticker(ticker_str)
    if shcode:
        ob = _get_ls_t1101_cached(shcode)
        if ob and ob.get("hname"):
            name = str(ob["hname"]).strip()
            _NAME_CACHE[ticker] = name
            return name
        # LS API 실패 → 해외주식으로 처리

    try:
        stock = yf.Ticker(ticker_str)
        info = stock.info
        name = info.get("shortName") or info.get("longName") or ticker_str
    except Exception:
        name = ticker_str

    _NAME_CACHE[ticker] = name
    return name


def get_exchange_rate():
    try:
        # USD/KRW 환율 가져오기
        rate = yf.Ticker("USDKRW=X").history(period="1d")
        if not rate.empty:
            return rate["Close"].iloc[0]
        return 1300.0  # API 실패 시 임시 기본값
    except:
        return 1300.0


def calculate_portfolio(account_filter=None, tag_filter=None):
    df = load_trade_history()
    if df.empty:
        return pd.DataFrame()

    # 계좌 필터링 적용
    if account_filter and account_filter != "전체 계좌":
        df = df[df["account"] == account_filter]

    # 태그 필터링 적용
    if tag_filter and tag_filter != "전체 태그":
        # product_master에서 해당 태그를 가진 종목들의 티커를 가져옵니다.
        from utils.product_master import load_product_master
        products = load_product_master()
        tickers_with_tag = [
            t for t, info in products.items() 
            if "tags" in info and tag_filter in info["tags"]
        ]
        df = df[df["ticker"].isin(tickers_with_tag)]

    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.sort_values("date", kind="mergesort")

    spot = get_exchange_rate()
    portfolio = {}

    for _, row in df.iterrows():
        ticker = row["ticker"]
        tradeType = row["tradeType"]
        quantity = float(row["quantity"])
        price = float(row["price"])
        currency = row["currency"]
        fx = _normalize_fx_for_row(currency, row.get("fx_krw_per_usd"), spot)
        exp = _normalize_exposure_currency(row.get("exposure_currency"))
        ac = _normalize_asset_class(row.get("asset_class"))

        if ticker not in portfolio:
            portfolio[ticker] = {
                "currentQuantity": 0.0,
                "totalCostKrw": 0.0,
                "totalCostUsd": 0.0,
                "averageCost": 0.0,
                "averageCostKrw": 0.0,
                "realizedPnlKrw": 0.0,
                "currency": currency,
                "exposure_currency": exp,
                "asset_class": ac,
                "companyName": get_company_name(ticker),
                "tags": get_product(ticker).get("tags", []),
            }
        else:
            portfolio[ticker]["exposure_currency"] = exp
            portfolio[ticker]["asset_class"] = ac


        # 선물 처리 (양방향 포지션 가능)
        if _is_future_ticker(ticker):
            dq = quantity if tradeType in ["Buy", "매수"] else -quantity
            q_old = portfolio[ticker]["currentQuantity"]
            cost_old = portfolio[ticker]["totalCostKrw"]
            product_info = get_product(ticker)
            multiplier = float(product_info.get("multiplier", 1.0)) if product_info else 1.0
            
            qn, cn, r = _apply_futures_trade(q_old, cost_old, dq, price, multiplier)
            portfolio[ticker]["currentQuantity"] = qn
            portfolio[ticker]["totalCostKrw"] = cn
            portfolio[ticker]["totalCostUsd"] = 0.0
            portfolio[ticker]["realizedPnlKrw"] += r
            if abs(qn) > 1e-12:
                portfolio[ticker]["averageCost"] = cn / qn
                portfolio[ticker]["averageCostKrw"] = cn / qn
            else:
                portfolio[ticker]["averageCost"] = 0.0
                portfolio[ticker]["averageCostKrw"] = 0.0
            continue

        # 매수 처리 (한글/영문 모두 지원) - 선물 제외
        if tradeType in ["Buy", "매수"]:
            portfolio[ticker]["currentQuantity"] += quantity
            
            if currency == "KRW":
                portfolio[ticker]["totalCostKrw"] += quantity * price
                q = portfolio[ticker]["currentQuantity"]
                portfolio[ticker]["averageCost"] = portfolio[ticker]["totalCostKrw"] / q
                portfolio[ticker]["averageCostKrw"] = portfolio[ticker]["averageCost"]
            else:
                portfolio[ticker]["totalCostUsd"] += quantity * price
                portfolio[ticker]["totalCostKrw"] += quantity * price * fx
                q = portfolio[ticker]["currentQuantity"]
                portfolio[ticker]["averageCost"] = portfolio[ticker]["totalCostUsd"] / q
                portfolio[ticker]["averageCostKrw"] = (
                    portfolio[ticker]["totalCostKrw"] / q
                )

        # 매도 처리 (한글/영문 모두 지원) - 선물 제외
        elif tradeType in ["Sell", "매도"]:
            if portfolio[ticker]["currentQuantity"] < quantity:
                continue

            if currency == "KRW":
                avg_krw = portfolio[ticker]["averageCostKrw"]
                portfolio[ticker]["realizedPnlKrw"] += (price - avg_krw) * quantity
                portfolio[ticker]["totalCostKrw"] -= avg_krw * quantity
                portfolio[ticker]["currentQuantity"] -= quantity
                if portfolio[ticker]["currentQuantity"] == 0:
                    portfolio[ticker]["averageCost"] = 0.0
                    portfolio[ticker]["averageCostKrw"] = 0.0
                    portfolio[ticker]["totalCostKrw"] = 0.0
                else:
                    portfolio[ticker]["averageCost"] = (
                        portfolio[ticker]["totalCostKrw"]
                        / portfolio[ticker]["currentQuantity"]
                    )
                    portfolio[ticker]["averageCostKrw"] = portfolio[ticker][
                        "averageCost"
                    ]
            else:
                avg_usd = portfolio[ticker]["averageCost"]
                avg_krw = portfolio[ticker]["averageCostKrw"]
                proceeds_krw = fx * price * quantity
                cost_krw = avg_krw * quantity
                portfolio[ticker]["realizedPnlKrw"] += proceeds_krw - cost_krw
                portfolio[ticker]["totalCostUsd"] -= avg_usd * quantity
                portfolio[ticker]["totalCostKrw"] -= cost_krw
                portfolio[ticker]["currentQuantity"] -= quantity
                if portfolio[ticker]["currentQuantity"] == 0:
                    portfolio[ticker]["averageCost"] = 0.0
                    portfolio[ticker]["averageCostKrw"] = 0.0
                    portfolio[ticker]["totalCostUsd"] = 0.0
                    portfolio[ticker]["totalCostKrw"] = 0.0
                else:
                    q = portfolio[ticker]["currentQuantity"]
                    portfolio[ticker]["averageCost"] = (
                        portfolio[ticker]["totalCostUsd"] / q
                    )
                    portfolio[ticker]["averageCostKrw"] = (
                        portfolio[ticker]["totalCostKrw"] / q
                    )

    # 보유 수량이 있거나 실현 손익이 있는 종목만 필터링
    active_portfolio = {
        k: v
        for k, v in portfolio.items()
        if abs(v["currentQuantity"]) > 1e-12 or v["realizedPnlKrw"] != 0
    }

    if not active_portfolio:
        return pd.DataFrame()

    result_df = pd.DataFrame.from_dict(active_portfolio, orient="index").reset_index()
    result_df.rename(columns={"index": "ticker"}, inplace=True)

    # 현재가 가져오기 (보유 수량이 있는 경우만)
    def get_price_if_active(row):
        if abs(row["currentQuantity"]) > 1e-12:
            return get_current_price(row["ticker"])
        return 0.0

    result_df["currentPrice"] = result_df.apply(get_price_if_active, axis=1)

    # 평가 금액(표시 통화) 및 원화 기준 지표
    def row_current_value_local(r):
        return r["currentQuantity"] * r["currentPrice"]

    result_df["currentValue"] = result_df.apply(row_current_value_local, axis=1)

    def row_current_value_krw(r):
        if r["asset_class"] == "선물":
            return 0.0
        if r["currency"] == "USD":
            return r["currentQuantity"] * r["currentPrice"] * spot
        return r["currentValue"]

    result_df["currentValueKrw"] = result_df.apply(row_current_value_krw, axis=1)

    def row_unrealized_local(r):
        if abs(r["currentQuantity"]) < 1e-12:
            return 0.0
        return (r["currentPrice"] - r["averageCost"]) * r["currentQuantity"]

    result_df["unrealizedPnl"] = result_df.apply(row_unrealized_local, axis=1)

    def row_unrealized_krw(r):
        if abs(r["currentQuantity"]) < 1e-12:
            return 0.0


        if r["asset_class"] == "선물":
            # 선물: 수량이 이미 승수가 반영됨
            return (r["currentPrice"] - r["averageCostKrw"]) * r["currentQuantity"]
            
        if r["currency"] == "USD":
            return r["currentValueKrw"] - r["totalCostKrw"]
            
        return r["unrealizedPnl"]

    result_df["unrealizedPnlKrw"] = result_df.apply(row_unrealized_krw, axis=1)

    result_df["realizedPnlKrw"] = result_df["realizedPnlKrw"].astype(float)

    def row_return_local(r):
        if abs(r["currentQuantity"]) < 1e-12 or abs(r["averageCost"]) < 1e-12:
            return 0.0
        if r["asset_class"] == "선물":
            return 0.0
        return (r["currentPrice"] - r["averageCost"]) / r["averageCost"] * 100

    result_df["returnRate"] = result_df.apply(row_return_local, axis=1)

    def row_return_krw(r):
        if abs(r["currentQuantity"]) < 1e-12:
            return 0.0
        if r["asset_class"] == "선물":
            return 0.0
        base = r["totalCostKrw"]
        if base <= 0:
            return 0.0
        return r["unrealizedPnlKrw"] / base * 100

    result_df["returnRateKrw"] = result_df.apply(row_return_krw, axis=1)

    # 원래 통화 모드용 실현손익: KRW 종목은 원화, USD 종목은 대략적인 USD(현재 환율로 환산)
    def row_realized_local(r):
        if r["currency"] == "KRW":
            return float(r["realizedPnlKrw"])
        return float(r["realizedPnlKrw"]) / spot if spot else 0.0

    result_df["realizedPnl"] = result_df.apply(row_realized_local, axis=1)

    # 전일 평가손익 계산 (현재 보유 수량 기준)
    def row_prev_close_price(r):
        return get_previous_close_price(r["ticker"])

    result_df["previousClosePrice"] = result_df.apply(row_prev_close_price, axis=1)

    # 전일 평가손익 (원화 기준) - 현재 보유 수량으로 전일 가격 계산
    def row_prev_unrealized_krw(r):
        if abs(r["currentQuantity"]) < 1e-12:
            return 0.0

        if r["asset_class"] == "선물":
            # 선물: 수량이 이미 승수가 반영됨
            return (r["previousClosePrice"] - r["averageCostKrw"]) * r["currentQuantity"]
            
        if r["currency"] == "USD":
            prev_value_krw = r["previousClosePrice"] * spot
            return (prev_value_krw - r["averageCostKrw"]) * r["currentQuantity"]
        else:
            return (r["previousClosePrice"] - r["averageCost"]) * r["currentQuantity"]

    result_df["prevUnrealizedPnlKrw"] = result_df.apply(row_prev_unrealized_krw, axis=1)

    # 전일대비 평가손익 변동 (오늘 - 어제)
    def row_pnl_change_krw(r):
        return r["unrealizedPnlKrw"] - r["prevUnrealizedPnlKrw"]

    result_df["pnlChangeKrw"] = result_df.apply(row_pnl_change_krw, axis=1)

    # 전일대비 변동률 (%) - 가격 변동률 기준: (현재가 / 전일가 - 1) * 100
    def row_pnl_change_rate(r):
        if abs(r["previousClosePrice"]) < 1e-12:
            return 0.0
        return ((r["currentPrice"] / r["previousClosePrice"]) - 1.0) * 100

    result_df["pnlChangeRate"] = result_df.apply(row_pnl_change_rate, axis=1)

    # USDKRW(선물·헤지): 평가「금액」만 0으로 두어 총자산·비중·차트에 반영하지 않음.
    # 평가손익은 MTM 그대로, 수익률은 의미 없어 0% 표시.
    
    # 선물 포지션도 평가「금액」만 0으로 (명목 가치를 자산에서 제외)
    _futures = result_df["asset_class"] == "선물"
    result_df.loc[_futures, "currentValue"] = 0.0
    result_df.loc[_futures, "currentValueKrw"] = 0.0
    result_df.loc[_futures, "returnRate"] = 0.0
    result_df.loc[_futures, "returnRateKrw"] = 0.0

    result_df = result_df.drop(
        columns=["totalCostKrw", "totalCostUsd"], errors="ignore"
    )

    return result_df
