import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date
import os
from utils.portfolio import load_trade_history, add_trade, calculate_portfolio

# Set page config
st.set_page_config(page_title="Stock Portfolio Tracker", layout="wide")

# Sidebar for adding trades
st.sidebar.header("Add New Trade")
with st.sidebar.form("trade_form"):
    trade_date = st.date_input("Date", date.today())
    ticker = st.text_input("Ticker (e.g., AAPL, TSLA)", "").upper()
    trade_type = st.selectbox("Trade Type", ["Buy", "Sell"])
    quantity = st.number_input("Quantity", min_value=0.01, step=1.0)
    price = st.number_input("Price", min_value=0.01, step=1.0)
    submit_button = st.form_submit_button("Add Trade")

    if submit_button:
        if ticker:
            # Ensure data directory exists
            if not os.path.exists("data"):
                os.makedirs("data")
            
            # Add to CSV
            add_trade(trade_date, ticker, trade_type, quantity, price)
            st.sidebar.success(f"Added {trade_type} {quantity} of {ticker} at ${price}")
        else:
            st.sidebar.error("Please enter a ticker.")

# Main content
st.title("Stock Portfolio Tracker")

# Calculate portfolio metrics
df, total_value, total_unrealized_pnl, total_realized_pnl = calculate_portfolio()

# Display top metrics
col1, col2, col3 = st.columns(3)
col1.metric("Total Portfolio Value", f"${total_value:,.2f}")
col2.metric("Total Unrealized PnL", f"${total_unrealized_pnl:,.2f}", f"{(total_unrealized_pnl / (total_value - total_unrealized_pnl) * 100) if (total_value - total_unrealized_pnl) > 0 else 0:,.2f}%")
col3.metric("Total Realized PnL", f"${total_realized_pnl:,.2f}")

st.divider()

# Tabs for different views
tab1, tab2 = st.tabs(["Portfolio Overview", "Trade History"])

with tab1:
    st.subheader("Current Holdings")
    
    if not df.empty:
        # Format dataframe for display
        display_df = df.copy()
        display_df = display_df[['ticker', 'currentQuantity', 'averageCost', 'currentPrice', 'currentValue', 'unrealizedPnl', 'returnRate', 'weight']]
        
        # Rename columns for better readability
        display_df.columns = ['Ticker', 'Quantity', 'Avg Cost ($)', 'Current Price ($)', 'Total Value ($)', 'Unrealized PnL ($)', 'Return (%)', 'Weight (%)']
        
        # Format numeric columns
        format_dict = {
            'Quantity': '{:.2f}',
            'Avg Cost ($)': '${:.2f}',
            'Current Price ($)': '${:.2f}',
            'Total Value ($)': '${:.2f}',
            'Unrealized PnL ($)': '${:.2f}',
            'Return (%)': '{:.2f}%',
            'Weight (%)': '{:.2f}%'
        }
        
        st.dataframe(display_df.style.format(format_dict), use_container_width=True)
        
        # Plotly Pie Chart for Portfolio Weight
        st.subheader("Portfolio Allocation")
        fig = px.pie(df, values='currentValue', names='ticker', title='Portfolio Weight by Ticker')
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No active holdings found. Add some trades in the sidebar!")

with tab2:
    st.subheader("Trade History")
    history_df = load_trade_history()
    if not history_df.empty:
        st.dataframe(history_df, use_container_width=True)
    else:
        st.info("No trade history available.")
