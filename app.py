import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, time, datetime
import os
from utils.logging_config import setup_logging, read_log_file
from utils.ls_t3521 import get_price_and_change_rate as get_overseas_macro_quote
from utils.ls_t1511 import get_price_and_change_rate as get_domestic_index_quote
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
)
from utils.product_master import (
    get_product,
    add_or_update_product,
    get_all_tags,
)  # get_all_tags 임포트

GREEN_BAR_COLORS = ["#C8E6C9", "#A5D6A7", "#66BB6A", "#43A047", "#2E7D32"]
RED_BAR_COLORS = ["#FFCDD2", "#EF9A9A", "#E57373", "#EF5350", "#C62828"]


def _format_rank_bar_label(value, value_kind):
    if value_kind == "percent":
        return f"{value:,.1f}%"
    return f"{value:,.0f}"


def _rank_bar_colors(count, is_top):
    palette = GREEN_BAR_COLORS if is_top else RED_BAR_COLORS
    if count <= 1:
        return [palette[-1]]
    step = (len(palette) - 1) / (count - 1)
    return [palette[min(int(round(i * step)), len(palette) - 1)] for i in range(count)]


def _build_rank_bar_chart(data, value_col, *, is_top, value_kind, x_title):
    if data.empty:
        return None

    chart_df = data[["companyName", value_col]].copy()
    if is_top:
        chart_df = chart_df.sort_values(value_col, ascending=True)
        bar_values = chart_df[value_col]
    else:
        chart_df["_bar_value"] = chart_df[value_col].abs()
        chart_df = chart_df.sort_values("_bar_value", ascending=True)
        bar_values = chart_df["_bar_value"]

    colors = _rank_bar_colors(len(chart_df), is_top)
    text_labels = [_format_rank_bar_label(v, value_kind) for v in chart_df[value_col]]

    fig = go.Figure(
        go.Bar(
            y=chart_df["companyName"],
            x=bar_values,
            orientation="h",
            marker_color=colors,
            text=text_labels,
            textposition="outside",
            cliponaxis=False,
            hovertemplate="%{y}<br>%{text}<extra></extra>",
        )
    )
    fig.update_layout(
        height=300,
        showlegend=False,
        margin=dict(l=20, r=80, t=20, b=20),
        xaxis_title=x_title,
        yaxis_title="",
    )
    fig.update_xaxes(
        range=[0, float(bar_values.max()) * 1.15 if len(bar_values) else 1]
    )
    return fig


def _render_rank_chart_pair(
    col_left,
    col_right,
    title_top,
    title_bottom,
    chart_data,
    value_col,
    value_kind,
    x_title,
):
    with col_left:
        st.markdown(f"**{title_top}**")
        top_df = chart_data.nlargest(5, value_col)[["companyName", value_col]]
        fig_top = _build_rank_bar_chart(
            top_df,
            value_col,
            is_top=True,
            value_kind=value_kind,
            x_title=x_title,
        )
        if fig_top is not None:
            st.plotly_chart(fig_top, width="stretch")
        else:
            st.caption("표시할 데이터가 없습니다.")

    with col_right:
        st.markdown(f"**{title_bottom}**")
        bottom_df = chart_data.nsmallest(5, value_col)[["companyName", value_col]]
        fig_bottom = _build_rank_bar_chart(
            bottom_df,
            value_col,
            is_top=False,
            value_kind=value_kind,
            x_title=x_title,
        )
        if fig_bottom is not None:
            st.plotly_chart(fig_bottom, width="stretch")
        else:
            st.caption("표시할 데이터가 없습니다.")


@st.cache_data(ttl=30, show_spinner=False)
def _get_macro_snapshot():
    snapshot = []

    for upcode, label in [("001", "코스피"), ("301", "코스닥")]:
        price, change_rate = get_domestic_index_quote(upcode)
        snapshot.append(
            {
                "label": label,
                "symbol": upcode,
                "price": price,
                "change_rate": change_rate,
            }
        )

    for kind, symbol, label in [
        ("S", "SPI@SPX", "S&P 500"),
        ("S", "NAS@IXIC", "나스닥 종합"),
        ("R", "USDKRWSMBS", "원/달러"),
    ]:
        price, change_rate = get_overseas_macro_quote(kind, symbol)
        snapshot.append(
            {
                "label": label,
                "symbol": symbol,
                "price": price,
                "change_rate": change_rate,
            }
        )

    return snapshot


def _format_macro_price(price):
    if price is None:
        return "-"
    return f"{price:,.2f}"


# 페이지 기본 설정
st.set_page_config(page_title="주식 포트폴리오 트래커", layout="wide")

# 로깅 설정
setup_logging()

# 사이드바 - 로그 뷰어 제거
# (메인 화면으로 이동)

# 매매 내역 로드 (기존 종목/계좌 확인용)
history_df = load_trade_history()
existing_tickers = (
    history_df["ticker"].unique().tolist() if not history_df.empty else []
)
existing_accounts = (
    history_df["account"].unique().tolist()
    if not history_df.empty and "account" in history_df.columns
    else []
)

# --- 사이드바: 매매 내역 추가 ---
st.sidebar.header("새 매매 내역 추가")

# 계좌 입력 방식 선택
account_option = st.sidebar.radio(
    "계좌 입력 방식", ["기존 계좌 선택", "새 계좌 직접 입력"]
)
account = ""

if account_option == "기존 계좌 선택":
    if existing_accounts:
        account = st.sidebar.selectbox("계좌 선택", existing_accounts)
    else:
        st.sidebar.warning("기존 계좌가 없습니다. '새 계좌 직접 입력'을 선택해주세요.")
else:
    account = st.sidebar.text_input("새 계좌명", "새계좌")

# 종목 입력 방식 선택 (기존 종목 vs 직접 입력)
ticker_option = st.sidebar.radio(
    "종목 입력 방식", ["기존 종목 선택", "새 종목 직접 입력"]
)

ticker = ""
if ticker_option == "기존 종목 선택":
    if existing_tickers:
        # 기존 종목 선택 시 종목명과 티커를 함께 표시
        ticker = st.sidebar.selectbox(
            "종목 선택",
            sorted(existing_tickers, key=lambda x: get_company_name(x)),
            format_func=lambda x: f"{get_company_name(x)} ({x})",
        )
    else:
        st.sidebar.warning(
            "기존 매매 내역이 없습니다. '새 종목 직접 입력'을 선택해주세요."
        )
else:
    ticker = st.sidebar.text_input("종목 코드 (예: AAPL, 005930)", "").upper()
    st.sidebar.caption(
        "한국 주식은 LS증권 6자리 코드(예: 005930). "
        "단가는 KRW/USD(원화 환율)이며, 매도를 먼저 넣어도 됩니다."
    )

# 종목이 선택/입력되면 현재가 표시 (한 번만 조회)
current_price = 0.0
product_info = None
if ticker:
    # 세션 스테이트에 저장된 티커와 다르면 새로 조회
    if "last_ticker" not in st.session_state or st.session_state.last_ticker != ticker:
        company_name = get_company_name(ticker)
        current_price = get_current_price(ticker)
        product_info = get_product(ticker)

        # 세션에 저장
        st.session_state.last_ticker = ticker
        st.session_state.last_company_name = company_name
        st.session_state.last_current_price = current_price
        st.session_state.last_product_info = product_info
    else:
        # 저장된 값 사용
        company_name = st.session_state.last_company_name
        current_price = st.session_state.last_current_price
        product_info = st.session_state.last_product_info

    st.sidebar.info(f"**{company_name} ({ticker})**\n\n현재가: {current_price:,.0f}")

trade_form_fx_default = get_exchange_rate()
# form 대신 container 사용 (엔터키 자동 제출 방지)
with st.sidebar.container():
    trade_date = st.date_input("매매 일자", date.today())
    
    # 시간 입력 (시, 분, 초)
    col_time_h, col_time_m, col_time_s = st.columns(3)
    with col_time_h:
        trade_hour = st.number_input("시(h)", min_value=0, max_value=23, value=9, step=1)
    with col_time_m:
        trade_minute = st.number_input("분(m)", min_value=0, max_value=59, value=0, step=1)
    with col_time_s:
        trade_second = st.number_input("초(s)", min_value=0, max_value=59, value=0, step=1)
    
    trade_time = time(hour=int(trade_hour), minute=int(trade_minute), second=int(trade_second))
    
    trade_type = st.selectbox("매매 종류", ["매수", "매도"])

    # 태그 입력 필드 (새 종목 또는 기존 종목에 태그가 없는 경우)
    current_tags_for_ticker = product_info.get("tags", []) if product_info else []
    if ticker_option == "새 종목 직접 입력" or not current_tags_for_ticker:
        tags_input_existing = st.multiselect(
            "태그 선택 (기존 태그)",
            options=get_all_tags(),
            default=current_tags_for_ticker,
            key="ticker_tags_multiselect",
        )
        new_tags_str = st.text_input(
            "새 태그 직접 입력 (여러 개는 쉼표로 구분)", key="ticker_new_tags_input"
        )

        tags_input = list(tags_input_existing)
        if new_tags_str:
            new_tags = [t.strip() for t in new_tags_str.split(",") if t.strip()]
            for t in new_tags:
                if t not in tags_input:
                    tags_input.append(t)
    else:
        # 기존 종목: product_master tags만 표시 (multiselect session_state 오염 방지)
        tags_input = list(current_tags_for_ticker)
        tag_display = ", ".join(current_tags_for_ticker) if current_tags_for_ticker else "(없음)"
        st.markdown(f"**태그** (기존 종목 · 수정불가): {tag_display}")

    # 새 종목 입력 모드와 기존 종목 선택 모드 구분
    if ticker_option == "새 종목 직접 입력":
        # 새 종목: 모든 조건 필수 입력
        st.subheader("⚠️ 모든 항목을 명시적으로 설정해주세요")

        # 결제 통화 (필수)
        currency_required = st.selectbox(
            "결제 통화 *",
            ["선택하세요", "KRW", "USD"],
            help="종목의 거래 통화를 선택하세요",
        )
        currency = None if currency_required == "선택하세요" else currency_required

        # 노출통화 (필수)
        exposure_required = st.selectbox(
            "노출통화 (환율 리스크) *",
            ["선택하세요"] + list(EXPOSURE_CURRENCY_OPTIONS),
            help="종목의 환율 리스크 노출 통화를 선택하세요",
        )
        exposure_currency = (
            None if exposure_required == "선택하세요" else exposure_required
        )

        # 자산군 (필수)
        asset_class_required = st.selectbox(
            "자산군 *",
            ["선택하세요"] + list(ASSET_CLASS_OPTIONS),
            help="주식, ETF, 선물 등 자산군을 선택하세요",
        )
        asset_class = (
            None if asset_class_required == "선택하세요" else asset_class_required
        )

        # 시장 (필수)
        market_required = st.selectbox(
            "시장 (Market) *",
            ["선택하세요", "KRX", "NASDAQ", "NYSE", "CME"],
            help="종목이 거래되는 시장을 선택하세요",
        )
        market = None if market_required == "선택하세요" else market_required

        # 거래승수 (필수)
        multiplier = st.number_input(
            "거래승수 (Multiplier) *",
            min_value=0.0,
            value=0.0,
            step=1.0,
            help="주식은 1, 달러선물은 10000 등. 0.0은 미입력 상태로 간주됩니다",
        )

    else:
        # 기존 종목: 기본값 사용
        currency_idx = 0  # 기본 KRW
        if product_info and product_info.get("settlement_currency"):
            currency_idx = 0 if product_info["settlement_currency"] == "KRW" else 1
        currency = st.selectbox("결제 통화", ["KRW", "USD"], index=currency_idx)

        exposure_default_idx = 1 if currency == "USD" else 0
        if product_info and product_info.get("exposure_currency"):
            exposure_default_idx = (
                list(EXPOSURE_CURRENCY_OPTIONS).index(product_info["exposure_currency"])
                if product_info["exposure_currency"] in EXPOSURE_CURRENCY_OPTIONS
                else exposure_default_idx
            )
        exposure_currency = st.selectbox(
            "노출통화 (환율 리스크)",
            list(EXPOSURE_CURRENCY_OPTIONS),
            index=exposure_default_idx,
            help="결제 통화와 다를 수 있습니다. 예: 국내 상장 KODEX 나스닥100은 원화로 거래되어도 미국 지수·달러 자산에 노출될 수 있어 노출통화를 USD로 둘 수 있습니다.",
        )

        ac_default_idx = list(ASSET_CLASS_OPTIONS).index(NEW_TRADE_DEFAULT_ASSET_CLASS)
        if product_info and product_info.get("asset_class"):
            ac_default_idx = (
                list(ASSET_CLASS_OPTIONS).index(product_info["asset_class"])
                if product_info["asset_class"] in ASSET_CLASS_OPTIONS
                else ac_default_idx
            )
        asset_class = st.selectbox(
            "자산군",
            list(ASSET_CLASS_OPTIONS),
            index=ac_default_idx,
        )

        market_default = product_info.get("market", "KRX") if product_info else "KRX"
        market = st.selectbox(
            "시장 (Market)",
            ["KRX", "NASDAQ", "NYSE", "CME"],
            index=(
                ["KRX", "NASDAQ", "NYSE", "CME"].index(market_default)
                if market_default in ["KRX", "NASDAQ", "NYSE", "CME"]
                else 0
            ),
        )

        multiplier_default = (
            product_info.get("multiplier", 1.0) if product_info else 1.0
        )
        multiplier = st.number_input(
            "거래승수 (Multiplier)",
            min_value=0.01,
            value=float(multiplier_default),
            step=1.0,
            help="주식은 1, 달러선물은 10000 등",
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
    elif currency is None and ticker_option == "새 종목 직접 입력":
        # 새 종목 입력 모드에서 결제통화가 선택되지 않은 경우
        st.text_input(
            "매매 당시 환율 (1 USD = ? KRW)",
            value="",
            placeholder="결제 통화를 먼저 선택해주세요",
            disabled=True,
        )

    st.divider()

    # 수량, 단가 입력
    st.markdown("**📊 거래 수량 및 단가**")
    qty_col, price_col = st.columns(2)

    with qty_col:
        quantity = st.number_input(
            "수량", min_value=0.01, value=1.0, step=1.0, key="quantity_input"
        )

    with price_col:
        default_price = float(current_price) if current_price >= 0.01 else 0.01
        price = st.number_input(
            "단가", min_value=0.01, value=default_price, step=1.0, key="price_input"
        )

    # 내역 추가 버튼
    st.divider()
    st.caption("⚠️ 아래 '내역 추가' 버튼을 클릭해야만 매매 내역이 저장됩니다")
    submit_button = st.button("✅ 내역 추가", type="primary", width="stretch")

if submit_button:
    # 기본 검증
    error_messages = []

    if not ticker:
        error_messages.append("종목 코드를 입력해주세요.")
    if not account:
        error_messages.append("계좌명을 입력해주세요.")

    # 새 종목 입력 모드 추가 검증
    if ticker_option == "새 종목 직접 입력":
        if currency is None:
            error_messages.append("결제 통화를 선택해주세요.")
        if exposure_currency is None:
            error_messages.append("노출통화를 선택해주세요.")
        if asset_class is None:
            error_messages.append("자산군을 선택해주세요.")
        if market is None:
            error_messages.append("시장을 선택해주세요.")
        if multiplier <= 0.0:
            error_messages.append("거래승수는 0보다 커야 합니다.")

    if error_messages:
        error_text = "\n".join(f"• {msg}" for msg in error_messages)
        st.sidebar.error(f"입력 오류:\n{error_text}")
    else:
        # 데이터 디렉토리 확인
        if not os.path.exists("data"):
            os.makedirs("data")

        # Product Master 업데이트 (새 종목인 경우)
        if ticker_option == "새 종목 직접 입력":
            add_or_update_product(
                ticker,
                asset_class,
                market,
                currency,
                exposure_currency,
                multiplier,
                name=company_name,
                tags=tags_input,
            )

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
            trade_time=trade_time,
        )
        st.sidebar.success(f"[{account}] {ticker} {quantity}주 {trade_type} 추가 완료!")
        st.rerun()  # 앱 새로고침

# --- 메인 화면 ---
col_title, col_btn = st.columns([4, 1])
with col_title:
    st.markdown(
        "<h2 style='font-size: 1.5rem; margin-bottom: 20px;'>주식 포트폴리오 트래커</h2>",
        unsafe_allow_html=True,
    )
with col_btn:
    if st.button("🔄 현재가 업데이트"):
        st.rerun()

macro_cols = st.columns(5)
for col, item in zip(macro_cols, _get_macro_snapshot()):
    delta_text = (
        f"{item['change_rate']:.2f}%" if item["change_rate"] is not None else "-"
    )
    with col:
        st.metric(
            f"{item['label']} ({item['symbol']})",
            _format_macro_price(item["price"]),
            delta_text,
        )

st.divider()

# --- 로그 뷰어 (메인 화면) ---
with st.expander("📋 **API 로그 뷰어** (최근 50줄)", expanded=False):
    log_content = read_log_file(num_lines=50)
    st.code(log_content, language="log")

st.divider()

# 환율 가져오기
exchange_rate = get_exchange_rate()

# 전체 원화 환산 모드로 고정
is_krw_mode = True

col_filters = st.columns([1, 1, 2])  # 1/4, 1/4, 나머지
with col_filters[0]:
    # 계좌 필터
    account_list = ["전체 계좌"] + existing_accounts
    selected_account = st.selectbox("조회할 계좌 선택", account_list)

with col_filters[1]:
    all_tags = ["전체 태그"] + get_all_tags()
    selected_tag = st.selectbox("조회할 태그 선택", all_tags)

# 포트폴리오 데이터 계산 (선택된 계좌 필터 적용)
# 태그 선택 시 계좌는 '전체 계좌'로 고정
if selected_tag != "전체 태그":
    df = calculate_portfolio("전체 계좌", selected_tag)
else:
    df = calculate_portfolio(selected_account)


if not df.empty:
    # 항상 원화 환산으로 표시
    display_df = df.copy()

    # USD: 평가손익은 원화 기준으로 표시, 단가/가격은 USD 원본 유지
    usd_mask = (display_df["currency"] == "USD") & (display_df["asset_class"] != "선물")
    display_df.loc[usd_mask, "currentValue"] = display_df.loc[
        usd_mask, "currentValueKrw"
    ]
    display_df.loc[usd_mask, "unrealizedPnl"] = display_df.loc[
        usd_mask, "unrealizedPnlKrw"
    ]
    display_df.loc[usd_mask, "realizedPnl"] = display_df.loc[usd_mask, "realizedPnlKrw"]
    display_df.loc[usd_mask, "returnRate"] = display_df.loc[usd_mask, "returnRateKrw"]

    # 총합 계산 - 항상 원화 기준
    total_value = display_df[display_df["asset_class"] != "선물"][
        "currentValueKrw"
    ].sum()
    total_unrealized_pnl = display_df["unrealizedPnlKrw"].sum()
    total_realized_pnl = display_df["realizedPnlKrw"].sum()
    total_pnl_change = display_df["pnlChangeKrw"].sum()

    # 상단 요약 지표 표시
    col1, col2, col3, col4, col5 = st.columns(5)

    def format_currency(val):
        # 원화 기호 없이 숫자만 표시
        return f"{val:,.0f}"

    col1.metric("총 자산 평가액", format_currency(total_value))

    # 총 수익률 계산 (총 평가손익 / 총 투자원금)
    total_cost = total_value - total_unrealized_pnl
    pnl_pct = (total_unrealized_pnl / total_cost * 100) if total_cost > 0 else 0.0
    col2.metric(
        "평가손익(누적)", format_currency(total_unrealized_pnl), f"{pnl_pct:,.0f}%"
    )

    # 총 평가손익(당일)을 총 평가 손익 옆에 배치
    daily_pnl_pct = (total_pnl_change / total_value * 100) if total_value > 0 else 0.0
    col3.metric(
        "평가손익(당일)", format_currency(total_pnl_change), f"{daily_pnl_pct:,.2f}%"
    )

    col4.metric("총 실현 손익", format_currency(total_realized_pnl))

    # 총 손익
    total_pnl = total_unrealized_pnl + total_realized_pnl
    col5.metric("총 손익", format_currency(total_pnl))

    st.divider()

    # 탭 구성
    tab1, tab2, tab3 = st.tabs(["포트폴리오 요약", "거래완료 내역", "매매 내역 관리"])

    with tab1:
        st.markdown(
            "<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>현재 보유 종목</h3>",
            unsafe_allow_html=True,
        )

        # 보유 수량이 0이 아닌 종목 (공매도·USDKRW 숏 포함)
        holdings_df = display_df[display_df["currentQuantity"] != 0].copy()

        if not holdings_df.empty:
            # 비중 계산 (선물 제외)
            non_futures = holdings_df[holdings_df["asset_class"] != "선물"]
            valid_total = non_futures["currentValue"].sum()
            holdings_df.loc[holdings_df["asset_class"] != "선물", "weight"] = (
                holdings_df.loc[holdings_df["asset_class"] != "선물", "currentValue"]
                / valid_total
                * 100
                if valid_total > 0
                else 0.0
            )
            holdings_df.loc[holdings_df["asset_class"] == "선물", "weight"] = 0.0

            # 화면 표시용 데이터프레임 정리 (companyName, tags 추가)
            if "tags" in holdings_df.columns:
                holdings_df["tags_str"] = holdings_df["tags"].apply(
                    lambda x: ", ".join(x) if isinstance(x, list) else ""
                )
            else:
                holdings_df["tags_str"] = ""

            show_df = holdings_df[
                [
                    "companyName",
                    "ticker",
                    "tags_str",
                    # "currency", # 결제통화 삭제
                    # "exposure_currency", # 노출통화 삭제
                    "asset_class",
                    "currentQuantity",
                    "averageCost",
                    "currentPrice",
                    "previousClosePrice",
                    "pnlChangeRate",
                    "currentValue",
                    "pnlChangeKrw",
                    "unrealizedPnlKrw",
                    "returnRate",
                    "realizedPnlKrw",
                    "weight",
                ]
            ].copy()

            show_df.columns = [
                "종목명",
                "종목코드",
                "태그",
                "자산군",
                "보유수량",
                "평균단가",
                "현재가",
                "전일가",
                "변동률(당일)",
                "평가금액",
                "평가손익(당일)",
                "평가손익(누적)",
                "누적수익률(%)",
                "매매손익",
                "비중(%)",
            ]

            # 총손익 = 평가손익(누적) + 매매손익 (표시 컬럼 단순 합산)
            show_df.insert(
                len(show_df.columns) - 1,
                "총손익",
                show_df["평가손익(누적)"] + show_df["매매손익"],
            )

            # 통화별 단가/가격 포맷팅 함수
            def format_price_by_currency(val, currency):
                """USD는 소수 둘째자리 + $, KRW는 소수점 없음"""
                if pd.isna(val) or not isinstance(val, (int, float)):
                    return val
                if currency == "USD":
                    return f"${val:,.2f}"
                else:
                    return f"{val:,.0f}"

            # 평균단가, 현재가, 전일가를 통화별로 포맷팅하여 문자열로 변환
            for col_idx, col_name in enumerate(["평균단가", "현재가", "전일가"]):
                # show_df는 결제통화 컬럼이 없으므로, holdings_df에서 원본 currency를 가져와 사용
                show_df[col_name] = show_df.apply(
                    lambda row: format_price_by_currency(
                        row[col_name], holdings_df.loc[row.name, "currency"]
                    ),
                    axis=1,
                )

            # 포맷팅 설정 (모두 소수점 버림, 변동률(당일)는 소수 첫째자리)
            format_dict = {
                "보유수량": "{:,.0f}",
                "평가금액": "{:,.0f}",
                "변동률(당일)": "{:,.1f}%",
                "평가손익(당일)": "{:,.0f}",
                "평가손익(누적)": "{:,.0f}",
                "누적수익률(%)": "{:,.0f}%",
                "매매손익": "{:,.0f}",
                "총손익": "{:,.0f}",
                "비중(%)": "{:,.0f}%",
            }

            # 음수값을 빨간색으로 표시하는 스타일 함수
            def highlight_negative(val):
                if isinstance(val, (int, float)):
                    if val < 0:
                        return "color: red"
                return ""

            # 데이터프레임 스타일링 적용
            styled_df = show_df.style.format(format_dict)

            # 음수값이 있는 컬럼들에 대해 음수 하이라이팅 적용
            negative_columns = [
                "변동률(당일)",
                "평가손익(당일)",
                "평가손익(누적)",
                "누적수익률(%)",
                "매매손익",
                "총손익",
            ]
            for col in negative_columns:
                if col in show_df.columns:
                    styled_df = styled_df.map(
                        highlight_negative, subset=pd.IndexSlice[:, col]
                    )

            st.dataframe(
                styled_df,
                width="stretch",
                column_config={
                    "종목명": st.column_config.TextColumn(
                        "종목명", width="medium", pinned=True  # 종목명 컬럼 고정
                    )
                },
            )

            # 4개의 Bar 차트 추가 (당일손익률, 당일손익금액, 누적손익률, 누적손익)
            st.markdown(
                "<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>손익 분석</h3>",
                unsafe_allow_html=True,
            )

            # 차트용 데이터 준비 (선물 제외, 보유수량 > 0)
            chart_data = holdings_df[
                (holdings_df["asset_class"] != "선물")
                & (holdings_df["currentQuantity"] > 0)
            ].copy()

            if not chart_data.empty:
                col_chart1, col_chart2 = st.columns(2)
                _render_rank_chart_pair(
                    col_chart1,
                    col_chart2,
                    "당일손익률 상위 5위",
                    "당일손익률 하위 5위",
                    chart_data,
                    "pnlChangeRate",
                    "percent",
                    "당일손익률(%)",
                )

                col_chart3, col_chart4 = st.columns(2)
                _render_rank_chart_pair(
                    col_chart3,
                    col_chart4,
                    "당일손익금액 상위 5위",
                    "당일손익금액 하위 5위",
                    chart_data,
                    "pnlChangeKrw",
                    "amount",
                    "당일손익금액(₩)",
                )

                col_chart5, col_chart6 = st.columns(2)
                _render_rank_chart_pair(
                    col_chart5,
                    col_chart6,
                    "누적손익률 상위 5위",
                    "누적손익률 하위 5위",
                    chart_data,
                    "returnRate",
                    "percent",
                    "누적손익률(%)",
                )

                col_chart7, col_chart8 = st.columns(2)
                _render_rank_chart_pair(
                    col_chart7,
                    col_chart8,
                    "누적손익금액 상위 5위",
                    "누적손익금액 하위 5위",
                    chart_data,
                    "unrealizedPnl",
                    "amount",
                    "누적손익금액(₩)",
                )

            pie_base = holdings_df[holdings_df["asset_class"] != "선물"]
            if pie_base.empty:
                st.caption("표시할 일반 보유 자산이 없습니다.")
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
                st.plotly_chart(fig, width="stretch")

            st.markdown(
                "<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>속성별 자산 비중</h3>",
                unsafe_allow_html=True,
            )
            st.caption(
                "조각 크기·비중은 그룹별 순평가액의 절대값 합으로 표시합니다. 표의 평가액(원)은 부호 있는 순액입니다."
            )
            by_asset = (
                holdings_df[holdings_df["asset_class"] != "선물"]
                .groupby("asset_class", as_index=False)["currentValueKrw"]
                .sum()
            )
            by_asset = by_asset.rename(columns={"currentValueKrw": "평가액_원"})
            by_asset["_slice"] = by_asset["평가액_원"].abs()
            by_asset = by_asset[by_asset["_slice"] > 1e-9]
            denom_a = float(by_asset["_slice"].sum())
            by_asset["비중(%)"] = (
                by_asset["_slice"] / denom_a * 100 if denom_a > 0 else 0.0
            )

            by_exposure = (
                holdings_df[holdings_df["asset_class"] != "선물"]
                .groupby("exposure_currency", as_index=False)["currentValueKrw"]
                .sum()
            )
            by_exposure = by_exposure.rename(columns={"currentValueKrw": "평가액_원"})
            by_exposure["_slice"] = by_exposure["평가액_원"].abs()
            by_exposure = by_exposure[by_exposure["_slice"] > 1e-9]
            denom_e = float(by_exposure["_slice"].sum())
            by_exposure["비중(%)"] = (
                by_exposure["_slice"] / denom_e * 100 if denom_e > 0 else 0.0
            )

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
                    st.plotly_chart(fig_a, width="stretch")
                    show_a = by_asset[["asset_class", "평가액_원", "비중(%)"]].copy()
                    show_a.columns = ["자산군", "평가액(원)", "비중(%)"]
                    st.dataframe(
                        show_a.style.format(
                            {"평가액(원)": "{:,.0f}", "비중(%)": "{:,.1f}%"}
                        ),
                        width="stretch",
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
                    st.plotly_chart(fig_e, width="stretch")
                    show_e = by_exposure[
                        ["exposure_currency", "평가액_원", "비중(%)"]
                    ].copy()
                    show_e.columns = ["노출통화", "평가액(원)", "비중(%)"]
                    st.dataframe(
                        show_e.style.format(
                            {"평가액(원)": "{:,.0f}", "비중(%)": "{:,.1f}%"}
                        ),
                        width="stretch",
                    )
                else:
                    st.info("노출통화별 집계할 평가금액이 없습니다.")

            # 태그별 자산 비중 섹션 추가
            st.markdown(
                "<h3 style='font-size: 1.1rem; margin-top: 30px; margin-bottom: 10px;'>태그별 자산 비중</h3>",
                unsafe_allow_html=True,
            )
            st.caption(
                "조각 크기·비중은 그룹별 순평가액의 절대값 합으로 표시합니다. 표의 평가액(원)은 부호 있는 순액입니다."
            )

            # tags_str 컬럼을 사용하여 태그별 그룹화
            if "tags_str" in holdings_df.columns and not holdings_df["tags_str"].empty:
                # 각 태그별 평가액 합산 (하나의 종목이 여러 태그를 가질 수 있으므로 개별 태그로 분리하여 합산)
                tag_values = []
                for idx, row in holdings_df.iterrows():
                    if row["tags_str"]:
                        for tag in row["tags"]:
                            tag_values.append(
                                {"tag": tag, "currentValueKrw": row["currentValueKrw"]}
                            )

                if tag_values:
                    by_tag = (
                        pd.DataFrame(tag_values)
                        .groupby("tag", as_index=False)["currentValueKrw"]
                        .sum()
                    )
                    by_tag = by_tag.rename(columns={"currentValueKrw": "평가액_원"})
                    by_tag["_slice"] = by_tag["평가액_원"].abs()
                    by_tag = by_tag[by_tag["_slice"] > 1e-9]
                    denom_t = float(by_tag["_slice"].sum())
                    by_tag["비중(%)"] = (
                        by_tag["_slice"] / denom_t * 100 if denom_t > 0 else 0.0
                    )

                    if not by_tag.empty:
                        fig_t = px.pie(
                            by_tag,
                            values="_slice",
                            names="tag",
                            title="태그별 자산 비중 (원화)",
                            custom_data=["평가액_원"],
                        )
                        fig_t.update_traces(
                            texttemplate="<b>%{label}</b><br>₩%{customdata[0]:,.0f}<br>%{percent}",
                            textinfo="text",
                            textposition="inside",
                            insidetextorientation="horizontal",
                            hoverinfo="skip",
                        )
                        st.plotly_chart(fig_t, width="stretch")
                        show_t = by_tag[["tag", "평가액_원", "비중(%)"]].copy()
                        show_t.columns = ["태그", "평가액(원)", "비중(%)"]
                        st.dataframe(
                            show_t.style.format(
                                {"평가액(원)": "{:,.0f}", "비중(%)": "{:,.1f}%"}
                            ),
                            width="stretch",
                        )
                    else:
                        st.info("태그별 집계할 평가금액이 없습니다.")
                else:
                    st.info("태그별 집계할 평가금액이 없습니다.")
            else:
                st.info("표시할 태그 정보가 없습니다. 매매 내역에 태그를 추가해보세요!")

        else:
            st.info(
                "현재 보유 중인 주식이 없습니다. 사이드바에서 매수 내역을 추가해보세요!"
            )

        st.divider()
        st.markdown(
            "<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>"
            "달러 노출 vs USDKRW (원화)</h3>",
            unsafe_allow_html=True,
        )
        st.caption(
            f"**달러 노출 주식**: 노출통화가 USD이고 선물이 아닌 자산의 원화 환산 평가액 합. "
            f"**달러 노출 선물**: 노출통화가 USD이고 선물인 자산의 수량 × 현재가 × 환율(USD 선물 시) 합. "
            "숏은 음수. **총 노출금액** = 위 둘의 합."
        )
        _usd_exposure_stocks = df[
            (df["exposure_currency"] == "USD") & (df["asset_class"] != "선물")
        ]["currentValueKrw"].sum()

        _usd_exposure_futures = (
            df[(df["exposure_currency"] == "USD") & (df["asset_class"] == "선물")]
            .apply(
                lambda r: r["currentQuantity"]
                * r["currentPrice"]
                * (exchange_rate if r["currency"] == "USD" else 1.0),
                axis=1,
            )
            .sum()
        )

        _total_exposure_krw = _usd_exposure_stocks + _usd_exposure_futures

        if abs(_usd_exposure_stocks) > 1e-6 or abs(_usd_exposure_futures) > 1e-6:
            _m1, _m2, _m3 = st.columns(3)
            _m1.metric("달러 노출 주식(원)", f"{_usd_exposure_stocks:,.0f}")
            _m2.metric("달러 노출 선물(원)", f"{_usd_exposure_futures:,.0f}")
            _m3.metric("총 노출금액(원)", f"{_total_exposure_krw:,.0f}")
        else:
            st.caption("표시할 달러 노출 자산 또는 USDKRW 포지션이 없습니다.")

    with tab2:
        st.markdown(
            "<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>거래완료 내역</h3>",
            unsafe_allow_html=True,
        )
        st.caption(
            "현재 거래가 있지만 보유 잔고가 없는 종목 (완전 매도된 종목)의 최종 매매손익"
        )

        # 거래완료 종목: 실현 손익이 있지만 현재 수량이 0인 종목
        completed_df = df[
            (df["realizedPnlKrw"] != 0) & (abs(df["currentQuantity"]) < 1e-12)
        ].copy()

        if not completed_df.empty:
            # 원화 환산으로 고정
            display_completed = completed_df.copy()
            usd_mask_c = display_completed["currency"] == "USD"
            display_completed.loc[usd_mask_c, "averageCost"] = display_completed.loc[
                usd_mask_c, "averageCostKrw"
            ]
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
                "평균 매입가": "{:,.0f}",
                "최종 매매손익": "{:,.0f}",
            }

            # 음수값을 빨간색으로 표시
            def highlight_negative_completed(val):
                if isinstance(val, (int, float)):
                    if val < 0:
                        return "color: red"
                return ""

            styled_completed = completed_show.style.format(completed_format)
            styled_completed = styled_completed.map(
                highlight_negative_completed, subset=pd.IndexSlice[:, "최종 매매손익"]
            )

            st.dataframe(styled_completed, width="stretch")
        else:
            st.info("거래완료 내역이 없습니다.")

    with tab3:
        st.markdown(
            "<h3 style='font-size: 1.1rem; margin-top: 10px; margin-bottom: 10px;'>전체 매매 내역</h3>",
            unsafe_allow_html=True,
        )
        # 최신 데이터를 다시 불러옴
        current_history_df = load_trade_history()

        if not current_history_df.empty:
            # 거래일 기준 내림차순 정렬 (최근 거래가 위로)
            current_history_df["date"] = pd.to_datetime(current_history_df["date"])
            current_history_df = current_history_df.sort_values("date", ascending=False)

            # 종목명 컬럼 추가
            current_history_df["종목명"] = current_history_df["ticker"].apply(
                get_company_name
            )

            if "fx_krw_per_usd" not in current_history_df.columns:
                current_history_df["fx_krw_per_usd"] = pd.NA
                current_history_df.loc[
                    current_history_df["currency"] == "KRW", "fx_krw_per_usd"
                ] = 1.0
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
            current_history_df["수량"] = pd.to_numeric(
                current_history_df["수량"], errors="coerce"
            ).fillna(0)
            current_history_df["단가"] = pd.to_numeric(
                current_history_df["단가"], errors="coerce"
            ).fillna(0)
            fx_col = "환율(1USD=KRW)"
            current_history_df[fx_col] = pd.to_numeric(
                current_history_df[fx_col], errors="coerce"
            )

            # 매매 내역 포맷팅 (수량, 단가 소수점 버림)
            history_format_dict = {
                "수량": "{:,.0f}",
                "단가": "{:,.0f}",
                fx_col: "{:,.2f}",
                "매매일자": lambda x: pd.to_datetime(x).strftime("%Y-%m-%d %H:%M:%S") if pd.notna(x) else "",
            }

            st.divider()
            st.markdown(
                "<h3 style='font-size: 1.1rem; margin-bottom: 10px;'>매매 내역 수정 및 삭제</h3>",
                unsafe_allow_html=True,
            )
            st.write("아래 표에서 수정하거나 삭제할 내역의 행(row)을 클릭하세요.")

            # 인덱스를 포함하여 표시하고 행 선택 기능 활성화
            event = st.dataframe(
                current_history_df.style.format(history_format_dict),
                width="stretch",
                on_select="rerun",
                selection_mode="single-row",
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
                        edit_date = st.date_input(
                            "매매 일자",
                            pd.to_datetime(row_data["date"]),
                            key=f"edit_date_{edit_index}",
                        )
                        # 기존 시간 정보 추출
                        existing_datetime = pd.to_datetime(row_data["date"])
                        existing_hour = existing_datetime.hour
                        existing_minute = existing_datetime.minute
                        existing_second = existing_datetime.second
                        
                        # 시간 입력 (시, 분, 초)
                        col_eth, col_etm, col_ets = st.columns(3)
                        with col_eth:
                            edit_hour = st.number_input(
                                "시(h)",
                                min_value=0,
                                max_value=23,
                                value=existing_hour,
                                step=1,
                                key=f"edit_hour_{edit_index}",
                            )
                        with col_etm:
                            edit_minute = st.number_input(
                                "분(m)",
                                min_value=0,
                                max_value=59,
                                value=existing_minute,
                                step=1,
                                key=f"edit_minute_{edit_index}",
                            )
                        with col_ets:
                            edit_second = st.number_input(
                                "초(s)",
                                min_value=0,
                                max_value=59,
                                value=existing_second,
                                step=1,
                                key=f"edit_second_{edit_index}",
                            )
                        
                        edit_time = time(hour=int(edit_hour), minute=int(edit_minute), second=int(edit_second))
                        
                        edit_account = st.text_input(
                            "계좌명",
                            row_data["account"],
                            key=f"edit_account_{edit_index}",
                        )
                        edit_ticker = st.text_input(
                            "종목 코드",
                            row_data["ticker"],
                            key=f"edit_ticker_{edit_index}",
                        ).upper()
                        raw_exp = row_data.get("exposure_currency", "KRW")
                        if raw_exp is None or (
                            isinstance(raw_exp, float) and pd.isna(raw_exp)
                        ):
                            raw_exp = "KRW"
                        edit_exposure = st.selectbox(
                            "노출통화",
                            list(EXPOSURE_CURRENCY_OPTIONS),
                            index=list(EXPOSURE_CURRENCY_OPTIONS).index(
                                str(raw_exp).upper()
                                if str(raw_exp).upper() in EXPOSURE_CURRENCY_OPTIONS
                                else "KRW"
                            ),
                            key=f"edit_exp_{edit_index}",
                        )
                        raw_ac = row_data.get(
                            "asset_class", NEW_TRADE_DEFAULT_ASSET_CLASS
                        )
                        if raw_ac is None or (
                            isinstance(raw_ac, float) and pd.isna(raw_ac)
                        ):
                            raw_ac = NEW_TRADE_DEFAULT_ASSET_CLASS
                        raw_ac = str(raw_ac).strip()
                        ac_idx = (
                            list(ASSET_CLASS_OPTIONS).index(raw_ac)
                            if raw_ac in ASSET_CLASS_OPTIONS
                            else 0
                        )
                        edit_asset_class = st.selectbox(
                            "자산군",
                            list(ASSET_CLASS_OPTIONS),
                            index=ac_idx,
                            key=f"edit_ac_{edit_index}",
                        )
                    with col_e2:
                        edit_type = st.selectbox(
                            "매매 종류",
                            ["매수", "매도"],
                            index=0 if row_data["tradeType"] in ["Buy", "매수"] else 1,
                            key=f"edit_type_{edit_index}",
                        )
                        edit_quantity = st.number_input(
                            "수량",
                            min_value=0.01,
                            value=float(row_data["quantity"]),
                            step=1.0,
                            key=f"edit_qty_{edit_index}",
                        )
                    with col_e3:
                        edit_price = st.number_input(
                            "단가",
                            min_value=0.01,
                            value=float(row_data["price"]),
                            step=1.0,
                            key=f"edit_price_{edit_index}",
                        )
                        edit_currency = st.selectbox(
                            "통화",
                            ["KRW", "USD"],
                            index=0 if row_data["currency"] == "KRW" else 1,
                            key=f"edit_currency_{edit_index}",
                        )
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
                        if st.button(
                            "수정", type="primary", key=f"btn_update_{edit_index}"
                        ):
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
                                trade_time=edit_time,
                            ):
                                st.success("성공적으로 수정되었습니다.")
                                st.rerun()
                    with col_btn2:
                        if st.button(
                            "삭제", type="secondary", key=f"btn_delete_{edit_index}"
                        ):
                            if delete_trade(edit_index):
                                st.success("성공적으로 삭제되었습니다.")
                                st.rerun()
        else:
            st.info("기록된 매매 내역이 없습니다.")
else:
    st.info(
        "선택된 계좌에 포트폴리오 데이터가 없습니다. 좌측 사이드바에서 매매 내역을 추가해주세요."
    )
