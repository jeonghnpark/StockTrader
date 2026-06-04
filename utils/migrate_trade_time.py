"""
trade_history.csv 마이그레이션: 날짜-only 데이터에 시간 정보 추가

규칙:
1. 같은 날짜, 같은 종목의 거래들을 그룹화
2. 같은 그룹 내에서:
   - 매수(Buy)는 매도(Sell) 전에 시간이 더 빨라야 함
   - 보유 잔고(position)가 음수가 되는 경우 감지하고 시간 순서 조정
3. 각 거래에 임의의 시간(초 단위) 할당
"""

import pandas as pd
from datetime import datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CSV_FILE = "data/trade_history.csv"


def migrate_trade_time():
    """기존 CSV 데이터에 시간 정보 추가"""
    df = pd.read_csv(CSV_FILE)
    
    # date를 datetime으로 변환
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    
    logger.info(f"총 {len(df)}개의 거래 레코드 로드됨")
    
    # date가 datetime이 아닌 경우 처리
    if df["date"].isna().any():
        logger.warning(f"{df['date'].isna().sum()}개의 잘못된 날짜 발견")
    
    # 종목별, 날짜별로 그룹화
    df_sorted = df.sort_values(["date", "ticker"]).reset_index(drop=True)
    
    # 각 거래에 시간 정보 추가
    time_assignments = []
    
    for ticker in df_sorted["ticker"].unique():
        ticker_df = df_sorted[df_sorted["ticker"] == ticker].reset_index(drop=True)
        
        for date in ticker_df["date"].unique():
            # 같은 날짜, 같은 종목의 거래들
            same_day_trades = ticker_df[ticker_df["date"] == date].reset_index(drop=True)
            
            if len(same_day_trades) > 0:
                position = 0.0
                reorder_needed = False
                
                # 거래 순서 검증 및 조정
                trades_for_reorder = []
                for idx, row in same_day_trades.iterrows():
                    trade_type = row["tradeType"]
                    quantity = row["quantity"]
                    
                    if trade_type == "매수":
                        position += quantity
                    else:  # 매도
                        position -= quantity
                    
                    trades_for_reorder.append({
                        "index": idx,
                        "trade_type": trade_type,
                        "quantity": quantity,
                        "original_position": position,
                    })
                
                # 음수 포지션 감지
                min_position = min([t["original_position"] for t in trades_for_reorder])
                if min_position < -0.01:  # 부동소수점 오차 허용
                    logger.warning(
                        f"⚠️ {ticker} {date.date()}: 매도 전에 보유 잔고가 음수 상태 감지 (최소: {min_position})"
                    )
                    reorder_needed = True
                    
                    # 시간 순서 조정: 매수를 매도 전에 배치
                    buys = [t for t in trades_for_reorder if t["trade_type"] == "매수"]
                    sells = [t for t in trades_for_reorder if t["trade_type"] == "매도"]
                    
                    # 매수 먼저, 그 다음 매도
                    reordered = buys + sells
                    trades_for_reorder = reordered
                
                # 각 거래에 임의의 시간 할당 (초 단위)
                base_time = pd.Timestamp(date).replace(hour=9, minute=0, second=0, microsecond=0)
                
                for order_idx, trade_info in enumerate(trades_for_reorder):
                    # 매수와 매도 사이에 시간 차이를 두기
                    buy_count = len([t for t in trades_for_reorder[:order_idx + 1] if t["trade_type"] == "매수"])
                    sell_count = len([t for t in trades_for_reorder[:order_idx + 1] if t["trade_type"] == "매도"])
                    
                    if trade_info["trade_type"] == "매수":
                        # 매수: 09:00:00부터 시작해서 1초씩 증가
                        time_assignments.append({
                            "ticker": ticker,
                            "date": date,
                            "trade_type": trade_info["trade_type"],
                            "quantity": trade_info["quantity"],
                            "assigned_time": base_time + timedelta(seconds=order_idx * 60),
                            "reordered": reorder_needed,
                        })
                    else:
                        # 매도: 매수보다 뒤에 배치 (매수 + 600초 이후부터)
                        time_assignments.append({
                            "ticker": ticker,
                            "date": date,
                            "trade_type": trade_info["trade_type"],
                            "quantity": trade_info["quantity"],
                            "assigned_time": base_time + timedelta(seconds=600 + order_idx * 60),
                            "reordered": reorder_needed,
                        })
    
    # 할당된 시간을 원본 df에 병합
    # 다시 정렬된 df 생성
    new_df = []
    for ticker in df_sorted["ticker"].unique():
        ticker_df = df_sorted[df_sorted["ticker"] == ticker].reset_index(drop=True)
        
        for date in ticker_df["date"].unique():
            same_day_trades = ticker_df[ticker_df["date"] == date].reset_index(drop=True)
            
            # 이 그룹에 해당하는 time_assignments 찾기
            group_assignments = [
                t for t in time_assignments
                if t["ticker"] == ticker and t["date"] == date
            ]
            
            if len(group_assignments) == len(same_day_trades):
                for row_idx, row in same_day_trades.iterrows():
                    original_index = df_sorted.index[df_sorted["ticker"].eq(ticker) & 
                                                     df_sorted["date"].eq(date)][row_idx]
                    time_info = group_assignments[row_idx]
                    
                    new_row = row.copy()
                    new_row["date"] = time_info["assigned_time"]
                    new_df.append(new_row)
            else:
                # 할당 실패 (이상적으로 이 경우는 발생하지 않음)
                for row in same_day_trades.iterrows():
                    new_df.append(row[1])
    
    result_df = pd.DataFrame(new_df)
    
    # 재정렬
    result_df = result_df.sort_values(["date"]).reset_index(drop=True)
    
    # 결과 로깅
    reordered_count = len([t for t in time_assignments if t["reordered"]])
    if reordered_count > 0:
        logger.info(f"✓ {reordered_count}개 그룹에서 거래 순서 조정됨")
    
    logger.info(f"✓ 모든 {len(result_df)}개의 거래에 시간 정보 추가 완료")
    
    # CSV에 저장
    result_df.to_csv(CSV_FILE, index=False)
    logger.info(f"✓ {CSV_FILE} 파일 업데이트 완료")
    
    return result_df


if __name__ == "__main__":
    result = migrate_trade_time()
    print("\n=== 마이그레이션 결과 (처음 10개 행) ===")
    print(result.head(10)[["date", "ticker", "tradeType", "quantity"]])
    print("\n=== 마이그레이션 결과 (마지막 10개 행) ===")
    print(result.tail(10)[["date", "ticker", "tradeType", "quantity"]])
