"""
Test TSLA current price with g3101 API - LS overseas stock API validation
"""

import sys
import os
from pathlib import Path
import logging

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
from utils import ls_g3101

load_dotenv()

# 로깅 활성화
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s: %(message)s')

print("=" * 60)
print("LS g3101 API Test - TSLA Current Price Inquiry")
print("=" * 60)

try:
    print("\n[1] Starting TSLA inquiry...")
    data = ls_g3101.get_current(symbol="TSLA", exchcd="82")
    
    if data:
        print("\n[OK] API call succeeded!")
        print(f"\nResult:")
        print(f"  - Symbol: {data.get('symbol', 'N/A')}")
        print(f"  - Korean Name: {data.get('korname', 'N/A')}")
        print(f"  - Current Price: {data.get('price', 'N/A')}")
        print(f"  - Exchange: {data.get('exchg', 'N/A')}")
        print(f"  - Currency: {data.get('currency', 'N/A')}")
        print(f"  - Change: {data.get('diff', 'N/A')} ({data.get('rate', 'N/A')}%)")
        print(f"  - Volume: {data.get('volume', 'N/A')}")
        print(f"  - High: {data.get('high', 'N/A')}")
        print(f"  - Low: {data.get('low', 'N/A')}")
        
        price = data.get('price')
        if price:
            try:
                price_float = float(price)
                print(f"\n[OK] Price parsing succeeded: ${price_float:.2f}")
            except (ValueError, TypeError):
                print(f"\n[WARN] Price parsing failed: {price}")
        else:
            print(f"\n[WARN] No price information")
            
        print(f"\nAll response fields:")
        for key, value in data.items():
            print(f"  - {key}: {value}")
    else:
        print("\n[ERROR] API call failed - returned None")
        print("   Check LS securities API keys in .env file")
        
except Exception as e:
    print(f"\n[ERROR] Exception: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "=" * 60)
