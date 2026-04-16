import pandas as pd
import yfinance as yf
import os

CSV_FILE = "data/trade_history.csv"

def load_trade_history():
    if not os.path.exists(CSV_FILE):
        return pd.DataFrame(columns=["date", "ticker", "tradeType", "quantity", "price"])
    return pd.read_csv(CSV_FILE)

def add_trade(date, ticker, tradeType, quantity, price):
    df = load_trade_history()
    new_row = pd.DataFrame([{
        "date": date,
        "ticker": ticker.upper(),
        "tradeType": tradeType,
        "quantity": float(quantity),
        "price": float(price)
    }])
    df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(CSV_FILE, index=False)

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

def calculate_portfolio():
    df = load_trade_history()
    if df.empty:
        return pd.DataFrame(), 0.0, 0.0, 0.0

    portfolio = {}
    total_realized_pnl = 0.0

    for _, row in df.iterrows():
        ticker = row['ticker']
        tradeType = row['tradeType']
        quantity = row['quantity']
        price = row['price']

        if ticker not in portfolio:
            portfolio[ticker] = {
                "currentQuantity": 0.0,
                "totalCost": 0.0,
                "averageCost": 0.0,
                "realizedPnl": 0.0
            }

        if tradeType == 'Buy':
            portfolio[ticker]['currentQuantity'] += quantity
            portfolio[ticker]['totalCost'] += quantity * price
            if portfolio[ticker]['currentQuantity'] > 0:
                portfolio[ticker]['averageCost'] = portfolio[ticker]['totalCost'] / portfolio[ticker]['currentQuantity']
        elif tradeType == 'Sell':
            if portfolio[ticker]['currentQuantity'] >= quantity:
                # Realized PnL = (Sell Price - Average Cost) * Quantity
                pnl = (price - portfolio[ticker]['averageCost']) * quantity
                portfolio[ticker]['realizedPnl'] += pnl
                total_realized_pnl += pnl
                
                portfolio[ticker]['currentQuantity'] -= quantity
                portfolio[ticker]['totalCost'] -= portfolio[ticker]['averageCost'] * quantity
                
                if portfolio[ticker]['currentQuantity'] == 0:
                    portfolio[ticker]['averageCost'] = 0.0
                    portfolio[ticker]['totalCost'] = 0.0

    # Filter out empty positions
    active_portfolio = {k: v for k, v in portfolio.items() if v['currentQuantity'] > 0}
    
    if not active_portfolio:
        return pd.DataFrame(), 0.0, 0.0, total_realized_pnl

    result_df = pd.DataFrame.from_dict(active_portfolio, orient='index').reset_index()
    result_df.rename(columns={'index': 'ticker'}, inplace=True)

    # Fetch current prices
    result_df['currentPrice'] = result_df['ticker'].apply(get_current_price)
    
    # Calculate Unrealized PnL and Value
    result_df['currentValue'] = result_df['currentQuantity'] * result_df['currentPrice']
    result_df['unrealizedPnl'] = (result_df['currentPrice'] - result_df['averageCost']) * result_df['currentQuantity']
    result_df['returnRate'] = (result_df['currentPrice'] - result_df['averageCost']) / result_df['averageCost'] * 100

    total_value = result_df['currentValue'].sum()
    total_unrealized_pnl = result_df['unrealizedPnl'].sum()

    if total_value > 0:
        result_df['weight'] = (result_df['currentValue'] / total_value) * 100
    else:
        result_df['weight'] = 0.0

    return result_df, total_value, total_unrealized_pnl, total_realized_pnl
