import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import os
from utils.portfolio import load_trade_history, add_trade, update_trade, calculate_portfolio, get_exchange_rate, get_current_price, delete_trade, get_company_name

# 페이지 기본 설정
st.set_page_config(page_title="주식 포트폴리오 트래커", layout="wide")

# 매매 내역 로드 (기존 종목/계좌 확인용)
history_df = load_trade_history()
existing_tickers = history_df['ticker'].unique().tolist() if not history_df.empty else []
existing_accounts = history_df['account'].unique().tolist() if not history_df.empty and 'account' in history_df.columns else []

# 계좌별 통화 매핑 (하드코딩 + 기존 데이터 기반)
ACCOUNT_CURRENCY_MAP = {
    "LS(한나)": "KRW",
    "키움퇴직": "KRW",
    "토스": "USD"
}
if not history_df.empty and 'account' in history_df.columns:
    for acc in existing_accounts:
        if acc not in ACCOUNT_CURRENCY_MAP:
            acc_df = history_df[history_df['account'] == acc]
            if not acc_df.empty:
                ACCOUNT_CURRENCY_MAP[acc] = acc_df.iloc[0]['currency']

# --- 사이드바: 매매 내역 추가 ---
st.sidebar.header("새 매매 내역 추가")

# 계좌 입력 방식 선택
account_option = st.sidebar.radio("계좌 입력 방식", ["기존 계좌 선택", "새 계좌 직접 입력"])
account = ""
target_currency = "KRW"

if account_option == "기존 계좌 선택":
    if existing_accounts:
        account = st.sidebar.selectbox("계좌 선택", existing_accounts)
        target_currency = ACCOUNT_CURRENCY_MAP.get(account, "KRW")
        st.sidebar.info(f"📌 [{account}] 계좌 지정 통화: **{target_currency}**")
    else:
        st.sidebar.warning("기존 계좌가 없습니다. '새 계좌 직접 입력'을 선택해주세요.")
else:
    account = st.sidebar.text_input("새 계좌명", "새계좌")
    target_currency = st.sidebar.selectbox("새 계좌 통화 지정", ["KRW", "USD"])

# 종목 입력 방식 선택 (기존 종목 vs 직접 입력)
ticker_option = st.sidebar.radio("종목 입력 방식", ["기존 종목 선택", "새 종목 직접 입력"])

ticker = ""
if ticker_option == "기존 종목 선택":
    if existing_tickers:
        # 기존 종목 선택 시 종목명과 티커를 함께 표시
        ticker = st.sidebar.selectbox(
            "종목 선택", 
            existing_tickers,
            format_func=lambda x: f"{get_company_name(x)} ({x})"
        )
    else:
        st.sidebar.warning("기존 매매 내역이 없습니다. '새 종목 직접 입력'을 선택해주세요.")
else:
    ticker = st.sidebar.text_input("종목 코드 (예: AAPL, 005930.KS)", "").upper()
    st.sidebar.caption("한국 주식은 코스피 '.KS', 코스닥 '.KQ'를 붙여주세요. (예: 삼성전자 005930.KS)")

# 종목이 선택/입력되면 현재가 표시
current_price = 0.0
if ticker:
    company_name = get_company_name(ticker)
    current_price = get_current_price(ticker)
    st.sidebar.info(f"**{company_name} ({ticker})**\n\n현재가: {current_price:,.0f}") # 현재가도 소수점 버림

with st.sidebar.form("trade_form"):
    trade_date = st.date_input("매매 일자", date.today())
    trade_type = st.selectbox("매매 종류", ["매수", "매도"])
    
    # 통화 기본값을 target_currency에 맞춤
    currency_idx = 0 if target_currency == "KRW" else 1
    currency = st.selectbox("통화", ["KRW", "USD"], index=currency_idx)
    
    # 수량 기본값 1.0으로 설정, 1씩 증가
    quantity = st.number_input("수량", min_value=0.01, value=1.0, step=1.0)
    
    # 단가 기본값을 현재가로 설정 (현재가가 없으면 0.01)
    default_price = float(current_price) if current_price >= 0.01 else 0.01
    price = st.number_input("단가", min_value=0.01, value=default_price, step=1.0)
    
    submit_button = st.form_submit_button("내역 추가")

    if submit_button:
        if ticker and account:
            if currency != target_currency:
                st.sidebar.error(f"🚨 입력 오류: [{account}] 계좌의 지정된 통화는 {target_currency}입니다. 통화를 일치시켜주세요.")
            else:
                # 데이터 디렉토리 확인
                if not os.path.exists("data"):
                    os.makedirs("data")
                
                # CSV에 추가
                add_trade(trade_date, account, ticker, trade_type, quantity, price, currency)
                st.sidebar.success(f"[{account}] {ticker} {quantity}주 {trade_type} 추가 완료!")
                st.rerun() # 앱 새로고침
        else:
            st.sidebar.error("계좌명과 종목 코드를 모두 입력해주세요.")

# --- 메인 화면 ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown("<h2 style='font-size: 1.5rem; margin-bottom: 20px;'>주식 포트폴리오 트래커</h2>", unsafe_allow_html=True)
with col_btn:
    if st.button("🔄 현재가 업데이트"):
        st.rerun()

# 환율 가져오기
exchange_rate = get_exchange_rate()

col_view, col_acc = st.columns(2)
with col_view:
    # 보기 모드 (원화 환산) - 기본값을 인덱스 1(원화 환산)로 설정
    view_mode = st.radio("표시 통화 모드", ["원래 통화로 보기 (USD/KRW 혼합)", "전체 원화(KRW)로 환산해서 보기"], index=1, horizontal=True)
    is_krw_mode = "환산" in view_mode
    if is_krw_mode:
        st.caption(f"적용 환율: 1 USD = {exchange_rate:,.2f} KRW")

with col_acc:
    # 계좌 필터
    account_list = ["전체 계좌"] + existing_accounts
    selected_account = st.selectbox("조회할 계좌 선택", account_list)

# 포트폴리오 데이터 계산 (선택된 계좌 필터 적용)
df = calculate_portfolio(selected_account)

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
        return f"{val:,.0f}" # 요약 지표도 소수점 버림

    col1.metric("총 자산 평가액", format_currency(total_value))
    
    # 총 수익률 계산 (총 평가손익 / 총 투자원금)
    total_cost = total_value - total_unrealized_pnl
    pnl_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    col2.metric("총 평가 손익", format_currency(total_unrealized_pnl), f"{pnl_pct:,.0f}%") # 수익률 소수점 버림
    
    col3.metric("총 실현 손익", format_currency(total_realized_pnl))

    st.divider()

    # 탭 구성
    tab1, tab2 = st.tabs(["포트폴리오 요약", "매매 내역 관리"])

    with tab1:
        st.markdown("<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>현재 보유 종목</h3>", unsafe_allow_html=True)
        
        # 보유 수량이 0보다 큰 종목만 표시
        holdings_df = display_df[display_df['currentQuantity'] > 0].copy()
        
        if not holdings_df.empty:
            # 비중 계산
            holdings_df['weight'] = (holdings_df['currentValue'] / total_value) * 100
            
            # 화면 표시용 데이터프레임 정리 (companyName 추가)
            show_df = holdings_df[['ticker', 'companyName', 'currency', 'currentQuantity', 'averageCost', 'currentPrice', 'currentValue', 'unrealizedPnl', 'returnRate', 'weight']]
            show_df.columns = ['종목코드', '종목명', '통화', '보유수량', '평균단가', '현재가', '평가금액', '평가손익', '수익률(%)', '비중(%)']
            
            # 포맷팅 설정 (모두 소수점 버림)
            format_dict = {
                '보유수량': '{:,.0f}',
                '평균단가': '{:,.0f}',
                '현재가': '{:,.0f}',
                '평가금액': '{:,.0f}',
                '평가손익': '{:,.0f}',
                '수익률(%)': '{:,.0f}%',
                '비중(%)': '{:,.0f}%'
            }
            
            st.dataframe(show_df.style.format(format_dict), use_container_width=True)
            
            # 파이 차트 (보유 비중)
            st.markdown("<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>포트폴리오 자산 비중</h3>", unsafe_allow_html=True)
            # 파이 차트 라벨을 종목명으로 표시
            fig = px.pie(holdings_df, values='currentValue', names='companyName', title='종목별 자산 비중')
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("현재 보유 중인 주식이 없습니다. 사이드바에서 매수 내역을 추가해보세요!")

    with tab2:
        st.markdown("<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>전체 매매 내역</h3>", unsafe_allow_html=True)
        # 최신 데이터를 다시 불러옴
        current_history_df = load_trade_history()
        
        if not current_history_df.empty:
            # 종목명 컬럼 추가
            current_history_df['종목명'] = current_history_df['ticker'].apply(get_company_name)
            
            # 명시적으로 컬럼 순서 지정 (데이터프레임의 실제 컬럼 순서가 꼬여있을 수 있으므로)
            current_history_df = current_history_df[['date', 'account', 'ticker', '종목명', 'tradeType', 'quantity', 'price', 'currency']]
            
            # 컬럼명 한글화
            current_history_df.columns = ['매매일자', '계좌명', '종목코드', '종목명', '매매종류', '수량', '단가', '통화']
            
            # 데이터 타입 명시적 변환 (문자열이 섞여있을 경우 포맷팅 에러 방지)
            current_history_df['수량'] = pd.to_numeric(current_history_df['수량'], errors='coerce').fillna(0)
            current_history_df['단가'] = pd.to_numeric(current_history_df['단가'], errors='coerce').fillna(0)
            
            # 매매 내역 포맷팅 (수량, 단가 소수점 버림)
            history_format_dict = {
                '수량': '{:,.0f}',
                '단가': '{:,.0f}'
            }
            
            st.divider()
            st.markdown("<h3 style='font-size: 1.1rem; margin-bottom: 10px;'>매매 내역 수정 및 삭제</h3>", unsafe_allow_html=True)
            st.write("아래 표에서 수정하거나 삭제할 내역의 행(row)을 클릭하세요.")
            
            # 인덱스를 포함하여 표시하고 행 선택 기능 활성화
            event = st.dataframe(
                current_history_df.style.format(history_format_dict), 
                use_container_width=True,
                on_select="rerun",
                selection_mode="single-row"
            )
            
            selected_rows = event.selection.rows
            
            if selected_rows:
                row_idx = selected_rows[0]
                edit_index = current_history_df.index[row_idx]
                
                raw_df = load_trade_history()
                row_data = raw_df.loc[edit_index]
                
                with st.container(border=True):
                    st.markdown(f"**선택된 내역 편집 (인덱스: {edit_index})**")
                    col_e1, col_e2, col_e3 = st.columns(3)
                    with col_e1:
                        edit_date = st.date_input("매매 일자", pd.to_datetime(row_data['date']), key=f"edit_date_{edit_index}")
                        edit_account = st.text_input("계좌명", row_data['account'], key=f"edit_account_{edit_index}")
                        edit_ticker = st.text_input("종목 코드", row_data['ticker'], key=f"edit_ticker_{edit_index}").upper()
                    with col_e2:
                        edit_type = st.selectbox("매매 종류", ["매수", "매도"], index=0 if row_data['tradeType'] in ['Buy', '매수'] else 1, key=f"edit_type_{edit_index}")
                        edit_quantity = st.number_input("수량", min_value=0.01, value=float(row_data['quantity']), step=1.0, key=f"edit_qty_{edit_index}")
                    with col_e3:
                        edit_price = st.number_input("단가", min_value=0.01, value=float(row_data['price']), step=1.0, key=f"edit_price_{edit_index}")
                        edit_currency = st.selectbox("통화", ["KRW", "USD"], index=0 if row_data['currency'] == 'KRW' else 1, key=f"edit_currency_{edit_index}")
                    
                    col_btn1, col_btn2 = st.columns([1, 10])
                    with col_btn1:
                        if st.button("수정", type="primary", key=f"btn_update_{edit_index}"):
                            expected_currency = ACCOUNT_CURRENCY_MAP.get(edit_account, edit_currency)
                            if edit_currency != expected_currency:
                                st.error(f"🚨 수정 오류: [{edit_account}] 계좌는 {expected_currency} 전용입니다. 통화를 확인해주세요.")
                            else:
                                if update_trade(edit_index, edit_date, edit_account, edit_ticker, edit_type, edit_quantity, edit_price, edit_currency):
                                    st.success("성공적으로 수정되었습니다.")
                                    st.rerun()
                    with col_btn2:
                        if st.button("삭제", type="secondary", key=f"btn_delete_{edit_index}"):
                            if delete_trade(edit_index):
                                st.success("성공적으로 삭제되었습니다.")
                                st.rerun()
        else:
            st.info("기록된 매매 내역이 없습니다.")
else:
    st.info("선택된 계좌에 포트폴리오 데이터가 없습니다. 좌측 사이드바에서 매매 내역을 추가해주세요.")
