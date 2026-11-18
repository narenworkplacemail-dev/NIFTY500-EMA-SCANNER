"""Simple NIFTY 500 daily EMA20/EMA50 trend scanner for Streamlit Cloud."""

from __future__ import annotations

from datetime import datetime

import pandas as pd
import streamlit as st
import yfinance as yf

NIFTY500_CSV = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

st.set_page_config(page_title="NIFTY 500 EMA Scanner", page_icon="📈", layout="wide")

st.markdown(
    """
    <style>
    .stApp { background: linear-gradient(135deg, #f6fbff 0%, #fff8f3 55%, #f5fbf7 100%); }
    [data-testid="stMetric"] { background: #ffffff; border: 1px solid #e7edf3;
      padding: 12px 16px; border-radius: 14px; }
    div.stButton > button { border-radius: 10px; }
    </style>
    """, unsafe_allow_html=True,
)


def get_universe() -> pd.DataFrame:
    """Fetch current NIFTY 500 symbols and company names from the NSE constituent CSV."""
    universe = pd.read_csv(NIFTY500_CSV)
    by_lower = {str(column).strip().lower(): column for column in universe.columns}
    symbol_col = by_lower.get("symbol")
    name_col = by_lower.get("company name") or by_lower.get("company")
    if not symbol_col:
        raise ValueError(f"NSE file has no Symbol column. Columns received: {list(universe.columns)}")
    if not name_col:
        name_col = symbol_col
    result = universe[[symbol_col, name_col]].copy()
    result.columns = ["Symbol", "Stock Name"]
    result["Symbol"] = result["Symbol"].astype(str).str.strip().str.upper()
    result["Stock Name"] = result["Stock Name"].astype(str).str.strip()
    result = result[result["Symbol"].ne("")].drop_duplicates("Symbol")
    result["Ticker"] = result["Symbol"] + ".NS"
    if result.empty:
        raise ValueError("The NIFTY 500 constituent list is empty.")
    return result.reset_index(drop=True)


def unpack_batch(data: pd.DataFrame, tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Handle either ticker-first or price-first yfinance multi-index columns."""
    frames: dict[str, pd.DataFrame] = {}
    if data.empty:
        return frames
    if isinstance(data.columns, pd.MultiIndex):
        first = set(data.columns.get_level_values(0))
        second = set(data.columns.get_level_values(1))
        for ticker in tickers:
            if ticker in first:
                frames[ticker] = data[ticker].dropna(how="all")
            elif ticker in second:
                frames[ticker] = data.xs(ticker, axis=1, level=1).dropna(how="all")
    elif len(tickers) == 1:
        frames[tickers[0]] = data.dropna(how="all")
    return frames


@st.cache_data(ttl=900, show_spinner=False)
def scan_nifty500(batch_size: int = 75) -> tuple[pd.DataFrame, int, int, str]:
    """Fetch daily bars in batches, cache for 15 minutes, and return trend matches."""
    universe = get_universe()
    matches: list[dict] = []
    data_count = 0
    failed_count = 0
    tickers = universe["Ticker"].tolist()
    stock_names = universe.set_index("Ticker")["Stock Name"].to_dict()
    symbols = universe.set_index("Ticker")["Symbol"].to_dict()
    for start in range(0, len(tickers), batch_size):
        batch = tickers[start:start + batch_size]
        try:
            downloaded = yf.download(
                batch,
                period="1y",
                interval="1d",
                auto_adjust=True,
                group_by="ticker",
                progress=False,
                threads=True,
                timeout=25,
                multi_level_index=True,
            )
            frames = unpack_batch(downloaded, batch)
        except Exception:
            frames = {}

        for ticker in batch:
            frame = frames.get(ticker)
            if frame is None or frame.empty or "Close" not in frame.columns:
                failed_count += 1
                continue
            close = frame["Close"].dropna().astype(float)
            if len(close) < 60:
                failed_count += 1
                continue

            ema20 = close.ewm(span=20, adjust=False, min_periods=20).mean()
            ema50 = close.ewm(span=50, adjust=False, min_periods=50).mean()
            valid = pd.concat([close.rename("Close"), ema20.rename("EMA20"),
                               ema50.rename("EMA50")], axis=1).dropna()
            if valid.empty:
                failed_count += 1
                continue
            data_count += 1
            latest = valid.iloc[-1]

            # Keep only stocks that currently satisfy Close > EMA20 > EMA50.
            if not (latest["Close"] > latest["EMA20"] > latest["EMA50"]):
                continue

            crossed_up = (valid["EMA20"].shift(1) <= valid["EMA50"].shift(1)) & (
                valid["EMA20"] > valid["EMA50"]
            )
            dates = valid.index[crossed_up.fillna(False)]
            if len(dates):
                crossover_date = pd.Timestamp(dates[-1])
                if crossover_date.tzinfo is not None:
                    crossover_date = crossover_date.tz_convert(None)
                crossover_text = crossover_date.strftime("%Y-%m-%d")
            else:
                crossover_text = "No bullish cross in 1Y"

            data_date = pd.Timestamp(valid.index[-1])
            if data_date.tzinfo is not None:
                data_date = data_date.tz_convert(None)
            matches.append({
                "Stock Name": stock_names[ticker],
                "Symbol": symbols[ticker],
                "Data Date": data_date.strftime("%Y-%m-%d"),
                "Close": round(float(latest["Close"]), 2),
                "Daily EMA 20": round(float(latest["EMA20"]), 2),
                "Daily EMA 50": round(float(latest["EMA50"]), 2),
                "EMA 20 crossed above EMA 50": crossover_text,
            })

    result = pd.DataFrame(matches)
    if not result.empty:
        result["_CrossoverSort"] = pd.to_datetime(
            result["EMA 20 crossed above EMA 50"], errors="coerce", format="%Y-%m-%d"
        )
        result.sort_values(
            ["_CrossoverSort", "Symbol"],
            ascending=[False, True],
            na_position="last",
            inplace=True,
        )
        result.drop(columns=["_CrossoverSort"], inplace=True)
        result.reset_index(drop=True, inplace=True)
    return result, data_count, failed_count, datetime.now().strftime("%Y-%m-%d %H:%M:%S")


st.title("📈 NIFTY 500 EMA 20/50 Scanner")
st.write("Scans current NIFTY 500 constituents using **daily candles**.")
st.info("Match rule: latest daily close > EMA 20 > EMA 50. The table shows the most recent bullish EMA crossover date from the past year.")

scan_col, refresh_col = st.columns([3, 1])
with scan_col:
    run_scan = st.button("🔎 Scan NIFTY 500", type="primary", use_container_width=True)
with refresh_col:
    if st.button("🔄 Refresh data", use_container_width=True):
        scan_nifty500.clear()
        st.rerun()

if run_scan:
    try:
        with st.spinner("Getting the NIFTY 500 list and daily prices… this may take a minute."):
            table, stocks_with_data, data_issues, scanned_at = scan_nifty500()
        st.session_state["ema_table"] = table
        st.session_state["ema_stocks_with_data"] = stocks_with_data
        st.session_state["ema_data_issues"] = data_issues
        st.session_state["ema_scanned_at"] = scanned_at
    except Exception as exc:
        st.error(f"Could not complete the scan: {exc}")
        st.caption("The app needs internet access to read the NSE constituent CSV and Yahoo Finance daily prices.")

if "ema_table" in st.session_state:
    table = st.session_state["ema_table"]
    metric_cols = st.columns(4)
    metric_cols[0].metric("Current NIFTY 500 stocks", "~500")
    metric_cols[1].metric("Stocks with usable data", st.session_state["ema_stocks_with_data"])
    metric_cols[2].metric("Matching EMA setups", len(table))
    metric_cols[3].metric("Data issues", st.session_state["ema_data_issues"])
    st.caption(f"Last scan: {st.session_state['ema_scanned_at']} · History: 1 year · Interval: 1 day · Prices from Yahoo Finance")

    if table.empty:
        st.warning("No stocks currently meet Close > EMA 20 > EMA 50.")
    else:
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.download_button(
            "⬇️ Download CSV",
            data=table.to_csv(index=False).encode("utf-8-sig"),
            file_name="nifty500_ema20_ema50_scan.csv",
            mime="text/csv",
        )

st.caption("Data is cached for 15 minutes. Use **Refresh data** to clear the cache and fetch again. This is a screening tool, not a trading recommendation.")
