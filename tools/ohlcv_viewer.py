# tools/ohlcv_viewer.py
from __future__ import annotations
import requests
import pandas as pd
from urllib.parse import quote
import streamlit as st
import plotly.graph_objects as go

st.set_page_config(page_title="OHLCV Viewer", layout="wide")

# ---- Paramètres ----
col1, col2, col3, col4 = st.columns(4)
with col1:
    base_url = st.text_input("API base URL", "http://127.0.0.1:8001", help="Ton FastAPI local")
with col2:
    symbol = st.text_input("Symbol", "^FCHI")
with col3:
    interval = st.selectbox("Interval", ["1d", "1wk", "1mo"], index=1)
with col4:
    period = st.selectbox("Period", ["1mo", "3mo", "6mo", "1y", "2y"], index=2)

# Encodage du symbole (ex: ^FCHI -> %5EFCHI)
sym_enc = quote(symbol, safe="")

url = f"{base_url}/v1/ohlcv/{sym_enc}?interval={interval}&period={period}"

st.write(f"**GET** {url}")

# ---- Récupération ----
try:
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    data = r.json()
except Exception as e:
    st.error(f"Erreur d'appel API: {e}")
    st.stop()

candles = data.get("candles", [])
if not candles:
    st.warning("Pas de data renvoyée.")
    st.stop()

# ---- DataFrame ----
df = pd.DataFrame(candles)
# renommer colonnes si besoin
df = df.rename(columns={
    "t": "time", "o": "open", "h": "high", "l": "low",
    "c": "close", "v": "volume"
})
df["time"] = pd.to_datetime(df["time"])
df = df.sort_values("time")

st.subheader(f"{data.get('symbol', symbol)} — {interval} / {period}")
st.dataframe(df, use_container_width=True)

# ---- Graph chandelier + volume ----
candlestick = go.Figure(data=[go.Candlestick(
    x=df["time"],
    open=df["open"], high=df["high"], low=df["low"], close=df["close"],
    name="OHLC"
)])
candlestick.update_layout(
    xaxis_title="Time", yaxis_title="Price",
    margin=dict(l=10, r=10, t=40, b=10), height=500
)

volume = go.Figure(data=[go.Bar(
    x=df["time"], y=df["volume"], name="Volume"
)])
volume.update_layout(
    xaxis_title="Time", yaxis_title="Volume",
    margin=dict(l=10, r=10, t=40, b=10), height=250
)

st.plotly_chart(candlestick, use_container_width=True)
st.plotly_chart(volume, use_container_width=True)
