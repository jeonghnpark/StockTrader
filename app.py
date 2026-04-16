import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import os
from utils.portfolio import load_trade_history, add_trade, calculate_portfolio, get_exchange_rate, get_current_price, delete_trade

# 페이지 기본 설정
st.set_page_config(page_title="주식 포트폴리오 트래커", layout="wide")

# 매매 내역 로드 (기존 종목 확인용)
history_df = load_trade_history()
existing_tickers = history_df['ticker'].unique().tolist() if not history_df.empty else []

# --- 사이드바: 매매 내역 추가 ---
st.sidebar.header("새 매매 내역 추가")

# 종목 입력 방식 선택 (기존 종목 vs 직접 입력)
ticker_option = st.sidebar.radio("종목 입력 방식", ["기존 종목 선택", "새 종목 직접 입력"])

ticker = ""
if ticker_option == "기존 종목 선택":
    if existing_tickers:
        ticker = st.sidebar.selectbox("종목 선택", existing_tickers)
    else:
        st.sidebar.warning("기존 매매 내역이 없습니다. '새 종목 직접 입력'을 선택해주세요.")
else:
    ticker = st.sidebar.text_input("종목 코드 (예: AAPL, 005930.KS)", "").upper()
    st.sidebar.caption("한국 주식은 코스피 '.KS', 코스닥 '.KQ'를 붙여주세요. (예: 삼성전자 005930.KS)")

# 종목이 선택/입력되면 현재가 표시
if ticker:
    current_price = get_current_price(ticker)
    st.sidebar.info(f"**{ticker}** 현재가: {current_price:,.2f}")

with st.sidebar.form("trade_form"):
    trade_date = st.date_input("매매 일자", date.today())
    trade_type = st.selectbox("매매 종류", ["매수", "매도"])
    currency = st.selectbox("통화", ["USD", "KRW"])
    quantity = st.number_input("수량", min_value=0.01, step=1.0)
    price = st.number_input("단가", min_value=0.01, step=1.0)
    submit_button = st.form_submit_button("내역 추가")

    if submit_button:
        if ticker:
            # 데이터 디렉토리 확인
            if not os.path.exists("data"):
                os.makedirs("data")
            
            # CSV에 추가
            add_trade(trade_date, ticker, trade_type, quantity, price, currency)
            st.sidebar.success(f"{ticker} {quantity}주 {trade_type} 추가 완료!")
            st.rerun() # 앱 새로고침
        else:
            st.sidebar.error("종목 코드를 입력해주세요.")

# --- 메인 화면 ---
st.title("주식 포트폴리오 트래커")

# 환율 가져오기
exchange_rate = get_exchange_rate()

# 보기 모드 (원화 환산)
view_mode = st.radio("표시 통화 모드", ["원래 통화로 보기 (USD/KRW 혼합)", "전체 원화(KRW)로 환산해서 보기"], horizontal=True)
is_krw_mode = "환산" in view_mode

if is_krw_mode:
    st.caption(f"적용 환율: 1 USD = {exchange_rate:,.2f} KRW")

# 포트폴리오 데이터 계산
df = calculate_portfolio()

if not df.empty:
    # 보기 모드에 따라 데이터 변환
    display_df = df.copy()
    
    if is_krw_mode:
        # USD 자산을 KRW로 변환
        usd_mask = display_df['currency'] == 'USD'
        display_df.loc[usd_mask, 'averageCost'] *= exchange_rate
        display_df.loc[usd_mask, 'currentPrice'] *= exchange_rate
        display_df.loc[usd_mask, 'currentValue'] *= exchange_rate
        display_df.loc[usd_mask, 'unrealizedPnl'] *= exchange_rate
        display_df.loc[usd_mask, 'realizedPnl'] *= exchange_rate
        display_df.loc[usd_mask, 'currency'] = 'KRW (환산)'

    # 총합 계산
    total_value = display_df['currentValue'].sum()
    total_unrealized_pnl = display_df['unrealizedPnl'].sum()
    total_realized_pnl = display_df['realizedPnl'].sum()

    # 상단 요약 지표 표시
    col1, col2, col3 = st.columns(3)
    
    def format_currency(val):
        if is_krw_mode:
            return f"₩{val:,.0f}"
        return f"{val:,.2f}"

    col1.metric("총 자산 평가액", format_currency(total_value))
    
    # 총 수익률 계산 (총 평가손익 / 총 투자원금)
    total_cost = total_value - total_unrealized_pnl
    pnl_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    col2.metric("총 평가 손익", format_currency(total_unrealized_pnl), f"{pnl_pct:,.2f}%")
    
    col3.metric("총 실현 손익", format_currency(total_realized_pnl))

    st.divider()

    # 탭 구성
    tab1, tab2 = st.tabs(["포트폴리오 요약", "매매 내역 관리"])

    with tab1:
        st.subheader("현재 보유 종목")
        
        # 보유 수량이 0보다 큰 종목만 표시
        holdings_df = display_df[display_df['currentQuantity'] > 0].copy()
        
        if not holdings_df.empty:
            # 비중 계산
            holdings_df['weight'] = (holdings_df['currentValue'] / total_value) * 100
            
            # 화면 표시용 데이터프레임 정리
            show_df = holdings_df[['ticker', 'currency', 'currentQuantity', 'averageCost', 'currentPrice', 'currentValue', 'unrealizedPnl', 'returnRate', 'weight']]
            show_df.columns = ['종목', '통화', '보유수량', '평균단가', '현재가', '평가금액', '평가손익', '수익률(%)', '비중(%)']
            
            # 포맷팅 설정
            format_dict = {
                '보유수량': '{:.2f}',
                '평균단가': '{:,.2f}',
                '현재가': '{:,.2f}',
                '평가금액': '{:,.2f}',
                '평가손익': '{:,.2f}',
                '수익률(%)': '{:.2f}%',
                '비중(%)': '{:.2f}%'
            }
            
            st.dataframe(show_df.style.format(format_dict), use_container_width=True)
            
            # 파이 차트 (보유 비중)
            st.subheader("포트폴리오 자산 비중")
            fig = px.pie(holdings_df, values='currentValue', names='ticker', title='종목별 자산 비중')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("현재 보유 중인 주식이 없습니다. 사이드바에서 매수 내역을 추가해보세요!")

    with tab2:
        st.subheader("전체 매매 내역")
        # 최신 데이터를 다시 불러옴
        current_history_df = load_trade_history()
        
        if not current_history_df.empty:
            # 인덱스를 포함하여 표시 (삭제 시 참고용)
            st.dataframe(current_history_df, use_container_width=True)
            
            st.divider()
            st.subheader("매매 내역 삭제")
            st.write("위 표의 가장 왼쪽 번호(인덱스)를 입력하여 잘못 입력된 내역을 삭제할 수 있습니다.")
            
            col_del1, col_del2 = st.columns([3, 1])
            with col_del1:
                delete_index = st.number_input("삭제할 내역의 인덱스 번호", min_value=0, max_value=len(current_history_df)-1, step=1)
            with col_del2:
                # 버튼을 입력 필드와 높이를 맞추기 위해 약간의 빈 공간 추가
                st.write("")
                st.write("")
                if st.button("해당 내역 삭제", type="primary"):
                    if delete_trade(delete_index):
                        st.success(f"인덱스 {delete_index} 내역이 성공적으로 삭제되었습니다.")
                        st.rerun() # 앱 새로고침하여 반영
                    else:
                        st.error("삭제에 실패했습니다.")
        else:
            st.info("기록된 매매 내역이 없습니다.")
else:
    st.info("포트폴리오 데이터가 없습니다. 좌측 사이드바에서 매매 내역을 추가해주세요.")
