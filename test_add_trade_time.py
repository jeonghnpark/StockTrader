"""
Test add_trade with time object (from app.py style)
"""

import sys
sys.path.insert(0, '.')

from datetime import date as date_type, time as time_type
from utils.portfolio import add_trade, load_trade_history

# Get initial count
initial_df = load_trade_history()
initial_count = len(initial_df)

# Test: Add trade with time object (like app.py does)
print("TEST: Add trade with time object (like app.py)")
print(f"  Current record count: {initial_count}")

try:
    add_trade(
        date_type(2026, 6, 4),  # date object
        "TestAccount",
        "005930",
        "매수",
        100,
        70000,
        currency="KRW",
        trade_time=time_type(10, 30, 45),  # time object from st.time_input
    )
    print("  Result: OK - Trade added successfully")
    
    # Verify
    after_df = load_trade_history()
    new_record = after_df.iloc[-1]
    print(f"  New record date: {new_record['date']}")
    print(f"  Expected: 2026-06-04 10:30:45")
    
except Exception as e:
    print(f"  Result: FAIL - {str(e)}")
    import traceback
    traceback.print_exc()
