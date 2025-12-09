import streamlit as st
import requests

N8N_MARKET_URL = "http://localhost:5678/webhook/market-radar"

def call_market_radar(universe=None, horizon_days=5, risk_mode="standard"):
    payload = {
        "universe": universe or ["^FCHI", "BNP.PA", "AIR.PA", "OR.PA", "MC.PA", "SAN.PA"],
        "horizon_days": horizon_days,
        "risk_mode": risk_mode,
        "user": "ala",
    }
    resp = requests.post(N8N_MARKET_URL, json=payload, timeout=20)
    resp.raise_for_status()
    return resp.json()

st.title("🛰️ Market Radar via n8n")

universe_text = st.text_input(
    "Universe (tickers séparés par des virgules)",
    "^FCHI, BNP.PA, AIR.PA, OR.PA, MC.PA, SAN.PA",
)

horizon_days = st.slider("Horizon (jours)", 1, 20, 5)
risk_mode = st.selectbox("Mode de risque", ["standard", "agressif", "prudent"])

if st.button("Lancer Market Radar n8n"):
    tickers = [t.strip() for t in universe_text.split(",") if t.strip()]
    try:
        res = call_market_radar(tickers, horizon_days=horizon_days, risk_mode=risk_mode)

        st.subheader("Résumé du marché")
        st.write(res.get("summary", "Résumé indisponible."))

        st.subheader("Risque global")
        st.info(res.get("global_risk", "N/A"))

        counts = res.get("counts", {})
        st.subheader("Synthèse des signaux")
        col1, col2, col3 = st.columns(3)
        col1.metric("Signaux ACHAT", counts.get("buy", 0))
        col2.metric("Signaux NEUTRE", counts.get("neutral", 0))
        col3.metric("Signaux VENTE", counts.get("sell", 0))

        with st.expander("Détail brut renvoyé par n8n"):
            st.json(res)

    except Exception as e:
        st.error(f"Erreur lors de l'appel à n8n : {e}")
