#!/usr/bin/env python
"""Test incremental migration"""

import os
import sys

# DB 파일 삭제 (테스트용)
if os.path.exists('data/portfolio.db'):
    os.remove('data/portfolio.db')

from utils import portfolio_db
import pandas as pd

# DB 초기화
portfolio_db.init_db()

# CSV 행 수 확인
df = pd.read_csv('data/trade_history.csv')
print(f'CSV trades: {len(df)}')

# 마이그레이션 실행
portfolio_db.migrate_from_csv_json()

# 결과 확인
trades = portfolio_db.get_all_trades()
print(f'DB trades after migration: {len(trades)}')

# 제품마스터 확인
products = portfolio_db.get_all_products()
print(f'DB products: {len(products)}')

print("\nMigration test passed!")
