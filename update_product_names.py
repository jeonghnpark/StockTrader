import json
from utils.portfolio import get_company_name
import os

file_path = os.path.join(os.path.dirname(__file__), 'data', 'product_master.json')

with open(file_path, 'r', encoding='utf-8') as f:
    products = json.load(f)

updated_products = {}
for ticker, info in products.items():
    name = get_company_name(ticker)
    info['name'] = name
    info.setdefault('tags', [])
    updated_products[ticker] = info

with open(file_path, 'w', encoding='utf-8') as f:
    json.dump(updated_products, f, ensure_ascii=False, indent=4)

print("product_master.json 파일이 업데이트되었습니다.")
