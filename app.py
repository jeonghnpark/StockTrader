import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import os
from utils.portfolio import (
    load_trade_history,
    add_trade,
    update_trade,
    calculate_portfolio,
    get_exchange_rate,
    get_current_price,
    delete_trade,
    get_company_name,
    EXPOSURE_CURRENCY_OPTIONS,
    ASSET_CLASS_OPTIONS,
    NEW_TRADE_DEFAULT_ASSET_CLASS,
    FX_HEDGE_TICKER,
)

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
    ticker = st.sidebar.text_input("종목 코드 (예: AAPL, 005930 또는 005930.KS)", "").upper()
    st.sidebar.caption(
        "한국 주식은 LS증권 6자리 코드(예: 005930) 또는 005930.KS / 005930.KQ 형식. "
        f"달러 헤지·선물 포지션은 **{FX_HEDGE_TICKER}** 로 입력하세요. 단가는 KRW/USD(원화 환율)이며, 매도를 먼저 넣어도 됩니다."
    )

# 종목이 선택/입력되면 현재가 표시
current_price = 0.0
if ticker:
    company_name = get_company_name(ticker)
    current_price = get_current_price(ticker)
    st.sidebar.info(f"**{company_name} ({ticker})**\n\n현재가: {current_price:,.0f}") # 현재가도 소수점 버림

trade_form_fx_default = get_exchange_rate()
with st.sidebar.form("trade_form"):
    trade_date = st.date_input("매매 일자", date.today())
    trade_type = st.selectbox("매매 종류", ["매수", "매도"])
    
    # 통화 기본값을 target_currency에 맞춤
    currency_idx = 0 if target_currency == "KRW" else 1
    currency = st.selectbox("통화", ["KRW", "USD"], index=currency_idx)

    exposure_default_idx = 1 if currency == "USD" else 0
    exposure_currency = st.selectbox(
        "노출통화 (환율 리스크)",
        list(EXPOSURE_CURRENCY_OPTIONS),
        index=exposure_default_idx,
        help="결제 통화와 다를 수 있습니다. 예: 국내 상장 KODEX 나스닥100은 원화로 거래되어도 미국 지수·달러 자산에 노출될 수 있어 노출통화를 USD로 둘 수 있습니다.",
    )
    asset_class = st.selectbox(
        "자산군",
        list(ASSET_CLASS_OPTIONS),
        index=list(ASSET_CLASS_OPTIONS).index(NEW_TRADE_DEFAULT_ASSET_CLASS),
    )

    trade_fx_krw_per_usd = 1.0
    if currency == "USD":
        trade_fx_krw_per_usd = st.number_input(
            "매매 당시 환율 (1 USD = ? KRW)",
            min_value=0.01,
            value=float(trade_form_fx_default),
            step=1.0,
            help="매수·매도 모두 해당 체결 시점의 USD/KRW 환율을 입력합니다. 실현손익은 매도환율×매도단가×수량 − 장부원화평균단가×수량으로 반영됩니다.",
        )
    
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
                add_trade(
                    trade_date,
                    account,
                    ticker,
                    trade_type,
                    quantity,
                    price,
                    currency,
                    fx_krw_per_usd=trade_fx_krw_per_usd,
                    exposure_currency=exposure_currency,
                    asset_class=asset_class,
                )
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
        # USD: 단가·평가는 현재 환율로 표시, 장부·손익은 매매 시점 환율 누적(평균원화단가) 반영
        # USDKRW는 단가가 이미 KRW/USD(원)이므로 환율을 한 번 더 곱하지 않음
        usd_mask = (display_df["currency"] == "USD") & (
            display_df["ticker"].str.upper() != FX_HEDGE_TICKER
        )
        display_df.loc[usd_mask, "averageCost"] = display_df.loc[usd_mask, "averageCostKrw"]
        display_df.loc[usd_mask, "currentPrice"] = display_df.loc[usd_mask, "currentPrice"] * exchange_rate
        display_df.loc[usd_mask, "currentValue"] = display_df.loc[usd_mask, "currentValueKrw"]
        display_df.loc[usd_mask, "unrealizedPnl"] = display_df.loc[usd_mask, "unrealizedPnlKrw"]
        display_df.loc[usd_mask, "realizedPnl"] = display_df.loc[usd_mask, "realizedPnlKrw"]
        display_df.loc[usd_mask, "returnRate"] = display_df.loc[usd_mask, "returnRateKrw"]
        display_df.loc[usd_mask, "currency"] = "KRW (환산)"
        fx_sym_mask = display_df["ticker"].str.upper() == FX_HEDGE_TICKER
        display_df.loc[fx_sym_mask, "currency"] = "KRW (USDKRW)"

    # 총합 계산
    if is_krw_mode:
        total_value = display_df["currentValueKrw"].sum()
        total_unrealized_pnl = display_df["unrealizedPnlKrw"].sum()
        total_realized_pnl = display_df["realizedPnlKrw"].sum()
        total_pnl_change = display_df["pnlChangeKrw"].sum()
    else:
        total_value = display_df["currentValue"].sum()
        total_unrealized_pnl = display_df["unrealizedPnl"].sum()
        total_realized_pnl = display_df["realizedPnl"].sum()
        # 전일 대비는 원화 기준으로만 계산
        total_pnl_change = df["pnlChangeKrw"].sum()

    # 상단 요약 지표 표시
    col1, col2, col3, col4, col5 = st.columns(5)
    
    def format_currency(val):
        if is_krw_mode:
            return f"₩{val:,.0f}"
        return f"{val:,.0f}"

    col1.metric("총 자산 평가액", format_currency(total_value))
    
    # 총 수익률 계산 (총 평가손익 / 총 투자원금)
    total_cost = total_value - total_unrealized_pnl
    pnl_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    col2.metric("총 평가 손익", format_currency(total_unrealized_pnl), f"{pnl_pct:,.0f}%")
    
    # 총 평가손익(당일)을 총 평가 손익 옆에 배치
    col3.metric("총 평가손익(당일)", format_currency(total_pnl_change))
    
    col4.metric("총 실현 손익", format_currency(total_realized_pnl))
    
    # 총 손익
    total_pnl = total_unrealized_pnl + total_realized_pnl
    col5.metric("총 손익", format_currency(total_pnl))

    st.divider()

    # 탭 구성
    tab1, tab2, tab3 = st.tabs(["포트폴리오 요약", "거래완료 내역", "매매 내역 관리"])

    with tab1:
        st.markdown("<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>현재 보유 종목</h3>", unsafe_allow_html=True)
        
        # 보유 수량이 0이 아닌 종목 (공매도·USDKRW 숏 포함)
        holdings_df = display_df[display_df["currentQuantity"] != 0].copy()
        
        if not holdings_df.empty:
            # 비중 계산
            holdings_df['weight'] = (holdings_df['currentValue'] / total_value) * 100
            
            # 화면 표시용 데이터프레임 정리 (companyName 추가)
            show_df = holdings_df[
                [
                    "ticker",
                    "companyName",
                    "exposure_currency",
                    "asset_class",
                    "currentQuantity",
                    "averageCost",
                    "currentPrice",
                    "currentValue",
                    "previousClosePrice",
                    "pnlChangeRate",
                    "pnlChangeKrw",
                    "unrealizedPnl",
                    "returnRate",
                    "realizedPnl",
                    "weight",
                ]
            ]
            show_df.columns = [
                "종목코드",
                "종목명",
                "노출통화",
                "자산군",
                "보유수량",
                "평균단가",
                "현재가",
                "평가금액",
                "전일가",
                "변동률(당일)",
                "평가손익(당일)",
                "평가손익(누적)",
                "누적수익률(%)",
                "매매손익",
                "비중(%)",
            ]
            
            # 포맷팅 설정 (모두 소수점 버림, 변동률(당일)는 소수 첫째자리)
            format_dict = {
                '보유수량': '{:,.0f}',
                '평균단가': '{:,.0f}',
                '현재가': '{:,.0f}',
                '평가금액': '{:,.0f}',
                '전일가': '{:,.0f}',
                '변동률(당일)': '{:,.1f}%',
                '평가손익(당일)': '{:,.0f}',
                '평가손익(누적)': '{:,.0f}',
                '누적수익률(%)': '{:,.0f}%',
                '매매손익': '{:,.0f}',
                '비중(%)': '{:,.0f}%'
            }
            
            # 음수값을 빨간색으로 표시하는 스타일 함수
            def highlight_negative(val):
                if isinstance(val, (int, float)):
                    if val < 0:
                        return 'color: red'
                return ''
            
            # 데이터프레임 스타일링 적용
            styled_df = show_df.style.format(format_dict)
            
            # 음수값이 있는 컬럼들에 대해 음수 하이라이팅 적용
            negative_columns = ['변동률(당일)', '평가손익(당일)', '평가손익(누적)', '누적수익률(%)', '매매손익']
            for col in negative_columns:
                if col in show_df.columns:
                    styled_df = styled_df.applymap(
                        highlight_negative,
                        subset=pd.IndexSlice[:, col]
                    )
            
            st.dataframe(styled_df, use_container_width=True)
            
            # 파이 차트 (보유 비중) — USDKRW는 평가 0·비중 제외이므로 차트에서도 제외
            st.markdown("<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>포트폴리오 자산 비중</h3>", unsafe_allow_html=True)
            pie_base = holdings_df[holdings_df["ticker"].str.upper() != FX_HEDGE_TICKER]
            if pie_base.empty:
                st.caption("표시할 일반 보유 자산이 없습니다. (USDKRW 헤지는 자산 비중 차트에 포함하지 않습니다.)")
            else:
                pie_hold = pie_base.assign(
                    _pie_slice=pie_base["currentValue"].abs(),
                )
                fig = px.pie(
                    pie_hold,
                    values="_pie_slice",
                    names="companyName",
                    title="종목별 자산 비중 (평가액 절대값 기준 조각)",
                    custom_data=["currentValueKrw"],
                )
                fig.update_traces(
                    texttemplate="<b>%{label}</b><br>₩%{customdata[0]:,.0f}<br>%{percent}",
                    textinfo="text",
                    textposition="inside",
                    insidetextorientation="horizontal",
                    hoverinfo="skip",
                )
                st.plotly_chart(fig, use_container_width=True)

            st.markdown(
                "<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>속성별 자산 비중</h3>",
                unsafe_allow_html=True,
            )
            st.caption(
                "조각 크기·비중은 그룹별 순평가액의 절대값 합으로 표시합니다. 표의 평가액(원)은 부호 있는 순액입니다."
            )
            by_asset = holdings_df.groupby("asset_class", as_index=False)["currentValueKrw"].sum()
            by_asset = by_asset.rename(columns={"currentValueKrw": "평가액_원"})
            by_asset["_slice"] = by_asset["평가액_원"].abs()
            by_asset = by_asset[by_asset["_slice"] > 1e-9]
            denom_a = float(by_asset["_slice"].sum())
            by_asset["비중(%)"] = by_asset["_slice"] / denom_a * 100 if denom_a > 0 else 0.0

            by_exposure = holdings_df.groupby("exposure_currency", as_index=False)["currentValueKrw"].sum()
            by_exposure = by_exposure.rename(columns={"currentValueKrw": "평가액_원"})
            by_exposure["_slice"] = by_exposure["평가액_원"].abs()
            by_exposure = by_exposure[by_exposure["_slice"] > 1e-9]
            denom_e = float(by_exposure["_slice"].sum())
            by_exposure["비중(%)"] = by_exposure["_slice"] / denom_e * 100 if denom_e > 0 else 0.0

            col_p1, col_p2 = st.columns(2)
            with col_p1:
                if not by_asset.empty:
                    fig_a = px.pie(
                        by_asset,
                        values="_slice",
                        names="asset_class",
                        title="자산군별 비중 (원화)",
                        custom_data=["평가액_원"],
                    )
                    fig_a.update_traces(
                        texttemplate="<b>%{label}</b><br>₩%{customdata[0]:,.0f}<br>%{percent}",
                        textinfo="text",
                        textposition="inside",
                        insidetextorientation="horizontal",
                        hoverinfo="skip",
                    )
                    st.plotly_chart(fig_a, use_container_width=True)
                    show_a = by_asset[["asset_class", "평가액_원", "비중(%)"]].copy()
                    show_a.columns = ["자산군", "평가액(원)", "비중(%)"]
                    st.dataframe(
                        show_a.style.format({"평가액(원)": "{:,.0f}", "비중(%)": "{:,.1f}%"}),
                        use_container_width=True,
                    )
                else:
                    st.info("자산군별 집계할 평가금액이 없습니다.")
            with col_p2:
                if not by_exposure.empty:
                    fig_e = px.pie(
                        by_exposure,
                        values="_slice",
                        names="exposure_currency",
                        title="노출통화별 비중 (원화)",
                        custom_data=["평가액_원"],
                    )
                    fig_e.update_traces(
                        texttemplate="<b>%{label}</b><br>₩%{customdata[0]:,.0f}<br>%{percent}",
                        textinfo="text",
                        textposition="inside",
                        insidetextorientation="horizontal",
                        hoverinfo="skip",
                    )
                    st.plotly_chart(fig_e, use_container_width=True)
                    show_e = by_exposure[["exposure_currency", "평가액_원", "비중(%)"]].copy()
                    show_e.columns = ["노출통화", "평가액(원)", "비중(%)"]
                    st.dataframe(
                        show_e.style.format({"평가액(원)": "{:,.0f}", "비중(%)": "{:,.1f}%"}),
                        use_container_width=True,
                    )
                else:
                    st.info("노출통화별 집계할 평가금액이 없습니다.")
        else:
            st.info("현재 보유 중인 주식이 없습니다. 사이드바에서 매수 내역을 추가해보세요!")

        st.divider()
        st.markdown(
            "<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>"
            "달러 노출 vs USDKRW (원화)</h3>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"**달러 노출 자산**: 노출통화가 USD인 종목(USDKRW 제외)의 원화 환산 평가액 합. "
            f"**USDKRW 평가**: 보유수량 × 현재 환율(1 USD = {exchange_rate:,.2f} KRW). "
            "숏은 음수. **넷 노출금액** = 위 둘의 합(원화 기준 근사)."
        )
        _mask_usd_exposure = (df["ticker"].str.upper() != FX_HEDGE_TICKER) & (
            df["exposure_currency"] == "USD"
        )
        _usd_exposure_krw = float(df.loc[_mask_usd_exposure, "currentValueKrw"].sum())
        _usdkrw_part = df[df["ticker"].str.upper() == FX_HEDGE_TICKER]
        _usdkrw_krw = (
            float((_usdkrw_part["currentQuantity"] * exchange_rate).sum())
            if not _usdkrw_part.empty
            else 0.0
        )
        _net_exposure_krw = _usd_exposure_krw + _usdkrw_krw

        if abs(_usd_exposure_krw) > 1e-6 or abs(_usdkrw_krw) > 1e-6:
            _m1, _m2, _m3 = st.columns(3)
            _m1.metric("달러 노출 자산(원)", f"₩{_usd_exposure_krw:,.0f}")
            _m2.metric("USDKRW 평가(원)", f"₩{_usdkrw_krw:,.0f}")
            _m3.metric("넷 노출금액(원)", f"₩{_net_exposure_krw:,.0f}")
        else:
            st.caption("표시할 달러 노출 자산 또는 USDKRW 포지션이 없습니다.")

    with tab2:
        st.markdown("<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>거래완료 내역</h3>", unsafe_allow_html=True)
        st.caption("현재 거래가 있지만 보유 잔고가 없는 종목 (완전 매도된 종목)의 최종 매매손익")
        
        # 거래완료 종목: 실현 손익이 있지만 현재 수량이 0인 종목
        completed_df = df[(df["realizedPnlKrw"] != 0) & (abs(df["currentQuantity"]) < 1e-12)].copy()
        
        if not completed_df.empty:
            # 원화 환산 모드 적용
            display_completed = completed_df.copy()
            if is_krw_mode:
                usd_mask_c = (display_completed["currency"] == "USD") & (
                    display_completed["ticker"].str.upper() != FX_HEDGE_TICKER
                )
                display_completed.loc[usd_mask_c, "averageCost"] = display_completed.loc[usd_mask_c, "averageCostKrw"]
                display_completed.loc[usd_mask_c, "currency"] = "KRW (환산)"
            
            # 표시용 데이터프레임
            completed_show = display_completed[
                [
                    "ticker",
                    "companyName",
                    "currency",
                    "exposure_currency",
                    "asset_class",
                    "averageCost",
                    "realizedPnlKrw",
                ]
            ].copy()
            
            completed_show.columns = [
                "종목코드",
                "종목명",
                "통화",
                "노출통화",
                "자산군",
                "평균 매입가",
                "최종 매매손익",
            ]
            
            completed_format = {
                '평균 매입가': '{:,.0f}',
                '최종 매매손익': '{:,.0f}',
            }
            
            # 음수값을 빨간색으로 표시
            def highlight_negative_completed(val):
                if isinstance(val, (int, float)):
                    if val < 0:
                        return 'color: red'
                return ''
            
            styled_completed = completed_show.style.format(completed_format)
            styled_completed = styled_completed.applymap(
                highlight_negative_completed,
                subset=pd.IndexSlice[:, '최종 매매손익']
            )
            
            st.dataframe(styled_completed, use_container_width=True)
        else:
            st.info("거래완료 내역이 없습니다.")

    with tab3:
        st.markdown("<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>전체 매매 내역</h3>", unsafe_allow_html=True)
        # 최신 데이터를 다시 불러옴
        current_history_df = load_trade_history()
        
        if not current_history_df.empty:
            # 종목명 컬럼 추가
            current_history_df['종목명'] = current_history_df['ticker'].apply(get_company_name)
            
            if "fx_krw_per_usd" not in current_history_df.columns:
                current_history_df["fx_krw_per_usd"] = pd.NA
                current_history_df.loc[current_history_df["currency"] == "KRW", "fx_krw_per_usd"] = 1.0
            if "exposure_currency" not in current_history_df.columns:
                current_history_df["exposure_currency"] = "KRW"
            if "asset_class" not in current_history_df.columns:
                current_history_df["asset_class"] = "지수형"

            # 명시적으로 컬럼 순서 지정 (데이터프레임의 실제 컬럼 순서가 꼬여있을 수 있으므로)
            current_history_df = current_history_df[
                [
                    "date",
                    "account",
                    "ticker",
                    "종목명",
                    "tradeType",
                    "quantity",
                    "price",
                    "currency",
                    "fx_krw_per_usd",
                    "exposure_currency",
                    "asset_class",
                ]
            ]

            # 컬럼명 한글화
            current_history_df.columns = [
                "매매일자",
                "계좌명",
                "종목코드",
                "종목명",
                "매매종류",
                "수량",
                "단가",
                "결제통화",
                "환율(1USD=KRW)",
                "노출통화",
                "자산군",
            ]

            # 데이터 타입 명시적 변환 (문자열이 섞여있을 경우 포맷팅 에러 방지)
            current_history_df['수량'] = pd.to_numeric(current_history_df['수량'], errors='coerce').fillna(0)
            current_history_df['단가'] = pd.to_numeric(current_history_df['단가'], errors='coerce').fillna(0)
            fx_col = "환율(1USD=KRW)"
            current_history_df[fx_col] = pd.to_numeric(current_history_df[fx_col], errors='coerce')

            # 매매 내역 포맷팅 (수량, 단가 소수점 버림)
            history_format_dict = {
                '수량': '{:,.0f}',
                '단가': '{:,.0f}',
                fx_col: '{:,.2f}',
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
                        raw_exp = row_data.get("exposure_currency", "KRW")
                        if raw_exp is None or (isinstance(raw_exp, float) and pd.isna(raw_exp)):
                            raw_exp = "KRW"
                        edit_exposure = st.selectbox(
                            "노출통화",
                            list(EXPOSURE_CURRENCY_OPTIONS),
                            index=list(EXPOSURE_CURRENCY_OPTIONS).index(str(raw_exp).upper() if str(raw_exp).upper() in EXPOSURE_CURRENCY_OPTIONS else "KRW"),
                            key=f"edit_exp_{edit_index}",
                        )
                        raw_ac = row_data.get("asset_class", NEW_TRADE_DEFAULT_ASSET_CLASS)
                        if raw_ac is None or (isinstance(raw_ac, float) and pd.isna(raw_ac)):
                            raw_ac = NEW_TRADE_DEFAULT_ASSET_CLASS
                        raw_ac = str(raw_ac).strip()
                        ac_idx = list(ASSET_CLASS_OPTIONS).index(raw_ac) if raw_ac in ASSET_CLASS_OPTIONS else 0
                        edit_asset_class = st.selectbox(
                            "자산군",
                            list(ASSET_CLASS_OPTIONS),
                            index=ac_idx,
                            key=f"edit_ac_{edit_index}",
                        )
                    with col_e2:
                        edit_type = st.selectbox("매매 종류", ["매수", "매도"], index=0 if row_data['tradeType'] in ['Buy', '매수'] else 1, key=f"edit_type_{edit_index}")
                        edit_quantity = st.number_input("수량", min_value=0.01, value=float(row_data['quantity']), step=1.0, key=f"edit_qty_{edit_index}")
                    with col_e3:
                        edit_price = st.number_input("단가", min_value=0.01, value=float(row_data['price']), step=1.0, key=f"edit_price_{edit_index}")
                        edit_currency = st.selectbox("통화", ["KRW", "USD"], index=0 if row_data['currency'] == 'KRW' else 1, key=f"edit_currency_{edit_index}")
                        raw_edit_fx = row_data.get("fx_krw_per_usd")
                        if edit_currency == "USD":
                            edit_fx_default = (
                                float(raw_edit_fx)
                                if raw_edit_fx is not None and not pd.isna(raw_edit_fx)
                                else float(get_exchange_rate())
                            )
                            edit_fx_krw = st.number_input(
                                "매매 당시 환율 (1 USD = KRW)",
                                min_value=0.01,
                                value=edit_fx_default,
                                step=1.0,
                                key=f"edit_fx_{edit_index}",
                            )
                        else:
                            edit_fx_krw = 1.0
                    
                    col_btn1, col_btn2 = st.columns([1, 10])
                    with col_btn1:
                        if st.button("수정", type="primary", key=f"btn_update_{edit_index}"):
                            expected_currency = ACCOUNT_CURRENCY_MAP.get(edit_account, edit_currency)
                            if edit_currency != expected_currency:
                                st.error(f"🚨 수정 오류: [{edit_account}] 계좌는 {expected_currency} 전용입니다. 통화를 확인해주세요.")
                            else:
                                if update_trade(
                                    edit_index,
                                    edit_date,
                                    edit_account,
                                    edit_ticker,
                                    edit_type,
                                    edit_quantity,
                                    edit_price,
                                    edit_currency,
                                    fx_krw_per_usd=edit_fx_krw,
                                    exposure_currency=edit_exposure,
                                    asset_class=edit_asset_class,
                                ):
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
