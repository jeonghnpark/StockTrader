#!/usr/bin/env python
"""Test add_trade with CSV and DB sync"""

import os
import sys
from datetime import date, time

# 기존 DB와 CSV 리셋
if os.path.exists('data/portfolio.db'):
    os.remove('data/portfolio.db')

from utils import portfolio_db
import pandas as pd
from utils.portfolio import add_trade

# DB 초기화
portfolio_db.init_db()
portfolio_db.migrate_from_csv_json()

# 초기 상태
df_before = pd.read_csv('data/trade_history.csv')
trades_before = portfolio_db.get_all_trades()
print(f'Before: CSV={len(df_before)}, DB={len(trades_before)}')

# 새 거래 추가
add_trade(
    date=date(2026, 6, 4),
    account='Test Account',
    ticker='TEST123',
    tradeType='Buy',
    quantity=100,
    price=50000.0,
    currency='KRW',
    trade_time=time(hour=14, minute=30, second=45)
)

# 결과 확인
df_after = pd.read_csv('data/trade_history.csv')
trades_after = portfolio_db.get_all_trades()
print(f'After: CSV={len(df_after)}, DB={len(trades_after)}')

# 검증
assert len(df_after) == len(df_before) + 1, "CSV row not added"
assert len(trades_after) == len(trades_before) + 1, "DB record not added"

# 마지막 행 확인
last_csv_row = df_after.iloc[-1]
last_db_row = trades_after[-1]

print(f'\nCSV last row: {last_csv_row["ticker"]}, {last_csv_row["tradeType"]}, {last_csv_row["quantity"]}')
print(f'DB last row: {last_db_row["ticker"]}, {last_db_row["tradeType"]}, {last_db_row["quantity"]}')

print("\nAdd trade sync test passed!")
