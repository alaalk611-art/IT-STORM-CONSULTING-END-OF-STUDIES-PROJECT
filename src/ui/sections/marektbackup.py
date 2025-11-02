from __future__ import annotations
import os
import numpy as np
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st


# ===============================
# Helpers quant
# ===============================
def _annualization_factor(interval: str) -> int:
    return {"1d": 252, "1wk": 52, "1mo": 12}.get(interval, 252)


def _compute_indicators(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    Normalise les colonnes et ajoute :
    - SMA20 / SMA50, EMA20
    - RSI(14)
    - MACD(12,26,9)
    - Volatilité annualisée (20 périodes)
    - Plus haut / bas 55 périodes
    """
    if df.empty:
        return df

    # Normalisation colonnes
    rename_map = {
        "t": "time", "timestamp": "time", "datetime": "time",
        "o": "open", "h": "high", "l": "low", "c": "close", "v": "volume",
    }
    df = df.rename(columns={k: v for k, v in rename_map.items() if k in df.columns}).copy()

    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"], errors="coerce")
        df = df.sort_values("time")

    # Retours
    df["ret"] = df["close"].pct_change()

    # Moyennes mobiles
    df["sma20"] = df["close"].rolling(20).mean()
    df["sma50"] = df["close"].rolling(50).mean()
    df["ema20"] = df["close"].ewm(span=20, adjust=False).mean()

    # RSI(14)
    delta = df["close"].diff()
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    roll_up = pd.Series(gain, index=df.index).rolling(14).mean()
    roll_down = pd.Series(loss, index=df.index).rolling(14).mean()
    rs = roll_up / (roll_down.replace(0, np.nan))
    df["rsi14"] = 100 - (100 / (1 + rs))
    df["rsi14"] = df["rsi14"].fillna(method="bfill")

    # MACD
    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    # Volatilité annualisée (20 périodes)
    ann = _annualization_factor(interval)
    df["vol20"] = df["ret"].rolling(20).std() * np.sqrt(ann)

    # Breakouts
    df["hh_55"] = df["close"].rolling(55).max()
    df["ll_55"] = df["close"].rolling(55).min()

    return df


def _score_and_reco(df: pd.DataFrame) -> dict:
    """
    Score simple + recommandation textuelle (ACHAT / NEUTRE / VENTE)
    basé sur tendance, momentum, MACD, breakouts et volatilité.
    """
    if df.empty or df["close"].isna().all():
        return {"label": "NEUTRE", "score": 0, "bullets": ["Données insuffisantes."]}

    last = df.iloc[-1]
    bullets: list[str] = []
    score = 0.0

    # 1) Tendance
    sma20 = float(last.get("sma20", np.nan))
    sma50 = float(last.get("sma50", np.nan))
    close = float(last.get("close", np.nan))

    if not np.isnan(sma20) and not np.isnan(sma50) and not np.isnan(close):
        if sma20 > sma50 and close > sma20:
            score += 2
            bullets.append("Tendance haussière (SMA20 > SMA50) et prix > SMA20.")
        elif sma20 < sma50 and close < sma20:
            score -= 2
            bullets.append("Tendance baissière (SMA20 < SMA50) et prix < SMA20.")
        else:
            bullets.append("Tendance mitigée (SMA20~SMA50 ou prix autour de SMA20).")
    else:
        bullets.append("Tendance non déterminée (MAs indisponibles).")

    # 2) Momentum (RSI)
    rsi = float(last.get("rsi14", np.nan))
    if not np.isnan(rsi):
        if 55 <= rsi <= 70:
            score += 1
            bullets.append(f"Momentum positif (RSI ≈ {rsi:.1f}).")
        elif rsi > 70:
            score -= 1
            bullets.append(f"RSI élevé (≈ {rsi:.1f}) → surachat possible.")
        elif rsi < 45:
            score -= 1
            bullets.append(f"RSI faible (≈ {rsi:.1f}) → momentum dégradé.")
        else:
            bullets.append(f"RSI neutre (≈ {rsi:.1f}).")

    # 3) MACD
    macd = float(last.get("macd", np.nan))
    signal = float(last.get("macd_signal", np.nan))
    if not np.isnan(macd) and not np.isnan(signal):
        if macd > signal:
            score += 1
            bullets.append("MACD > signal → biais haussier court terme.")
        else:
            score -= 1
            bullets.append("MACD < signal → biais baissier court terme.")

    # 4) Breakouts / Supports
    hh55 = float(last.get("hh_55", np.nan)) if not np.isnan(last.get("hh_55", np.nan)) else None
    ll55 = float(last.get("ll_55", np.nan)) if not np.isnan(last.get("ll_55", np.nan)) else None
    if hh55 and not np.isnan(close):
        if close >= hh55 * 0.999:
            score += 2
            bullets.append("Cassure/retour sur plus haut 55 périodes → signal fort.")
    if ll55 and not np.isnan(close):
        if close <= ll55 * 1.001:
            score -= 2
            bullets.append("Retour vers plus bas 55 périodes → prudence.")

    # 5) Volatilité
    vol = float(last.get("vol20", np.nan))
    if not np.isnan(vol):
        if vol > 0.35:
            score -= 1
            bullets.append(f"Volatilité annualisée élevée (≈ {vol:.0%}).")
        elif vol < 0.15:
            score += 0.5
            bullets.append(f"Volatilité modérée (≈ {vol:.0%}).")
        else:
            bullets.append(f"Volatilité moyenne (≈ {vol:.0%}).")

    # Label
    if score >= 3:
        label = "ACHAT"
    elif score <= -2:
        label = "VENTE"
    else:
        label = "NEUTRE"

    return {"label": label, "score": round(score, 2), "bullets": bullets}


# ===============================
# Backtest helpers
# ===============================
def _max_drawdown(equity: pd.Series) -> float:
    roll_max = equity.cummax()
    dd = equity / roll_max - 1.0
    return float(dd.min())


def _bt_stats(strat_ret: pd.Series, interval: str) -> dict:
    ann = {"1d": 252, "1wk": 52, "1mo": 12}.get(interval, 252)
    strat_ret = strat_ret.fillna(0.0)
    equity = (1.0 + strat_ret).cumprod()
    tot_ret = float(equity.iloc[-1] - 1.0)
    n = len(strat_ret)
    cagr = float((equity.iloc[-1]) ** (ann / max(n, 1)) - 1.0) if n > 0 else 0.0
    vol = float(strat_ret.std() * np.sqrt(ann)) if n > 1 else 0.0
    sharpe = float((strat_ret.mean() * ann) / vol) if vol > 1e-12 else 0.0
    mdd = _max_drawdown(equity)
    return {"equity": equity, "total_return": tot_ret, "cagr": cagr, "vol": vol, "sharpe": sharpe, "maxdd": mdd}


def _backtest_sma(df: pd.DataFrame, fast: int = 20, slow: int = 50, fee_bps: float = 5.0) -> pd.DataFrame:
    """
    Règle simple : long (1) quand SMA_fast > SMA_slow, sinon cash (0).
    Frais : fee_bps (ex: 5 bps = 0.05%) appliqués à chaque changement de position.
    """
    data = df.copy()
    data["sma_fast"] = data["close"].rolling(fast).mean()
    data["sma_slow"] = data["close"].rolling(slow).mean()
    data["pos"] = (data["sma_fast"] > data["sma_slow"]).astype(float)
    data["ret"] = data["close"].pct_change().fillna(0.0)

    change = data["pos"].diff().abs().fillna(0.0)
    fee = change * (fee_bps / 10000.0)
    data["strat_ret"] = data["pos"].shift(1).fillna(0.0) * data["ret"] - fee
    data["bh_ret"] = data["ret"]
    return data


# ===============================
# Glossaire UI
# ===============================
def _glossary_ui():
    with st.expander("📚 Glossaire des termes (clique pour ouvrir)"):
        terms = {
            "SMA (Simple Moving Average)": "Moyenne arithmétique des n dernières clôtures. SMA20 = 20 derniers jours.",
            "EMA (Exponential Moving Average)": "Moyenne mobile qui pèse davantage les données récentes.",
            "RSI (Relative Strength Index)": "Oscillateur de momentum de 0 à 100. >70: surachat, <30: survente.",
            "MACD": "Différence EMA(12) - EMA(26). Croisement avec sa ligne signal (EMA(9)) donne des signaux.",
            "Volatilité annualisée": "Écart-type des rendements annualisé (ex. sur 20 périodes). Mesure le risque.",
            "Breakout 55 périodes": "Cassure du plus haut (ou retour au plus bas) des 55 dernières barres.",
            "Écart vs SMA20": "Pourcentage d’écart entre le prix et la SMA20 (prix/SMA20 - 1).",
            "Sharpe ratio": "Rendement excédentaire / volatilité. Plus c’est haut, mieux c’est (à risque égal).",
            "CAGR": "Taux de croissance annuel composé du portefeuille (annualisé).",
            "Max drawdown (MaxDD)": "Perte maximale entre un sommet et le plus bas suivant de l’equity curve.",
            "Buy & Hold": "Stratégie passive : acheter puis conserver l’actif sur toute la période.",
            "bps (basis points)": "Points de base. 1 bp = 0,01%. 5 bps = 0,05% de frais par trade.",
        }
        for title, desc in terms.items():
            st.markdown(f"**{title}** — {desc}")


# ===============================
# UI principale
# ===============================
def render() -> None:
    """Affiche le tableau de bord 'Market Watch' dans Streamlit avec indicateurs, reco & backtest."""
    API_BASE = os.getenv("MARKET_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

    def api_get(path: str, **params):
        try:
            r = requests.get(API_BASE + path, params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            st.error(f"API error: {e}")
            return None

    st.header("📈 Market Watch — CAC40 (Quant)")

    # ---- Choix de symboles ----
    symbols = st.multiselect(
        "Choisissez des symboles (Yahoo Finance, suffixe .PA)",
        ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"],
        ["^FCHI", "BNP.PA", "MC.PA"],
    )

    # ---- Indicateurs rapides ----
    cols = st.columns(min(len(symbols), 4) or 1)
    for i, sym in enumerate(symbols):
        data = api_get(f"/v1/quote/{sym}")
        with cols[i % len(cols)]:
            if data:
                price = data.get("price", 0)
                currency = data.get("currency") or ""
                chg = data.get("change_percent")
                delta_txt = f"{float(chg):+.2f}%" if isinstance(chg, (int, float)) else "+0.00%"
                st.metric(label=sym, value=f"{price:,.2f} {currency}", delta=delta_txt)
            else:
                st.error(f"Erreur pour {sym}")

    st.divider()

    # ---- Historique + indicateurs + reco ----
    st.subheader("Historique, indicateurs & recommandations")
    chosen = st.selectbox("Symbole :", options=symbols or ["^FCHI"])
    interval = st.selectbox("Intervalle :", options=["1d", "1wk", "1mo"], index=0)
    period = st.selectbox("Période :", options=["1mo", "3mo", "6mo", "1y"], index=2)

    show_ma = st.checkbox("Afficher SMA20 / SMA50 / EMA20", value=True, help="Moyennes mobiles pour la tendance.")
    show_rsi = st.checkbox("Afficher RSI(14)", value=True, help="Momentum. >70: surachat, <30: survente.")
    show_macd = st.checkbox("Afficher MACD(12,26,9)", value=True, help="Signal court terme via croisement MACD/signal.")
    show_table = st.checkbox("Afficher le tableau brut (dernières lignes)", value=True)

    hist = api_get(f"/v1/ohlcv/{chosen}", interval=interval, period=period)
    if not hist:
        st.info("Pas de données disponibles pour ce symbole / intervalle.")
        _glossary_ui()
        return
    
    candles = hist.get("candles") or hist.get("data")
    if not candles:
        st.warning("Aucune donnée renvoyée par l'API.")
        _glossary_ui()
        return

    df = pd.DataFrame(candles)
    df = _compute_indicators(df, interval=interval)

    # ---- Recommandation
    reco = _score_and_reco(df)
    c1, c2, c3 = st.columns([1, 2, 3])
    with c1:
        st.markdown("**Signal**")
        st.markdown(f"### {reco['label']}")
        st.caption(f"Score: {reco['score']:+.2f}")
    with c2:
        st.markdown("**Raisons principales**")
        for b in reco["bullets"]:
            st.write(f"- {b}")
    with c3:
        # KPIs
        last = df.iloc[-1]
        st.markdown("**KPIs**")
        if "close" in last:
            st.metric("Prix", f"{last['close']:,.2f}")
        if "sma20" in last and not np.isnan(last["sma20"]) and "close" in last:
            st.metric("Écart vs SMA20", f"{(last['close']/last['sma20']-1):+.2%}")
        if "vol20" in last and not np.isnan(last["vol20"]):
            st.metric("Vol(20, ann.)", f"{last['vol20']:.0%}")
        if "rsi14" in last and not np.isnan(last["rsi14"]):
            st.metric("RSI(14)", f"{last['rsi14']:.1f}")

    # ---- Chandelier (+ MAs)
    fig_c = go.Figure(data=[go.Candlestick(
        x=df.get("time"),
        open=df.get("open"), high=df.get("high"), low=df.get("low"), close=df.get("close"),
        name="OHLC",
    )])
    if show_ma:
        if "sma20" in df: fig_c.add_trace(go.Scatter(x=df["time"], y=df["sma20"], name="SMA20", mode="lines"))
        if "sma50" in df: fig_c.add_trace(go.Scatter(x=df["time"], y=df["sma50"], name="SMA50", mode="lines"))
        if "ema20" in df: fig_c.add_trace(go.Scatter(x=df["time"], y=df["ema20"], name="EMA20", mode="lines"))
    fig_c.update_layout(
        title=f"{chosen} — {interval} / {period}",
        xaxis_title="Temps", yaxis_title="Prix",
        margin=dict(l=10, r=10, t=40, b=10), height=480,
    )
    st.plotly_chart(fig_c, use_container_width=True)

    # ---- RSI
    if show_rsi and "rsi14" in df:
        fig_rsi = go.Figure(data=[go.Scatter(x=df["time"], y=df["rsi14"], name="RSI(14)", mode="lines")])
        fig_rsi.add_hline(y=70, line_dash="dot")
        fig_rsi.add_hline(y=30, line_dash="dot")
        fig_rsi.update_layout(
            xaxis_title="Temps", yaxis_title="RSI(14)",
            margin=dict(l=10, r=10, t=40, b=10), height=220,
        )
        st.plotly_chart(fig_rsi, use_container_width=True)

    # ---- MACD
    if show_macd and {"macd", "macd_signal", "macd_hist"}.issubset(df.columns):
        fig_macd = go.Figure()
        fig_macd.add_trace(go.Bar(x=df["time"], y=df["macd_hist"], name="MACD hist"))
        fig_macd.add_trace(go.Scatter(x=df["time"], y=df["macd"], name="MACD", mode="lines"))
        fig_macd.add_trace(go.Scatter(x=df["time"], y=df["macd_signal"], name="Signal", mode="lines"))
        fig_macd.update_layout(
            xaxis_title="Temps", yaxis_title="MACD",
            margin=dict(l=10, r=10, t=40, b=10), height=260,
        )
        st.plotly_chart(fig_macd, use_container_width=True)

    # ---- Backtest SMA ----
    st.subheader("Backtest — SMA crossover")
    c_bt1, c_bt2, c_bt3 = st.columns([1, 1, 1])
    with c_bt1:
        fast = st.number_input("SMA rapide", min_value=5, max_value=100, value=20, step=1, help="Fenêtre de la SMA rapide.")
    with c_bt2:
        slow = st.number_input("SMA lente", min_value=10, max_value=250, value=50, step=1, help="Fenêtre de la SMA lente.")
    with c_bt3:
        fee_bps = st.number_input("Frais (bps par trade)", min_value=0.0, max_value=50.0, value=5.0, step=0.5,
                                  help="1 bp = 0,01%. Exemple : 5 bps = 0,05%.")

    if fast >= slow:
        st.warning("⚠️ La SMA rapide doit être < à la SMA lente.")
    else:
        base = df[["time", "close"]].dropna().reset_index(drop=True)
        bt = _backtest_sma(base, fast=fast, slow=slow, fee_bps=fee_bps)
        stats_strat = _bt_stats(bt["strat_ret"], interval)
        stats_bh    = _bt_stats(bt["bh_ret"], interval)

        # Equity curve
        fig_eq = go.Figure()
        fig_eq.add_trace(go.Scatter(x=base["time"].iloc[-len(stats_strat["equity"]):],
                                    y=stats_strat["equity"], name="Stratégie (SMA)", mode="lines"))
        fig_eq.add_trace(go.Scatter(x=base["time"].iloc[-len(stats_bh["equity"]):],
                                    y=stats_bh["equity"], name="Buy & Hold", mode="lines"))
        fig_eq.update_layout(
            title=f"Évolution de 1€ — SMA({fast},{slow}) vs Buy&Hold — frais {fee_bps:.1f} bps/trade",
            xaxis_title="Temps", yaxis_title="Valeur du portefeuille (base 1.00)",
            margin=dict(l=10, r=10, t=40, b=10), height=320
        )
        st.plotly_chart(fig_eq, use_container_width=True)

        # Stats
        cs1, cs2, cs3, cs4, cs5, cs6, cs7 = st.columns(7)
        cs1.metric("Strat — Total", f"{stats_strat['total_return']*100:,.2f}%")
        cs2.metric("Strat — CAGR",  f"{stats_strat['cagr']*100:,.2f}%")
        cs3.metric("Strat — Vol",   f"{stats_strat['vol']*100:,.2f}%")
        cs4.metric("Strat — Sharpe", f"{stats_strat['sharpe']:.2f}")
        cs5.metric("Strat — MaxDD", f"{stats_strat['maxdd']*100:,.2f}%")

        # Approx trades & win-rate
        approx_trades = int(bt["pos"].diff().abs().sum())
        # Win rate par segment (entrée->sortie)
        seg_returns = []
        in_trade = False
        start_idx = None
        for i in range(len(bt)):
            if not in_trade and bt.loc[i, "pos"] == 1:
                in_trade = True
                start_idx = i
            elif in_trade and (bt.loc[i, "pos"] == 0 or i == len(bt) - 1):
                end_idx = i if bt.loc[i, "pos"] == 0 else i
                segment = bt.loc[start_idx:end_idx, "strat_ret"]
                seg_equity = (1.0 + segment.fillna(0.0)).prod() - 1.0
                seg_returns.append(seg_equity)
                in_trade = False
                start_idx = None
        if seg_returns:
            wins = sum(1 for r in seg_returns if r > 0)
            win_rate = wins / len(seg_returns)
        else:
            win_rate = 0.0

        cs6.metric("Trades (approx.)", f"{approx_trades}")
        cs7.metric("Win-rate (approx.)", f"{win_rate*100:,.1f}%")

    # ---- Tableau brut
    if show_table:
        cols_show = ["time", "open", "high", "low", "close", "volume",
                     "sma20", "sma50", "ema20", "rsi14", "macd", "macd_signal", "vol20"]
        cols_show = [c for c in cols_show if c in df.columns]
        st.dataframe(df[cols_show].tail(15), use_container_width=True)

    # ---- Glossaire
    _glossary_ui()
