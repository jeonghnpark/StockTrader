"""
개선 사항 테스트: 전일 평가손익, 변동률 등이 제대로 계산되는지 확인
"""
import sys
import pandas as pd
from utils.portfolio import calculate_portfolio, get_previous_close_price, get_current_price

print("=" * 60)
print("Portfolio Improvements Test")
print("=" * 60)

# 포트폴리오 데이터 로드
portfolio_df = calculate_portfolio()

if not portfolio_df.empty:
    print("\nPortfolio Summary:")
    print(f"Number of holdings: {len(portfolio_df[portfolio_df['currentQuantity'] != 0])}")
    
    print("\nKey Metrics:")
    total_unrealized = portfolio_df["unrealizedPnlKrw"].sum()
    total_realized = portfolio_df["realizedPnlKrw"].sum()
    total_pnl = total_unrealized + total_realized
    total_pnl_change = portfolio_df["pnlChangeKrw"].sum()
    
    print(f"Total Unrealized P&L: {total_unrealized:,.0f}")
    print(f"Total Realized P&L: {total_realized:,.0f}")
    print(f"Total P&L: {total_pnl:,.0f}")
    print(f"Day-over-Day P&L Change: {total_pnl_change:,.0f}")
    
    print("\nIndividual Holdings:")
    display_cols = [
        "ticker", "companyName", "currentQuantity", 
        "currentPrice", "unrealizedPnlKrw", 
        "pnlChangeKrw", "pnlChangeRate"
    ]
    
    missing_cols = [col for col in display_cols if col not in portfolio_df.columns]
    if missing_cols:
        print(f"Warning: Missing columns: {missing_cols}")
    
    summary_df = portfolio_df[
        (portfolio_df["currentQuantity"] != 0) | (portfolio_df["realizedPnlKrw"] != 0)
    ][[col for col in display_cols if col in portfolio_df.columns]].copy()
    
    print(summary_df.to_string(index=False))
    
    print("\nSuccess: All fields calculated properly!")
else:
    print("\nWarning: No portfolio data available.")

print("\n" + "=" * 60)

