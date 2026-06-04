"""
Test trade validation function
"""

import sys
sys.path.insert(0, '.')

from utils.portfolio import validate_trade, load_trade_history

# Check current portfolio state
df = load_trade_history()
print("=== Current Trade Records ===")
print(f"Total: {len(df)} trades")
print()

# Test case 1: Buy on holding stock
print("TEST 1: Buy 100 shares of '009470' (holding stock)")
is_valid, msg = validate_trade("009470", "매수", 100)
print(f"  Result: {'OK' if is_valid else 'FAIL'}")
if msg:
    print(f"  Message: {msg}")
print()

# Test case 2: Sell on holding stock (valid quantity)
print("TEST 2: Sell 14 shares of '009470' (holding: 14 shares)")
is_valid, msg = validate_trade("009470", "매도", 14)
print(f"  Result: {'OK' if is_valid else 'FAIL'}")
if msg:
    print(f"  Message: {msg}")
print()

# Test case 3: Sell on holding stock (exceed quantity)
print("TEST 3: Sell 100 shares of '009470' (holding: 14 shares) - EXCEED")
is_valid, msg = validate_trade("009470", "매도", 100)
print(f"  Result: {'OK' if is_valid else 'FAIL'}")
if msg:
    print(f"  Message:\n{msg}")
print()

# Test case 4: Sell on non-holding stock
print("TEST 4: Sell 10 shares of 'NOTEXIST' (not holding)")
is_valid, msg = validate_trade("NOTEXIST", "매도", 10)
print(f"  Result: {'OK' if is_valid else 'FAIL'}")
if msg:
    print(f"  Message: {msg}")
print()

# Test case 5: Sell on future (bidirectional trading allowed)
print("TEST 5: Sell 100 shares of 'A7566000' (future - bidirectional)")
is_valid, msg = validate_trade("A7566000", "매도", 100)
print(f"  Result: {'OK' if is_valid else 'FAIL'}")
if msg:
    print(f"  Message: {msg}")
print()
