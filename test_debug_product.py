#!/usr/bin/env python
"""Debug product sync"""

import os

# 기존 DB 리셋
if os.path.exists('data/portfolio.db'):
    os.remove('data/portfolio.db')

from utils import portfolio_db
from utils.product_master import add_or_update_product

# DB 초기화
portfolio_db.init_db()
portfolio_db.migrate_from_csv_json()

# 초기 상태
print("== Before adding NEWPROD ==")
product = portfolio_db.get_product('NEWPROD')
print(f"DB get_product('NEWPROD'): {product}")

products = portfolio_db.get_all_products()
print(f"DB get_all_products(): {len(products)}")
print(f"'NEWPROD' in products: {'NEWPROD' in products}")

# 새 제품 추가
print("\n== Adding NEWPROD ==")
add_or_update_product(
    ticker='NEWPROD',
    asset_class='개별주식',
    market='KRX',
    settlement_currency='KRW',
    exposure_currency='KRW',
    multiplier=1.0,
    name='New Product',
    tags=['test', 'new']
)

# 결과 확인
print("\n== After adding NEWPROD ==")
product = portfolio_db.get_product('NEWPROD')
print(f"DB get_product('NEWPROD'): {product}")

products = portfolio_db.get_all_products()
print(f"DB get_all_products(): {len(products)}")
print(f"'NEWPROD' in products: {'NEWPROD' in products}")

if 'NEWPROD' in products:
    print(f"NEWPROD in DB: {products['NEWPROD']}")
