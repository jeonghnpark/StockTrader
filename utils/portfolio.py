import pandas as pd
import yfinance as yf
import os
import urllib.request
import re

CSV_FILE = "data/trade_history.csv"
_NAME_CACHE = {} # 종목명 캐싱용 딕셔너리

# 노출통화: 환율(USD/KRW) 리스크 기준 — 거래 결제 통화(currency)와 별개
EXPOSURE_CURRENCY_OPTIONS = ("KRW", "USD")
# 자산군 (향후개발계획 1.2)
ASSET_CLASS_OPTIONS = ("지수형", "개별주식", "채권형")
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
        df["exposure_currency"] = df["exposure_currency"].fillna(LEGACY_DEFAULT_EXPOSURE_CURRENCY)
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

def get_current_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        # Fast way to get current price
        todays_data = stock.history(period='1d')
        if not todays_data.empty:
            return todays_data['Close'].iloc[0]
        return 0.0
    except Exception as e:
        print(f"Error fetching price for {ticker}: {e}")
        return 0.0

def get_korean_company_name(ticker):
    """네이버 금융을 통해 한국 주식의 한글 종목명을 가져옵니다."""
    try:
        code = ticker.split('.')[0]
        url = f"https://finance.naver.com/item/main.naver?code={code}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req) as response:
            html = response.read().decode('utf-8', errors='ignore')
            # <title>삼성전자 : Npay 증권</title> 형태에서 이름 추출
            match = re.search(r'<title>(.*?)\s*:', html)
            if match:
                return match.group(1).strip()
    except Exception as e:
        print(f"Error fetching Korean name for {ticker}: {e}")
    return None

def get_company_name(ticker):
    """종목 코드로 회사 이름을 가져옵니다. (캐싱 적용)"""
    if ticker in _NAME_CACHE:
        return _NAME_CACHE[ticker]
    
    name = None
    
    # 한국 주식인 경우 네이버 금융에서 한글명 조회 시도
    if ticker.endswith('.KS') or ticker.endswith('.KQ'):
        name = get_korean_company_name(ticker)
        
    # 한글명 조회가 실패했거나 해외 주식인 경우 yfinance 사용
    if not name:
        try:
            stock = yf.Ticker(ticker)
            info = stock.info
            # shortName이 없으면 longName, 둘 다 없으면 ticker 반환
            name = info.get('shortName') or info.get('longName') or ticker
        except Exception:
            # API 호출 실패 시 ticker 자체를 이름으로 사용
            name = ticker
            
    _NAME_CACHE[ticker] = name
    return name

def get_exchange_rate():
    try:
        # USD/KRW 환율 가져오기
        rate = yf.Ticker("USDKRW=X").history(period='1d')
        if not rate.empty:
            return rate['Close'].iloc[0]
        return 1300.0 # API 실패 시 임시 기본값
    except:
        return 1300.0

def calculate_portfolio(account_filter=None):
    df = load_trade_history()
    if df.empty:
        return pd.DataFrame()

    # 계좌 필터링 적용
    if account_filter and account_filter != "전체 계좌":
        df = df[df["account"] == account_filter]

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
            }
        else:
            portfolio[ticker]["exposure_currency"] = exp
            portfolio[ticker]["asset_class"] = ac

        # 매수 처리 (한글/영문 모두 지원)
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
                portfolio[ticker]["averageCostKrw"] = portfolio[ticker]["totalCostKrw"] / q

        # 매도 처리 (한글/영문 모두 지원)
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
                    portfolio[ticker]["averageCost"] = portfolio[ticker]["totalCostKrw"] / portfolio[ticker]["currentQuantity"]
                    portfolio[ticker]["averageCostKrw"] = portfolio[ticker]["averageCost"]
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
                    portfolio[ticker]["averageCost"] = portfolio[ticker]["totalCostUsd"] / q
                    portfolio[ticker]["averageCostKrw"] = portfolio[ticker]["totalCostKrw"] / q

    # 보유 수량이 있거나 실현 손익이 있는 종목만 필터링
    active_portfolio = {
        k: v
        for k, v in portfolio.items()
        if v["currentQuantity"] > 0 or v["realizedPnlKrw"] != 0
    }

    if not active_portfolio:
        return pd.DataFrame()

    result_df = pd.DataFrame.from_dict(active_portfolio, orient="index").reset_index()
    result_df.rename(columns={"index": "ticker"}, inplace=True)

    # 현재가 가져오기 (보유 수량이 있는 경우만)
    def get_price_if_active(row):
        if row["currentQuantity"] > 0:
            return get_current_price(row["ticker"])
        return 0.0

    result_df["currentPrice"] = result_df.apply(get_price_if_active, axis=1)

    # 평가 금액(표시 통화) 및 원화 기준 지표
    def row_current_value_local(r):
        return r["currentQuantity"] * r["currentPrice"]

    result_df["currentValue"] = result_df.apply(row_current_value_local, axis=1)

    def row_current_value_krw(r):
        if r["currency"] == "USD":
            return r["currentQuantity"] * r["currentPrice"] * spot
        return r["currentValue"]

    result_df["currentValueKrw"] = result_df.apply(row_current_value_krw, axis=1)

    def row_unrealized_local(r):
        if r["currentQuantity"] <= 0:
            return 0.0
        return (r["currentPrice"] - r["averageCost"]) * r["currentQuantity"]

    result_df["unrealizedPnl"] = result_df.apply(row_unrealized_local, axis=1)

    def row_unrealized_krw(r):
        if r["currentQuantity"] <= 0:
            return 0.0
        if r["currency"] == "USD":
            return r["currentValueKrw"] - r["totalCostKrw"]
        return r["unrealizedPnl"]

    result_df["unrealizedPnlKrw"] = result_df.apply(row_unrealized_krw, axis=1)

    result_df["realizedPnlKrw"] = result_df["realizedPnlKrw"].astype(float)

    def row_return_local(r):
        if r["averageCost"] <= 0 or r["currentQuantity"] <= 0:
            return 0.0
        return (r["currentPrice"] - r["averageCost"]) / r["averageCost"] * 100

    result_df["returnRate"] = result_df.apply(row_return_local, axis=1)

    def row_return_krw(r):
        base = r["totalCostKrw"]
        if base <= 0 or r["currentQuantity"] <= 0:
            return 0.0
        return r["unrealizedPnlKrw"] / base * 100

    result_df["returnRateKrw"] = result_df.apply(row_return_krw, axis=1)

    # 원래 통화 모드용 실현손익: KRW 종목은 원화, USD 종목은 대략적인 USD(현재 환율로 환산)
    def row_realized_local(r):
        if r["currency"] == "KRW":
            return float(r["realizedPnlKrw"])
        return float(r["realizedPnlKrw"]) / spot if spot else 0.0

    result_df["realizedPnl"] = result_df.apply(row_realized_local, axis=1)

    result_df = result_df.drop(columns=["totalCostKrw", "totalCostUsd"], errors="ignore")

    return result_df
