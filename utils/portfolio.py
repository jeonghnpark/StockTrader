import pandas as pd
import yfinance as yf
import os
import urllib.request
import re

CSV_FILE = "data/trade_history.csv"
_NAME_CACHE = {} # 종목명 캐싱용 딕셔너리

def load_trade_history():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=["date", "account", "ticker", "tradeType", "quantity", "price", "currency"])
    
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
        
    if changed:
        df.to_csv(CSV_FILE, index=False)
        
    return df

def add_trade(date, account, ticker, tradeType, quantity, price, currency="KRW"):
    df = load_trade_history()
    new_row = pd.DataFrame([{
        "date": date,
        "account": account,
        "ticker": ticker.upper(),
        "tradeType": tradeType,
        "quantity": float(quantity),
        "price": float(price),
        "currency": currency
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

def update_trade(index, date, account, ticker, tradeType, quantity, price, currency):
    df = load_trade_history()
    if 0 <= index < len(df):
        df.loc[index, "date"] = date
        df.loc[index, "account"] = account
        df.loc[index, "ticker"] = ticker.upper()
        df.loc[index, "tradeType"] = tradeType
        df.loc[index, "quantity"] = float(quantity)
        df.loc[index, "price"] = float(price)
        df.loc[index, "currency"] = currency
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
        df = df[df['account'] == account_filter]

    if df.empty:
        return pd.DataFrame()

    portfolio = {}

    for _, row in df.iterrows():
        ticker = row['ticker']
        tradeType = row['tradeType']
        quantity = row['quantity']
        price = row['price']
        currency = row['currency']

        if ticker not in portfolio:
            portfolio[ticker] = {
                "currentQuantity": 0.0,
                "totalCost": 0.0,
                "averageCost": 0.0,
                "realizedPnl": 0.0,
                "currency": currency,
                "companyName": get_company_name(ticker) # 종목명 추가
            }

        # 매수 처리 (한글/영문 모두 지원)
        if tradeType in ['Buy', '매수']:
            portfolio[ticker]['currentQuantity'] += quantity
            portfolio[ticker]['totalCost'] += quantity * price
            if portfolio[ticker]['currentQuantity'] > 0:
                portfolio[ticker]['averageCost'] = portfolio[ticker]['totalCost'] / portfolio[ticker]['currentQuantity']
        
        # 매도 처리 (한글/영문 모두 지원)
        elif tradeType in ['Sell', '매도']:
            if portfolio[ticker]['currentQuantity'] >= quantity:
                # 실현 손익 = (매도단가 - 평균단가) * 수량
                pnl = (price - portfolio[ticker]['averageCost']) * quantity
                portfolio[ticker]['realizedPnl'] += pnl
                
                portfolio[ticker]['currentQuantity'] -= quantity
                portfolio[ticker]['totalCost'] -= portfolio[ticker]['averageCost'] * quantity
                
                if portfolio[ticker]['currentQuantity'] == 0:
                    portfolio[ticker]['averageCost'] = 0.0
                    portfolio[ticker]['totalCost'] = 0.0

    # 보유 수량이 있거나 실현 손익이 있는 종목만 필터링
    active_portfolio = {k: v for k, v in portfolio.items() if v['currentQuantity'] > 0 or v['realizedPnl'] != 0}
    
    if not active_portfolio:
        return pd.DataFrame()

    result_df = pd.DataFrame.from_dict(active_portfolio, orient='index').reset_index()
    result_df.rename(columns={'index': 'ticker'}, inplace=True)

    # 현재가 가져오기 (보유 수량이 있는 경우만)
    def get_price_if_active(row):
        if row['currentQuantity'] > 0:
            return get_current_price(row['ticker'])
        return 0.0
        
    result_df['currentPrice'] = result_df.apply(get_price_if_active, axis=1)
    
    # 평가 금액 및 평가 손익 계산
    result_df['currentValue'] = result_df['currentQuantity'] * result_df['currentPrice']
    result_df['unrealizedPnl'] = (result_df['currentPrice'] - result_df['averageCost']) * result_df['currentQuantity']
    
    # 수익률 계산 (0으로 나누기 방지)
    result_df['returnRate'] = result_df.apply(
        lambda x: (x['currentPrice'] - x['averageCost']) / x['averageCost'] * 100 if x['averageCost'] > 0 else 0.0, 
        axis=1
    )

    return result_df
