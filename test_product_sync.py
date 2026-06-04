#!/usr/bin/env python
"""Test product master sync"""

import os
import json
import time

# 기존 DB 리셋
if os.path.exists('data/portfolio.db'):
    os.remove('data/portfolio.db')

from utils import portfolio_db
from utils.product_master import add_or_update_product

# DB 초기화
portfolio_db.init_db()
portfolio_db.migrate_from_csv_json()

# 초기 상태
products_before = portfolio_db.get_all_products()
print(f'Before: DB products={len(products_before)}')

# JSON 파일도 확인
with open('data/product_master.json', 'r', encoding='utf-8') as f:
    json_before = json.load(f)
print(f'Before: JSON products={len(json_before)}')

# 고유한 제품명 생성
unique_ticker = f'TESTPROD{int(time.time()) % 100000}'
print(f'\nTesting with ticker: {unique_ticker}')

# 새 제품 추가
add_or_update_product(
    ticker=unique_ticker,
    asset_class='개별주식',
    market='KRX',
    settlement_currency='KRW',
    exposure_currency='KRW',
    multiplier=1.0,
    name='Test Product',
    tags=['test', 'new']
)

# 결과 확인
products_after = portfolio_db.get_all_products()
with open('data/product_master.json', 'r', encoding='utf-8') as f:
    json_after = json.load(f)

print(f'After: DB products={len(products_after)}')
print(f'After: JSON products={len(json_after)}')

# 검증
assert len(products_after) == len(products_before) + 1, f"DB product not added: {len(products_before)} -> {len(products_after)}"
assert len(json_after) == len(json_before) + 1, f"JSON product not added: {len(json_before)} -> {len(json_after)}"
assert unique_ticker in products_after, f"New product not in DB"
assert unique_ticker in json_after, f"New product not in JSON"

print(f'\nDB: {unique_ticker} tags={products_after[unique_ticker]["tags"]}')
print(f'JSON: {unique_ticker} tags={json_after[unique_ticker]["tags"]}')

print("\nProduct master sync test passed!")
