import pandas as pd
import yfinance as yf
import os

CSV_FILE = "data/trade_history.csv"

def load_trade_history():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=["date", "ticker", "tradeType", "quantity", "price", "currency"])
    
    df = pd.read_csv(CSV_FILE)
    
    # 기존 데이터에 currency 컬럼이 없는 경우 추가 (기본값 USD)
    if "currency" not in df.columns:
        df["currency"] = "USD"
        df.to_csv(CSV_FILE, index=False)
        
    return df

def add_trade(date, ticker, tradeType, quantity, price, currency="USD"):
    df = load_trade_history()
    new_row = pd.DataFrame([{
        "date": date,
        "ticker": ticker.upper(),
        "tradeType": tradeType,
        "quantity": float(quantity),
        "price": float(price),
        "currency": currency
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

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

def get_exchange_rate():
    try:
        # USD/KRW 환율 가져오기
        rate = yf.Ticker("USDKRW=X").history(period='1d')
        if not rate.empty:
            return rate['Close'].iloc[0]
        return 1300.0 # API 실패 시 임시 기본값
    except:
        return 1300.0

def calculate_portfolio():
    df = load_trade_history()
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
                "currency": currency
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
