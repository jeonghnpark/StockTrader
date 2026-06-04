import logging
import os
import time
from datetime import datetime

import pandas as pd
import yfinance as yf

from utils import ls_t1101, ls_t2111, ls_g3101, ls_g3106
from utils.product_master import get_product

CSV_FILE = "data/trade_history.csv"
_NAME_CACHE = {}  # 종목명 캐싱용 딕셔너리
# LS t1101 응답 캐시 (동일 종목 연속 조회·Streamlit 재실행 시 과도한 API 방지)
_LS_T1101_CACHE = {}  # shcode -> (monotonic_ts, outblock dict | None)
_LS_T1101_CACHE_TTL_SEC = 30.0
_LS_G3101_CACHE = {}  # symbol -> (ts, data)
_LS_G3101_CACHE_TTL_SEC = 30.0
_LS_G3106_CACHE = {}  # symbol -> (ts, data)
_LS_G3106_CACHE_TTL_SEC = 30.0
# 티커별 (현재가, 전일가) — 동일 OutBlock에서 한 번에 추출
_QUOTE_CACHE = {}  # ticker -> (monotonic_ts, (current, previous_close))
_QUOTE_CACHE_TTL_SEC = 30.0

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
    return (product_info and product_info.get("asset_class") == "선물") or len(
        ticker_str
    ) == 8


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
    
    # date 컬럼을 datetime으로 파싱
    df["date"] = pd.to_datetime(df["date"], errors="coerce")

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
    trade_time=None,
):
    df = load_trade_history()
    spot = get_exchange_rate()
    fx = _normalize_fx_for_row(currency, fx_krw_per_usd, spot)
    exp = _normalize_exposure_currency(exposure_currency)
    ac = _normalize_asset_class(asset_class or NEW_TRADE_DEFAULT_ASSET_CLASS)
    
    # date가 datetime 객체인지 date 객체인지 확인해서 datetime으로 통일
    if isinstance(date, str):
        datetime_obj = pd.to_datetime(date)
    else:
        datetime_obj = pd.to_datetime(date)
    
    # 시간 정보가 없으면 현재 시간 추가
    if trade_time is None:
        now = datetime.now()
        datetime_obj = datetime_obj.replace(
            hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond
        )
    else:
        # trade_time이 제공되면 datetime 객체에서 시간 정보 추출해서 병합
        from datetime import time as time_type
        
        if isinstance(trade_time, datetime):
            # datetime 객체인 경우
            datetime_obj = datetime_obj.replace(
                hour=trade_time.hour,
                minute=trade_time.minute,
                second=trade_time.second,
                microsecond=trade_time.microsecond
            )
        elif isinstance(trade_time, time_type):
            # time 객체인 경우 (app.py에서 전달)
            datetime_obj = datetime_obj.replace(
                hour=trade_time.hour,
                minute=trade_time.minute,
                second=trade_time.second,
                microsecond=trade_time.microsecond
            )
        else:
            # 문자열인 경우
            time_obj = pd.to_datetime(trade_time).time()
            datetime_obj = datetime_obj.replace(
                hour=time_obj.hour,
                minute=time_obj.minute,
                second=time_obj.second,
                microsecond=time_obj.microsecond
            )
    
    new_row = pd.DataFrame(
        [
            {
                "date": datetime_obj,
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
    trade_time=None,
):
    df = load_trade_history()
    if 0 <= index < len(df):
        spot = get_exchange_rate()
        fx = _normalize_fx_for_row(currency, fx_krw_per_usd, spot)
        exp = _normalize_exposure_currency(exposure_currency)
        ac = _normalize_asset_class(asset_class)
        
        # date를 datetime으로 통일
        if isinstance(date, str):
            datetime_obj = pd.to_datetime(date)
        else:
            datetime_obj = pd.to_datetime(date)
        
        # 시간 정보 처리
        if trade_time is None:
            # 기존 시간 정보가 있으면 유지, 없으면 현재 시간
            existing_datetime = pd.to_datetime(df.loc[index, "date"])
            if pd.notna(existing_datetime) and existing_datetime.time() != datetime.min.time():
                datetime_obj = datetime_obj.replace(
                    hour=existing_datetime.hour,
                    minute=existing_datetime.minute,
                    second=existing_datetime.second,
                    microsecond=existing_datetime.microsecond
                )
            else:
                now = datetime.now()
                datetime_obj = datetime_obj.replace(
                    hour=now.hour, minute=now.minute, second=now.second, microsecond=now.microsecond
                )
        else:
            from datetime import time as time_type
            
            if isinstance(trade_time, datetime):
                datetime_obj = datetime_obj.replace(
                    hour=trade_time.hour,
                    minute=trade_time.minute,
                    second=trade_time.second,
                    microsecond=trade_time.microsecond
                )
            elif isinstance(trade_time, time_type):
                # time 객체인 경우 (app.py에서 전달)
                datetime_obj = datetime_obj.replace(
                    hour=trade_time.hour,
                    minute=trade_time.minute,
                    second=trade_time.second,
                    microsecond=trade_time.microsecond
                )
            else:
                # 문자열인 경우
                time_obj = pd.to_datetime(trade_time).time()
                datetime_obj = datetime_obj.replace(
                    hour=time_obj.hour,
                    minute=time_obj.minute,
                    second=time_obj.second,
                    microsecond=time_obj.microsecond
                )
        
        df.loc[index, "date"] = datetime_obj
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
    """LS API 응답에서 전일 종가(jnilclose) 추출"""
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


def _get_ls_g3101_cached(symbol):
    now = time.monotonic()
    if symbol in _LS_G3101_CACHE:
        ts, data = _LS_G3101_CACHE[symbol]
        if now - ts < _LS_G3101_CACHE_TTL_SEC:
            return data
    data = ls_g3101.get_current(symbol)
    _LS_G3101_CACHE[symbol] = (now, data)
    return data


def _get_ls_g3106_cached(symbol, exchange="NASDAQ"):
    now = time.monotonic()
    cache_key = f"{symbol}_{exchange}"
    if cache_key in _LS_G3106_CACHE:
        ts, data = _LS_G3106_CACHE[cache_key]
        if now - ts < _LS_G3106_CACHE_TTL_SEC:
            return data
    data = ls_g3106.get_current(symbol, exchange=exchange)
    _LS_G3106_CACHE[cache_key] = (now, data)
    return data


def _get_ls_t2101_cached(shcode):
    """
    t2111 선물 API 캐시
    """
    now = time.monotonic()
    if shcode in _LS_T2101_CACHE:
        ts, data = _LS_T2101_CACHE[shcode]
        if now - ts < _LS_T1101_CACHE_TTL_SEC:
            return data

    # t2111로 직접 조회
    data = ls_t2111.get_future_current_price(shcode)
    _LS_T2101_CACHE[shcode] = (now, data)
    return data


def _get_quote_outblock_from_product(ticker_str: str, product_info: dict):
    """product_master 기준으로 시세 OutBlock 1회 조회."""
    market = product_info.get("market", "").upper()
    asset_class = product_info.get("asset_class", "")

    if market == "KRX":
        if asset_class == "선물":
            return _get_ls_t2101_cached(ticker_str)
        shcode = _ls_shcode_from_ticker(ticker_str)
        if shcode:
            return _get_ls_t1101_cached(shcode)
        return None

    if market in ("NYSE", "NASDAQ"):
        try:
            return _get_ls_g3106_cached(ticker_str, exchange=market)
        except Exception as e:
            logger.warning(
                "LS g3106 error for %s (%s): %s", ticker_str, market, e
            )
        return None

    return None


def _get_quote_outblock_heuristic(ticker_str: str):
    """product_master 없을 때 티커 형식으로 시세 API 추정 (새 종목 입력용).

    - 8자리 영숫자: 국내 선물 (t2111)
    - 6자리(또는 1~5자리 숫자): 국내 주식/ETF (t1101)
    - 알파벳만: 해외 주식 (g3106, NASDAQ → NYSE 순)
    """
    t = str(ticker_str).strip().upper()
    if not t:
        return None

    if len(t) == 8 and t.isalnum():
        ob = _get_ls_t2101_cached(t)
        if ob:
            return ob

    shcode = _ls_shcode_from_ticker(t)
    if shcode:
        ob = _get_ls_t1101_cached(shcode)
        if ob:
            return ob

    if t.isalpha():
        for exchange in ("NASDAQ", "NYSE"):
            try:
                ob = _get_ls_g3106_cached(t, exchange=exchange)
                if ob and _ls_price_to_float(ob) > 0:
                    return ob
            except Exception as e:
                logger.warning(
                    "LS g3106 heuristic error for %s (%s): %s", t, exchange, e
                )

    return None


def _get_quote_outblock(ticker_str: str, product_info: dict):
    """product_master 우선, 없거나 실패 시 티커 형식 휴리스틱 폴백."""
    if product_info:
        ob = _get_quote_outblock_from_product(ticker_str, product_info)
        if ob:
            return ob
    return _get_quote_outblock_heuristic(ticker_str)


def get_quote(ticker):
    """현재가·전일 종가를 한 번의 API(또는 캐시) 조회로 반환.

    Returns:
        tuple[float, float]: (current_price, previous_close_price)
    """
    ticker_str = str(ticker).strip().upper()
    now = time.monotonic()
    if ticker_str in _QUOTE_CACHE:
        ts, quote = _QUOTE_CACHE[ticker_str]
        if now - ts < _QUOTE_CACHE_TTL_SEC:
            return quote

    product_info = get_product(ticker_str)
    ob = _get_quote_outblock(ticker_str, product_info)

    if ob:
        current = _ls_price_to_float(ob)
        previous = _ls_previous_close_to_float(ob)
        if current < 0:
            current = 0.0
        if previous < 0:
            previous = 0.0
        quote = (current, previous)
    else:
        logger.warning(
            "No valid quote source for %s (master=%s), returning (0.0, 0.0)",
            ticker_str,
            bool(product_info),
        )
        quote = (0.0, 0.0)

    _QUOTE_CACHE[ticker_str] = (now, quote)
    return quote


def get_current_price(ticker):
    """현재가 조회. get_quote() 사용 (동일 티커는 전일가와 API 1회 공유)."""
    return get_quote(ticker)[0]


def get_previous_close_price(ticker):
    """전일 종가 조회. get_quote() 사용 (동일 티커는 현재가와 API 1회 공유)."""
    return get_quote(ticker)[1]


def prefetch_quotes(tickers):
    """여러 티커의 (현재가, 전일가)를 티커당 get_quote 1회로 조회.

    Returns:
        dict[str, tuple[float, float]]: ticker -> (current_price, previous_close_price)
    """
    unique = sorted({str(t).strip().upper() for t in tickers if t})
    return {t: get_quote(t) for t in unique}


def _company_name_from_outblock(outblock):
    """LS 시세 OutBlock에서 종목명 추출 (t1101 hname, g3106 korname 등)."""
    if not outblock:
        return None
    for key in ("hname", "korname", "name"):
        val = outblock.get(key)
        if val is not None:
            s = str(val).strip()
            if s:
                return s
    return None


def _get_company_name_from_api(ticker_str: str, product_info: dict):
    """시세 API OutBlock에서 종목명 조회 (캐시된 quote 경로 재사용)."""
    ob = _get_quote_outblock(ticker_str, product_info or {})
    name = _company_name_from_outblock(ob)
    if name:
        return name

    # 해외: 가격이 0이어도 korname만 있을 수 있음
    if str(ticker_str).strip().upper().isalpha():
        for exchange in ("NASDAQ", "NYSE"):
            try:
                ob = _get_ls_g3106_cached(ticker_str, exchange=exchange)
                name = _company_name_from_outblock(ob)
                if name:
                    return name
            except Exception as e:
                logger.warning(
                    "LS g3106 name lookup error for %s (%s): %s",
                    ticker_str,
                    exchange,
                    e,
                )
    return None


def get_company_name(ticker):
    """종목명: product_master → LS API(휴리스틱) → 티커 코드."""

    if ticker in _NAME_CACHE:
        return _NAME_CACHE[ticker]

    ticker_str = str(ticker).strip().upper()
    product_info = get_product(ticker_str)

    master_name = ""
    if product_info:
        master_name = str(product_info.get("name", "") or "").strip()
    # master에 유효한 종목명이 있고 티커와 다를 때만 사용
    if master_name and master_name != ticker_str:
        _NAME_CACHE[ticker] = master_name
        return master_name

    api_name = _get_company_name_from_api(ticker_str, product_info)
    if api_name:
        _NAME_CACHE[ticker] = api_name
        return api_name

    _NAME_CACHE[ticker] = ticker_str
    return ticker_str


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
            t
            for t, info in products.items()
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
            multiplier = (
                float(product_info.get("multiplier", 1.0)) if product_info else 1.0
            )

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

    # 티커별 시세 1회 조회 (현재가·전일가 동시 추출, 캐시 공유)
    quote_by_ticker = prefetch_quotes(result_df["ticker"])

    def _current_price_for_row(row):
        if abs(row["currentQuantity"]) < 1e-12:
            return 0.0
        return quote_by_ticker[row["ticker"]][0]

    result_df["currentPrice"] = result_df.apply(_current_price_for_row, axis=1)
    result_df["previousClosePrice"] = result_df["ticker"].map(
        lambda t: quote_by_ticker[t][1]
    )

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

    # 전일 평가손익 (previousClosePrice는 위 quote_by_ticker에서 이미 설정됨)
    def row_prev_unrealized_krw(r):
        if abs(r["currentQuantity"]) < 1e-12:
            return 0.0

        if r["asset_class"] == "선물":
            # 선물: 수량이 이미 승수가 반영됨
            return (r["previousClosePrice"] - r["averageCostKrw"]) * r[
                "currentQuantity"
            ]

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


def validate_trade(ticker, trade_type, quantity, account_filter=None):
    """
    거래 가능 여부를 검증한다.
    
    Args:
        ticker: 종목 코드
        trade_type: 매수(매수) 또는 매도(매도)
        quantity: 거래 수량
        account_filter: 계좌 필터 (None이면 전체)
    
    Returns:
        (is_valid, error_message)
        - is_valid: True면 거래 가능, False면 거래 불가
        - error_message: 에러 메시지 (거래 가능하면 빈 문자열)
    """
    # 선물은 양방향 거래 가능 - 검증 필요 없음
    if _is_future_ticker(ticker):
        return True, ""
    
    # 주식/ETF: 매수는 항상 가능
    if trade_type in ["Buy", "매수"]:
        return True, ""
    
    # 매도인 경우 보유 수량 확인
    if trade_type in ["Sell", "매도"]:
        portfolio_df = calculate_portfolio(account_filter=account_filter)
        
        # 포트폴리오가 비어있거나 해당 종목이 없는 경우
        if portfolio_df.empty:
            return False, f"⚠️ [{ticker}] 보유 수량이 없어서 매도할 수 없습니다."
        
        # 해당 종목의 보유 수량 확인
        ticker_rows = portfolio_df[portfolio_df["ticker"] == ticker]
        if ticker_rows.empty:
            return False, f"⚠️ [{ticker}] 보유 수량이 없어서 매도할 수 없습니다."
        
        holding_quantity = ticker_rows.iloc[0].get("currentQuantity", 0)
        
        if holding_quantity < quantity:
            return (
                False,
                f"⚠️ [{ticker}] 매도 수량 초과!\n"
                f"   보유: {holding_quantity:,.0f}주\n"
                f"   시도: {quantity:,.0f}주"
            )
    
    return True, ""
