import json
import os
import pandas as pd

PRODUCT_MASTER_FILE = "data/product_master.json"

def load_product_master():
    if not os.path.exists(PRODUCT_MASTER_FILE):
        # Initialize from trade_history.csv if it exists
        products = {}
        history_file = "data/trade_history.csv"
        if os.path.exists(history_file):
            df = pd.read_csv(history_file)
            for _, row in df.iterrows():
                ticker = str(row['ticker']).strip().upper()
                if ticker not in products:
                    currency = row.get('currency', 'KRW')
                    exposure = row.get('exposure_currency', 'KRW')
                    asset_class = row.get('asset_class', '개별주식')
                    
                    # Determine market based on ticker format (simple heuristic)
                    if ticker.isalpha():
                        market = "NASDAQ" if currency == "USD" else "KRX"
                    else:
                        market = "KRX"
                        
                    products[ticker] = {
                        "ticker": ticker,
                        "asset_class": asset_class,
                        "market": market,
                        "settlement_currency": currency,
                        "exposure_currency": exposure,
                        "multiplier": 1.0
                    }
        
        # Save the initialized master
        os.makedirs(os.path.dirname(PRODUCT_MASTER_FILE), exist_ok=True)
        with open(PRODUCT_MASTER_FILE, "w", encoding="utf-8") as f:
            json.dump(products, f, indent=4, ensure_ascii=False)
            
        return products
        
    with open(PRODUCT_MASTER_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_product_master(products):
    os.makedirs(os.path.dirname(PRODUCT_MASTER_FILE), exist_ok=True)
    with open(PRODUCT_MASTER_FILE, "w", encoding="utf-8") as f:
        json.dump(products, f, indent=4, ensure_ascii=False)

def get_product(ticker):
    products = load_product_master()
    ticker = str(ticker).strip().upper()
    return products.get(ticker)

def add_or_update_product(ticker, asset_class, market, settlement_currency, exposure_currency, multiplier):
    products = load_product_master()
    ticker = str(ticker).strip().upper()
    products[ticker] = {
        "ticker": ticker,
        "asset_class": asset_class,
        "market": market,
        "settlement_currency": settlement_currency,
        "exposure_currency": exposure_currency,
        "multiplier": float(multiplier)
    }
    save_product_master(products)
