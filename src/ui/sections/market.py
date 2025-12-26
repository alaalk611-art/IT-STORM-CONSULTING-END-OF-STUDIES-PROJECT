from __future__ import annotations
import os
from pathlib import Path
import numpy as np
import requests
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from datetime import date
from collections import deque
import random
import json 
# Import DL optionnel (autoencoder + DQN)
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
except ImportError:
    torch = None
    nn = None
    optim = None

# ===============================
# Helpers quant existants + nouveaux
# ===============================
def _annualization_factor(interval: str) -> int:
    return {"1d": 252, "1wk": 52, "1mo": 12}.get(interval, 252)


def _compute_indicators(df: pd.DataFrame, interval: str) -> pd.DataFrame:
    """
    Normalise les colonnes et ajoute :
    - ret, SMA20/50, EMA20
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
    df["rsi14"] = df["rsi14"].bfill()

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
    Score simple + recommandation (ACHAT / NEUTRE / VENTE)
    basé sur tendance, momentum, MACD, breakouts, volatilité.
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
    return {
        "equity": equity,
        "total_return": tot_ret,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "maxdd": mdd,
    }


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
# Nouveaux mini-ML helpers
# ===============================
def _rolling_zscore_anomalies(df: pd.DataFrame, window: int = 20, z_thresh: float = 2.0) -> pd.Series:
    """Retourne un booléen par ligne: |zscore(ret)| > z_thresh."""
    r = df["ret"]
    mu = r.rolling(window).mean()
    sd = r.rolling(window).std()
    z = (r - mu) / (sd.replace(0, np.nan))
    return (z.abs() > z_thresh).fillna(False)


def _trend_slope_and_projection(df: pd.DataFrame, lookback: int = 60, horizon: int = 10):
    """
    Calcule la tendance via régression linéaire (numpy.polyfit) sur les
    'lookback' derniers points de clôture et renvoie :

        (x_hist_time, y_reg_line, x_proj_time, y_proj_line, slope_annualized_pct)
    """
    if "time" not in df.columns or "close" not in df.columns:
        return None
    if len(df) < max(5, lookback):
        return None

    time_series = pd.to_datetime(df["time"], utc=True, errors="coerce")
    close_series = pd.to_numeric(df["close"], errors="coerce")

    mask_valid = time_series.notna() & close_series.notna()
    if mask_valid.sum() < max(5, lookback // 2):
        return None

    time_series = time_series[mask_valid]
    close_series = close_series[mask_valid]

    sub_time = time_series.tail(lookback)
    sub_close = close_series.tail(lookback)

    if sub_close.count() < 5:
        return None

    x = np.arange(len(sub_close))
    y = sub_close.values.astype(float)

    b1, b0 = np.polyfit(x, y, 1)  # y ≈ b1*x + b0
    y_fit = b1 * x + b0

    periods_per_year = _annualization_factor("1d")
    slope_rel = (b1 / max(np.mean(y), 1e-8)) * periods_per_year
    slope_pct = float(slope_rel * 100.0)

    diffs = sub_time.diff().dropna()
    if not diffs.empty and diffs.median() > pd.Timedelta(0):
        step = diffs.median()
    else:
        step = pd.Timedelta(days=1)

    last_time = sub_time.iloc[-1]
    proj_times = pd.to_datetime(
        [last_time + (i + 1) * step for i in range(horizon)],
        utc=True,
    )

    x_proj_idx = np.arange(len(sub_close), len(sub_close) + horizon)
    y_proj = b1 * x_proj_idx + b0

    return sub_time, y_fit, proj_times, y_proj, slope_pct


def _kmeans_regimes(df: pd.DataFrame, n_clusters: int = 3):
    """
    KMeans sur [ret, vol20]. Retourne labels (ou None si sklearn absent)
    et la liste de couleurs associées.
    """
    try:
        from sklearn.cluster import KMeans
    except Exception:
        return None, None

    X = pd.DataFrame({
        "ret": df["ret"].fillna(0.0),
        "vol20": df["vol20"].fillna(df["vol20"].median() if not df["vol20"].dropna().empty else 0.0),
    })
    try:
        km = KMeans(n_clusters=n_clusters, n_init="auto", random_state=0)
    except TypeError:
        km = KMeans(n_clusters=n_clusters, n_init=10, random_state=0)
    labels = km.fit_predict(X)

    palette = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728"]
    colors = [palette[l % len(palette)] for l in labels]
    return labels, colors


# ===============================
# Deep Learning : Autoencoder anomalies
# ===============================
class _TinyAutoencoder(nn.Module):
    def __init__(self, n_features: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(n_features, 8),
            nn.ReLU(),
            nn.Linear(8, 3),
            nn.ReLU(),
        )
        self.decoder = nn.Sequential(
            nn.Linear(3, 8),
            nn.ReLU(),
            nn.Linear(8, n_features),
        )

    def forward(self, x):
        z = self.encoder(x)
        out = self.decoder(z)
        return out


def _dl_autoencoder_anomaly_scores(
    df: pd.DataFrame,
    n_epochs: int = 20,
    batch_size: int = 32,
):
    """
    Entraîne un minuscule autoencoder sur quelques features techniques
    et retourne une série 'reconstruction_error' alignée sur df.index.
    """
    if torch is None or nn is None:
        return None, "PyTorch n'est pas installé dans l'environnement."

    feat_cols = ["ret", "vol20", "rsi14", "macd", "macd_signal"]
    feat_cols = [c for c in feat_cols if c in df.columns]
    if len(feat_cols) < 3:
        return None, "Pas assez de features techniques pour l'autoencoder."

    feats = df[feat_cols].dropna()
    if len(feats) < 100:
        return None, "Trop peu de données pour entraîner un autoencoder (min ≈100 lignes)."

    X = feats.values.astype("float32")
    mu = X.mean(axis=0, keepdims=True)
    sigma = X.std(axis=0, keepdims=True)
    sigma[sigma == 0] = 1.0
    Xn = (X - mu) / sigma

    x_tensor = torch.from_numpy(Xn)
    n_features = Xn.shape[1]

    model = _TinyAutoencoder(n_features)
    opt = torch.optim.Adam(model.parameters(), lr=1e-3)
    loss_fn = nn.MSELoss()

    model.train()
    n = len(x_tensor)
    for _ in range(n_epochs):
        perm = torch.randperm(n)
        for i in range(0, n, batch_size):
            idx = perm[i: i + batch_size]
            batch = x_tensor[idx]
            opt.zero_grad()
            recon = model(batch)
            loss = loss_fn(recon, batch)
            loss.backward()
            opt.step()

    model.eval()
    with torch.no_grad():
        recon = model(x_tensor)
        errors = ((x_tensor - recon) ** 2).mean(dim=1).cpu().numpy()

    scores = pd.Series(errors, index=feats.index, name="ae_recon_error")
    return scores, None


# ===============================
# Reinforcement Learning : Q-learning sur SMA (aligné TradingEnvSMA)
# ===============================
def _train_q_learning_sma(
    bt: pd.DataFrame,
    fee_bps: float = 5.0,
    episodes: int = 50,
    gamma: float = 0.95,
    alpha: float = 0.1,
    epsilon: float = 0.1,
):
    """
    Agent RL (Q-learning tabulaire) aligné avec TradingEnvSMA.

    - États: (position, sign_sma, rsi_bin, vol_bin)
        position ∈ {-1,0,1}
        sign_sma ∈ {-1,0,1}  (signe de sma_fast - sma_slow)
        rsi_bin ∈ {-1,0,1}   (<40, entre 40 et 60, >60)
        vol_bin ∈ {0,1}      (vol <= médiane, vol > médiane)

    - Actions: -1 (short), 0 (cash), 1 (long)
    - Récompense: position_future * ret_{t+1} - frais si changement de position

    Retourne:
        - q_table: dict[(pos, sign_sma, rsi_bin, vol_bin)][action] = Q
        - liste_pnl_episodes: liste des PnL cumulés par épisode
    """
    required_cols = ["ret", "sma_fast", "sma_slow", "rsi14", "vol20"]
    if any(c not in bt.columns for c in required_cols):
        return None, []

    data = bt.dropna(subset=required_cols).copy()
    if len(data) < 50:
        return None, []

    # Pré-calcul des signaux
    sign_sma = np.sign(data["sma_fast"] - data["sma_slow"]).astype(int).values
    rets = data["ret"].values
    rsi_vals = data["rsi14"].values
    vol_vals = data["vol20"].values

    # Binarisation RSI
    rsi_bin = np.zeros_like(rsi_vals, dtype=int)
    rsi_bin[rsi_vals > 60] = 1
    rsi_bin[rsi_vals < 40] = -1

    # Binarisation Volatilité
    vol_median = np.nanmedian(vol_vals) if not np.isnan(vol_vals).all() else 0.0
    vol_bin = (vol_vals > vol_median).astype(int)

    fee = fee_bps / 10000.0

    positions = [-1, 0, 1]
    sign_vals = [-1, 0, 1]
    rsi_vals_set = [-1, 0, 1]
    vol_vals_set = [0, 1]
    actions = [-1, 0, 1]

    # Q-table: dict[state][action]
    Q: dict[tuple[int, int, int, int], dict[int, float]] = {}
    for p in positions:
        for s in sign_vals:
            for rb in rsi_vals_set:
                for vb in vol_vals_set:
                    Q[(p, s, rb, vb)] = {a: 0.0 for a in actions}

    episode_pnls: list[float] = []

    n = len(data)
    for _ in range(episodes):
        pos = 0
        pnl = 0.0

        for t in range(n - 1):
            s_sma = int(sign_sma[t])
            rb = int(rsi_bin[t])
            vb = int(vol_bin[t])
            state = (pos, s_sma, rb, vb)

            # ε-greedy
            if np.random.rand() < epsilon:
                act = int(np.random.choice(actions))
            else:
                qvals = Q[state]
                act = max(qvals, key=qvals.get)

            new_pos = act
            trade_cost = fee if new_pos != pos else 0.0
            r = new_pos * rets[t + 1] - trade_cost
            pnl += r

            s_sma_next = int(sign_sma[t + 1])
            rb_next = int(rsi_bin[t + 1])
            vb_next = int(vol_bin[t + 1])
            next_state = (new_pos, s_sma_next, rb_next, vb_next)

            best_next = max(Q[next_state].values())
            old_q = Q[state][act]
            Q[state][act] = old_q + alpha * (r + gamma * best_next - old_q)

            pos = new_pos

        episode_pnls.append(float(pnl))

    return Q, episode_pnls


# ===============================
# Environnement RL basé sur SMA (DQN)
# ===============================
class TradingEnvSMA:
    """
    Environnement de trading simple pour RL:
    - action ∈ {-1, 0, 1} → short, cash, long
    - état = [position, sign_sma, rsi_bin, vol_bin]
    """

    def __init__(self, df: pd.DataFrame, fee_bps: float = 5.0):
        # On suppose que df contient déjà: time, close, ret, sma_fast, sma_slow, rsi14, vol20
        self.df = df.dropna(subset=["ret", "sma_fast", "sma_slow", "rsi14", "vol20"]).reset_index(drop=True)
        self.fee = fee_bps / 10000.0
        self.t = 0
        self.position = 0  # -1 short, 0 cash, 1 long

    def reset(self):
        self.t = 0
        self.position = 0
        return self._get_state()

    def step(self, action: int):
        """
        action ∈ {-1, 0, 1}
        Retourne: (state_next, reward, done, info)
        """
        reward = 0.0
        done = False

        if self.t < len(self.df) - 1:
            ret_tp1 = float(self.df.loc[self.t + 1, "ret"])
        else:
            done = True
            return self._get_state(), 0.0, True, {}

        new_position = int(action)
        trade_cost = self.fee if new_position != self.position else 0.0
        reward = new_position * ret_tp1 - trade_cost

        self.position = new_position
        self.t += 1

        if self.t >= len(self.df) - 2:
            done = True

        return self._get_state(), float(reward), bool(done), {}

    def _get_state(self) -> np.ndarray:
        row = self.df.loc[self.t]

        sign_sma = int(np.sign(row["sma_fast"] - row["sma_slow"]))

        if row["rsi14"] > 60:
            rsi_bin = 1
        elif row["rsi14"] < 40:
            rsi_bin = -1
        else:
            rsi_bin = 0

        if row["vol20"] > self.df["vol20"].median():
            vol_bin = 1
        else:
            vol_bin = 0

        return np.array([self.position, sign_sma, rsi_bin, vol_bin], dtype=np.float32)


# ===============================
# Réseau DQN + Replay Buffer
# ===============================
if nn is not None:
    class DQN(nn.Module):
        def __init__(self, state_dim: int = 4, action_dim: int = 3):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim, 32),
                nn.ReLU(),
                nn.Linear(32, 32),
                nn.ReLU(),
                nn.Linear(32, action_dim),
            )

        def forward(self, x):
            return self.net(x)
else:
    class DQN:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("PyTorch n'est pas installé → DQN indisponible.")


class ReplayBuffer:
    def __init__(self, size: int = 5000):
        self.buffer = deque(maxlen=size)

    def add(self, exp):
        self.buffer.append(exp)

    def sample(self, batch_size: int = 64):
        batch = random.sample(self.buffer, batch_size)
        s, a, r, sn, d = zip(*batch)
        return (
            torch.tensor(s, dtype=torch.float32),
            torch.tensor(a, dtype=torch.int64),
            torch.tensor(r, dtype=torch.float32),
            torch.tensor(sn, dtype=torch.float32),
            torch.tensor(d, dtype=torch.float32),
        )

    def __len__(self):
        return len(self.buffer)


def train_dqn(env: TradingEnvSMA, episodes: int = 50):
    """
    Entraîne un DQN sur l'environnement TradingEnvSMA.
    - Policy ε-greedy
    - réseau cible
    - γ = 0.95, lr = 1e-3, batch = 64
    Retourne: (q_net, liste_rewards_episodes)
    """
    if torch is None or nn is None or optim is None:
        raise RuntimeError("PyTorch n'est pas disponible pour entraîner le DQN.")

    state_dim = 4
    action_dim = 3

    q_net = DQN(state_dim, action_dim)
    target_net = DQN(state_dim, action_dim)
    target_net.load_state_dict(q_net.state_dict())
    target_net.eval()

    optimizer = optim.Adam(q_net.parameters(), lr=1e-3)
    gamma = 0.95
    epsilon = 0.2
    batch_size = 64
    buffer = ReplayBuffer()

    episode_rewards: list[float] = []

    for ep in range(episodes):
        s = env.reset()
        done = False
        total_reward = 0.0

        while not done:
            if np.random.rand() < epsilon:
                a = np.random.randint(0, 3)
            else:
                with torch.no_grad():
                    qs = q_net(torch.tensor(s, dtype=torch.float32).unsqueeze(0))
                a = int(qs.argmax(dim=1).item())

            mapped_a = [-1, 0, 1][a]
            sn, r, done, _ = env.step(mapped_a)

            buffer.add((s, a, r, sn, done))
            s = sn
            total_reward += r

            if len(buffer) > batch_size:
                S, A, R, SN, D = buffer.sample(batch_size)

                with torch.no_grad():
                    target_q = target_net(SN).max(1)[0]
                    Y = R + gamma * target_q * (1.0 - D)

                q_values = q_net(S).gather(1, A.unsqueeze(1)).squeeze()
                loss = nn.MSELoss()(q_values, Y)

                optimizer.zero_grad()
                loss.backward()
                optimizer.step()

        episode_rewards.append(float(total_reward))

        if ep % 5 == 0:
            target_net.load_state_dict(q_net.state_dict())

    return q_net, episode_rewards


# ===============================
# Sauvegarde quotidienne OHLCV (ancienne version, gardée pour compat)
# ===============================
def _save_daily_csv(
    df: pd.DataFrame,
    symbol: str,
    interval: str,
    period: str,
    root_dir: str = "data/market",
) -> Path:
    """
    Sauvegarde un CSV quotidien pour un symbole donné.

    Structure de sortie:
        data/market/YYYY-MM-DD/INDEX_FCHI_1d_1y.csv
        data/market/YYYY-MM-DD/BNP.PA_1d_1y.csv
    """
    df = df.copy()

    if "time" in df.columns:
        df["time"] = pd.to_datetime(df["time"])
        df = df.sort_values("time")

    today_str = date.today().isoformat()
    out_dir = Path(root_dir) / today_str
    out_dir.mkdir(parents=True, exist_ok=True)

    safe_symbol = symbol.replace("^", "INDEX_")
    fname = f"{safe_symbol}_{interval}_{period}.csv"
    out_path = out_dir / fname

    df.to_csv(out_path, index=False)
    return out_path


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
            "CAGR": "Taux de croissance annuel composé (annualisé).",
            "Max drawdown (MaxDD)": "Perte maximale entre un sommet et le plus bas suivant.",
            "Buy & Hold": "Stratégie passive : acheter puis conserver l’actif.",
            "z-score (ret)": "Nombre d’écarts-types par rapport à la moyenne roulante.",
        }
        for title, desc in terms.items():
            st.markdown(f"**{title}** — {desc}")


# ===============================
# UI principale
# ===============================
DEFAULT_SYMBOLS = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]
def call_n8n_market_radar(
    symbols: str = "^FCHI,BNP.PA,AIR.PA,MC.PA,OR.PA,ORA.PA",
    interval: str = "1d",
    period: str = "1y",
):
    """
    Appelle le workflow n8n 'Market Radar - IT-STORM' via le webhook
    et renvoie un DataFrame avec une ligne par symbole.
    """
    base = os.getenv("N8N_BASE_URL", "http://127.0.0.1:5678").rstrip("/")
    url = f"{base}/webhook/market-radar"

    payload = {
        "symbols": symbols,
        "interval": interval,
        "period": period,
    }

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
    except Exception as e:
        st.error(f"Erreur appel n8n Market Radar : {e}")
        return None

    # n8n peut renvoyer soit un dict, soit une liste de dicts
    try:
        data = resp.json()
    except json.JSONDecodeError:
        st.error("Réponse n8n non valide (JSON).")
        return None

    # Normalisation en liste
    if isinstance(data, dict):
        items = [data]
    elif isinstance(data, list):
        items = data
    else:
        st.error(f"Format de réponse inattendu depuis n8n : {type(data)}")
        return None

    cleaned = []
    for it in items:
        # si un jour tu repasses en {{ $items() }}, gère aussi { "json": {...} }
        row = it.get("json", it)

        error = row.get("error")
        if isinstance(error, dict):
            error_message = error.get("message")
            error_status = error.get("status")
        else:
            error_message = None
            error_status = None

        cleaned.append(
            {
                "symbol": row.get("symbol"),
                "nb_candles": row.get("nb_candles", 0),
                "source": row.get("source", "backend"),
                "interval": row.get("interval"),
                "period": row.get("period"),
                "error_message": error_message,
                "error_status": error_status,
                "fetched_at": row.get("fetched_at"),
            }
        )

    if not cleaned:
        st.warning("Aucun résultat reçu depuis n8n.")
        return None

    return pd.DataFrame(cleaned)


def render() -> None:
    """Tableau de bord 'Market Watch' avec mini-ML, reco & backtest."""
    API_BASE = os.getenv("MARKET_API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")

    def api_get(path: str, **params):
        try:
            r = requests.get(API_BASE + path, params=params, timeout=12)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            st.error(f"API error: {e}")
            return None

    # ------------------------------------------------------------------
    # Liste fixe des 6 actifs à suivre (pour la sauvegarde auto)
    # ------------------------------------------------------------------
    DEFAULT_SYMBOLS = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]

    st.caption("💾 Sauvegarde automatique des données quotidiennes (1d, 1y) en local si API OK.")

    # ------------------------------------------------------------------
    # Sélection de l'actif / période
    # ------------------------------------------------------------------
    col_asset, col_interval, col_period = st.columns([2, 1, 1])
    with col_asset:
        symbol = st.selectbox(
            "Actif",
            ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"],
            index=0,
        )
    with col_interval:
        interval = st.selectbox(
            "Intervalle",
            ["1d", "1h"],
            index=0,
            help="Résolution des chandeliers.",
        )
    with col_period:
        period = st.selectbox(
            "Période",
            ["6mo", "1y", "2y"],
            index=1,
            help="Fenêtre historique globale.",
        )

    # ------------------------------------------------------------------
    # Récupération des données marché via l'API FastAPI
    # ------------------------------------------------------------------
    data = api_get(f"/v1/ohlcv/{symbol}", interval=interval, period=period)
    if not data or "candles" not in data:
        st.error("Impossible de récupérer les données de marché.")
        _glossary_ui()
        return

    candles = data["candles"]
    if not candles:
        st.warning("Pas de chandelles retournées par l'API.")
        _glossary_ui()
        return

    df = pd.DataFrame(candles)

    # Sauvegarde auto sur disque (1d, 1y seulement, pour les 6 actifs)
    if interval == "1d" and period == "1y" and symbol in DEFAULT_SYMBOLS:
        try:
            _save_daily_csv(df, symbol, interval=interval, period=period)
        except Exception as e:
            st.warning(f"Impossible de sauvegarder le CSV localement : {e}")

    if df.empty:
        st.warning("DataFrame vide après conversion.")
        _glossary_ui()
        return

    # Indicateurs techniques
    df = _compute_indicators(df, interval=interval)

    if df.empty or "close" not in df.columns:
        st.warning("Impossible de calculer les indicateurs sur ces données.")
        _glossary_ui()
        return

    # ------------------------------------------------------------------
    # Signal & KPIs (ligne synthèse)
    # ------------------------------------------------------------------
    last = df.iloc[-1]
    st.markdown("### 🔎 Synthèse instantanée")

    col_k1, col_k2, col_k3, col_k4 = st.columns(4)
    with col_k1:
        if "close" in last:
            st.metric("Prix", f"{last['close']:,.2f}")
    with col_k2:
        if "sma20" in last and not np.isnan(last["sma20"]) and "close" in last:
            st.metric("Écart vs SMA20", f"{(last['close']/last['sma20']-1):+.2%}")
    with col_k3:
        if "vol20" in last and not np.isnan(last["vol20"]):
            st.metric("Vol(20, ann.)", f"{last['vol20']:.0%}")
    with col_k4:
        if "rsi14" in last and not np.isnan(last["rsi14"]):
            st.metric("RSI(14)", f"{last['rsi14']:.1f}")

    st.markdown("---")

    # ------------------------------------------------------------------
    # Sous-onglets : graphes & analyses
    # ------------------------------------------------------------------
    tab_report,tab_price, tab_mom, tab_diag, tab_bt, tab_data,tab_n8n = st.tabs(
        [
            "📰 Daily Report",
            "📊 Prix & moyennes mobiles",
            "📈 Momentum & oscillateurs",
            "🧪 Diagnostics ML",
            "📈 Backtest SMA & RL",
            "📄 Données brutes",
            "🤝 n8n Market Radar",

             
        ]
    )

    # ===== TAB 1 : Prix & moyennes =====
    with tab_price:
        st.markdown("### 📊 Prix, moyennes mobiles & volatilité")
        st.caption("Lecture visuelle de la tendance et de la volatilité du prix.")

        # =========================
        # 🧠 Lecture dynamique (1 phrase)
        # =========================
        price_last = float(df["close"].iloc[-1])
        sma20_last = float(df["sma20"].iloc[-1]) if "sma20" in df and not pd.isna(df["sma20"].iloc[-1]) else None
        sma50_last = float(df["sma50"].iloc[-1]) if "sma50" in df and not pd.isna(df["sma50"].iloc[-1]) else None

        trend_txt = None
        if sma20_last is not None and sma50_last is not None:
            if price_last > sma20_last > sma50_last:
                trend_txt = "Tendance haussière visible : le prix évolue au-dessus de ses moyennes."
            elif price_last < sma20_last < sma50_last:
                trend_txt = "Tendance baissière : le prix reste sous ses moyennes mobiles."
            else:
                trend_txt = "Marché sans direction claire : le prix oscille autour des moyennes."

        # Bollinger (position actuelle)
        try:
            bb_window = 20
            ma = df["close"].rolling(bb_window).mean()
            std = df["close"].rolling(bb_window).std()
            upper = ma + 2 * std
            lower = ma - 2 * std

            if price_last >= upper.iloc[-1]:
                trend_txt += " Le prix est proche de la borne haute de volatilité."
            elif price_last <= lower.iloc[-1]:
                trend_txt += " Le prix est proche de la borne basse de volatilité."
        except Exception:
            pass

        if trend_txt:
            st.info(trend_txt)

        # =========================
        # 📌 Mini KPIs (UX)
        # =========================
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("Dernier prix", f"{price_last:.2f}")
        with k2:
            st.metric("SMA20", f"{sma20_last:.2f}" if sma20_last is not None else "—")
        with k3:
            st.metric("SMA50", f"{sma50_last:.2f}" if sma50_last is not None else "—")

        st.markdown("---")

        # =========================
        # 📈 Graphique principal
        # =========================
        fig = go.Figure()
        fig.add_trace(
            go.Candlestick(
                x=df["time"],
                open=df["open"],
                high=df["high"],
                low=df["low"],
                close=df["close"],
                name="OHLC",
            )
        )

        # Moyennes mobiles
        if "sma20" in df.columns:
            fig.add_trace(go.Scatter(x=df["time"], y=df["sma20"], name="SMA20", mode="lines"))
        if "sma50" in df.columns:
            fig.add_trace(go.Scatter(x=df["time"], y=df["sma50"], name="SMA50", mode="lines"))

        # Bollinger Bands (20, 2σ)
        try:
            fig.add_trace(go.Scatter(x=df["time"], y=upper, name="Bollinger +2σ", mode="lines", line=dict(dash="dot")))
            fig.add_trace(go.Scatter(x=df["time"], y=lower, name="Bollinger -2σ", mode="lines", line=dict(dash="dot")))
        except Exception:
            pass

        fig.update_layout(
            margin=dict(l=10, r=10, t=40, b=10),
            height=500,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.caption(
            "Les moyennes mobiles aident à lire la tendance, "
            "tandis que les bandes de Bollinger donnent une indication sur la volatilité."
        )

    # ===== TAB 2 : Momentum & oscillateurs =====
    with tab_mom:
        st.markdown("### 📈 Momentum (RSI & MACD)")
        st.caption("Lecture rapide du momentum : excès (RSI) + dynamique (MACD).")

        # =========================
        # 🧠 Lecture dynamique (1 phrase)
        # =========================
        rsi_last = float(df["rsi14"].dropna().iloc[-1]) if "rsi14" in df and df["rsi14"].notna().any() else None
        macd_last = float(df["macd"].dropna().iloc[-1]) if "macd" in df and df["macd"].notna().any() else None
        sig_last = float(df["macd_signal"].dropna().iloc[-1]) if "macd_signal" in df and df["macd_signal"].notna().any() else None

        macd_hist_last = None
        if macd_last is not None and sig_last is not None:
            macd_hist_last = macd_last - sig_last

        momentum_txt = None
        if rsi_last is not None:
            if rsi_last > 70:
                momentum_txt = "RSI élevé : zone de surachat, un essoufflement est possible."
            elif rsi_last < 30:
                momentum_txt = "RSI faible : zone de survente, un rebond technique est possible."
            else:
                momentum_txt = "RSI neutre : pas d’excès clair sur cette période."

        if macd_hist_last is not None:
            if macd_hist_last > 0:
                momentum_txt = (momentum_txt or "Momentum") + " MACD confirme une dynamique plutôt haussière."
            elif macd_hist_last < 0:
                momentum_txt = (momentum_txt or "Momentum") + " MACD indique une dynamique plutôt baissière."
            else:
                momentum_txt = (momentum_txt or "Momentum") + " MACD est proche de l’équilibre."

        if momentum_txt:
            st.info(momentum_txt)

        # =========================
        # 📌 Mini KPIs (UX)
        # =========================
        k1, k2, k3 = st.columns(3)
        with k1:
            st.metric("RSI(14)", f"{rsi_last:.1f}" if rsi_last is not None else "—")
        with k2:
            st.metric("MACD", f"{macd_last:.3f}" if macd_last is not None else "—")
        with k3:
            st.metric("Hist(MACD)", f"{macd_hist_last:.3f}" if macd_hist_last is not None else "—")

        st.markdown("---")

        col_m1, col_m2 = st.columns(2)

        with col_m1:
            st.markdown("**RSI(14)**")
            if "rsi14" in df:
                fig_rsi = go.Figure(
                    data=[
                        go.Scatter(
                            x=df["time"],
                            y=df["rsi14"],
                            name="RSI(14)",
                            mode="lines",
                        )
                    ]
                )
                fig_rsi.add_hline(y=70, line_dash="dot")
                fig_rsi.add_hline(y=30, line_dash="dot")
                fig_rsi.update_layout(
                    margin=dict(l=10, r=10, t=30, b=10),
                    height=260,
                )
                st.plotly_chart(fig_rsi, use_container_width=True)
            else:
                st.info("RSI(14) indisponible.")

        with col_m2:
            st.markdown("**MACD(12,26,9)**")
            if "macd" in df and "macd_signal" in df:
                macd_hist = (df["macd"] - df["macd_signal"]).fillna(0.0)

                fig_macd = go.Figure()
                fig_macd.add_trace(
                    go.Bar(
                        x=df["time"],
                        y=macd_hist,
                        name="Histogram",
                    )
                )
                fig_macd.add_trace(
                    go.Scatter(
                        x=df["time"], y=df["macd"], name="MACD", mode="lines"
                    )
                )
                fig_macd.add_trace(
                    go.Scatter(
                        x=df["time"],
                        y=df["macd_signal"],
                        name="Signal",
                        mode="lines",
                    )
                )
                fig_macd.add_hline(y=0, line_dash="dot")
                fig_macd.update_layout(
                    margin=dict(l=10, r=10, t=30, b=10),
                    height=260,
                )
                st.plotly_chart(fig_macd, use_container_width=True)
            else:
                st.info("MACD indisponible.")

    # ===== TAB 3 : Diagnostics mini-ML =====
    with tab_diag:
        st.markdown("## 🧪 Diagnostics ML")
        st.caption("Lecture guidée du risque de marché : anomalies, tendance et régimes.")

        # =========================
        # 0) Calculs rapides pour le résumé (robustes)
        # =========================
        z_mask_full = _rolling_zscore_anomalies(df, window=20, z_thresh=2.0)
        risk_z = float(z_mask_full.tail(90).mean()) if len(z_mask_full) >= 90 else float(z_mask_full.mean())

        labels, _ = _kmeans_regimes(df, n_clusters=3)
        risk_reg = 0.0
        if labels is not None and "vol20" in df.columns:
            reg_df = pd.DataFrame(
                {"vol20": df["vol20"].fillna(df["vol20"].median()), "regime": labels},
                index=df.index,
            )
            high_reg = reg_df.groupby("regime")["vol20"].mean().idxmax()
            risk_reg = float((reg_df["regime"] == high_reg).tail(90).mean()) if len(reg_df) >= 90 else float((reg_df["regime"] == high_reg).mean())

        # Autoencoder : seulement si activé plus bas
        ae_mask_full = pd.Series(False, index=df.index)
        risk_ae = 0.0

        # Tendance (pour interprétation)
        slope_pct = None
        trend = _trend_slope_and_projection(df, lookback=60, horizon=10)
        if trend:
            x_hist, y_hist, x_proj, y_proj, slope_pct = trend

        # =========================
        # 1) 🧠 LECTURE & DÉCISION (EN HAUT)
        # =========================
        st.markdown("### 🧠 Lecture & décision")

        # Score composite simple (AE = 0 tant qu'il n'est pas activé)
        score_raw = 0.55 * risk_z + 0.30 * risk_reg + 0.15 * risk_ae
        score_pct = round(score_raw * 100, 1)

        if score_raw < 0.15:
            level, title = "🟢", "Risque faible"
            decision = "Décision : contexte plutôt calme, les signaux d’analyse sont globalement exploitables."
        elif score_raw < 0.35:
            level, title = "🟡", "Risque modéré"
            decision = "Décision : prudence raisonnable, privilégier les signaux clairs et éviter de sur-interpréter."
        else:
            level, title = "🔴", "Risque élevé"
            decision = "Décision : contexte tendu, limiter les prises de position et attendre une stabilisation."

        c1, c2 = st.columns([1, 3])
        with c1:
            st.metric("Score (0–100)", f"{score_pct} / 100")
            st.markdown(f"**{level} {title}**")
        with c2:
            notes = []

            # Anomalies z-score
            if risk_z < 0.05:
                notes.append("Peu d’anomalies statistiques récentes (z-score).")
            elif risk_z < 0.12:
                notes.append("Quelques anomalies statistiques : surveillance conseillée.")
            else:
                notes.append("Anomalies fréquentes : comportements atypiques visibles.")

            # Régimes de volatilité
            if risk_reg < 0.35:
                notes.append("Régime volatil peu dominant récemment.")
            elif risk_reg < 0.6:
                notes.append("Régime volatil présent une part significative du temps.")
            else:
                notes.append("Régime volatil dominant : risque de variations rapides.")

            # Tendance
            if slope_pct is not None:
                if slope_pct > 8:
                    notes.append("Tendance haussière marquée sur la fenêtre récente.")
                elif slope_pct < -8:
                    notes.append("Tendance baissière marquée sur la fenêtre récente.")
                else:
                    notes.append("Tendance faible à neutre sur la fenêtre récente.")
            else:
                notes.append("Tendance non déterminée (données insuffisantes).")

            for n in notes:
                st.write(f"- {n}")

        st.info(decision)

        with st.expander("🔎 Pourquoi ce verdict ?"):
            st.write(
                "- Le score combine : fréquence d’anomalies (z-score), présence d’un régime volatil (KMeans), et anomalies DL si activées.\n"
                "- Un risque élevé signifie : davantage d’événements atypiques + volatilité plus fréquente.\n"
                "- Ce diagnostic décrit un **contexte** (marché), pas une recommandation d’investissement."
            )

        st.markdown("---")

        # =========================
        # 2) Z-SCORE (simple)
        # =========================
        with st.expander("📊 Anomalies statistiques (z-score)"):
            r1, r2 = st.columns([1, 1])
            with r1:
                z_window = st.slider("Fenêtre", 10, 60, 20, 1)
            with r2:
                z_thresh = st.slider("Seuil |z|", 1.5, 3.5, 2.0, 0.1)

            z_mask = _rolling_zscore_anomalies(df, window=z_window, z_thresh=z_thresh)
            st.write(f"Anomalies détectées : **{int(z_mask.sum())}** points.")
            if z_mask.any():
                st.dataframe(df.loc[z_mask, ["time", "close", "ret"]].tail(10), use_container_width=True)
            else:
                st.info("Aucune anomalie significative détectée avec ces paramètres.")

        # =========================
        # 3) TENDANCE & PROJECTION
        # =========================
        with st.expander("📈 Tendance estimée & projection"):
            if trend:
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df["time"], y=df["close"], name="Close"))
                fig.add_trace(go.Scatter(x=df["time"].tail(len(y_hist)), y=y_hist, name="Régression"))
                fig.add_trace(go.Scatter(x=x_proj, y=y_proj, name="Projection", line=dict(dash="dot")))
                fig.update_layout(
                    title=f"Tendance annualisée ≈ {slope_pct:+.1f}%" if slope_pct is not None else "Tendance estimée",
                    height=320,
                    margin=dict(l=10, r=10, t=40, b=10),
                )
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("Données insuffisantes pour estimer la tendance.")

        # =========================
        # 4) RÉGIMES DE MARCHÉ
        # =========================
        with st.expander("🧩 Régimes de marché (K-Means)"):
            if labels is None:
                st.info("K-Means indisponible (scikit-learn absent).")
            else:
                st.write("Répartition récente des régimes.")
                preview = df[["time", "ret", "vol20"]].copy()
                preview["regime"] = labels
                st.dataframe(preview.tail(15), use_container_width=True)

        # =========================
        # 5) AUTOENCODER (avancé)
        # =========================
        with st.expander("🤖 Autoencoder DL (avancé)"):
            if torch is None or nn is None:
                st.info("PyTorch non installé.")
            else:
                if st.checkbox("Activer l’autoencoder"):
                    with st.spinner("Entraînement rapide…"):
                        scores, msg = _dl_autoencoder_anomaly_scores(df)
                    if scores is None:
                        st.warning(msg)
                    else:
                        q97 = float(np.quantile(scores, 0.97))
                        mask = scores > q97
                        ae_mask_full.loc[mask.index] = mask
                        risk_ae = float(ae_mask_full.tail(90).mean()) if len(ae_mask_full) >= 90 else float(ae_mask_full.mean())

                        st.write(f"Anomalies DL détectées : **{int(mask.sum())}**")
                        st.dataframe(
                            df.loc[mask.index, ["time", "close"]].assign(ae_error=scores[mask]),
                            use_container_width=True,
                        )

                        st.caption("💡 Remarque : l’autoencoder ajoute un signal DL ; le score en haut reste basé sur z-score + régimes (sauf si tu décides de le recalculer).")

    # ===== TAB 4 : Backtest SMA =====
    with tab_bt:
        st.markdown("## 📈 Backtest SMA & décisions")
        st.caption("Baseline : croisement de moyennes mobiles. Lecture guidée + modules RL optionnels.")

        # ---------- Réglages (UI clean) ----------
        with st.expander("⚙️ Réglages du backtest", expanded=True):
            cA, cB, cC = st.columns(3)
            with cA:
                fast = st.slider("SMA courte", 5, 50, 20, 1)
            with cB:
                slow = st.slider("SMA longue", 20, 200, 50, 5)
            with cC:
                fee_bps = st.slider("Frais (bps)", 0.0, 50.0, 5.0, 0.5, help="1 bps = 0,01%")

            if slow <= fast:
                st.warning("Conseil : SMA longue devrait être > SMA courte (sinon signal instable).")

        base = df.dropna(subset=["close"]).copy()
        if len(base) < max(fast, slow) + 10:
            st.info("Pas assez de données pour le backtest.")
        else:
            bt = _backtest_sma(base, fast=fast, slow=slow, fee_bps=fee_bps)

            # ✅ CORRECTION : stats sur strat_ret (et non ret)
            stats_sma = _bt_stats(bt["strat_ret"], interval)
            stats_bh = _bt_stats(bt["bh_ret"], interval)

            # ---------- Courbes equity ----------
            st.markdown("### 📉 Équité cumulée")
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=base["time"], y=stats_sma["equity"], name="Stratégie SMA"))
            fig.add_trace(go.Scatter(x=base["time"], y=stats_bh["equity"], name="Buy & Hold"))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=30, b=10))
            st.plotly_chart(fig, use_container_width=True)

            # ---------- KPIs (UI : 3 colonnes x 2 blocs) ----------
            st.markdown("### 📊 Indicateurs clés")

            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**Stratégie SMA**")
                k1, k2, k3 = st.columns(3)
                with k1:
                    st.metric("CAGR", f"{stats_sma['cagr']*100:.2f}%")
                with k2:
                    st.metric("Sharpe", f"{stats_sma['sharpe']:.2f}")
                with k3:
                    st.metric("Max DD", f"{stats_sma['maxdd']*100:.2f}%")

            with c2:
                st.markdown("**Buy & Hold**")
                k4, k5, k6 = st.columns(3)
                with k4:
                    st.metric("CAGR", f"{stats_bh['cagr']*100:.2f}%")
                with k5:
                    st.metric("Sharpe", f"{stats_bh['sharpe']:.2f}")
                with k6:
                    st.metric("Max DD", f"{stats_bh['maxdd']*100:.2f}%")

            st.markdown("---")

            # ---------- Lecture & décision ----------
            def _bt_verdict(stats_sma: dict, stats_bh: dict):
                cagr_s, sh_s, mdd_s = stats_sma["cagr"], stats_sma["sharpe"], stats_sma["maxdd"]
                cagr_b, sh_b, mdd_b = stats_bh["cagr"], stats_bh["sharpe"], stats_bh["maxdd"]

                notes = []

                # perf/risque
                if sh_s > sh_b and cagr_s >= cagr_b * 0.9:
                    level, title = "🟢", "Stratégie SMA intéressante sur cette fenêtre"
                    notes.append("Le couple rendement/risque est compétitif vs Buy & Hold.")
                elif sh_s > 0 and cagr_s > 0:
                    level, title = "🟡", "Stratégie SMA correcte mais pas dominante"
                    notes.append("La stratégie fonctionne, mais l’avantage n’est pas net face à Buy & Hold.")
                else:
                    level, title = "🔴", "Stratégie SMA défavorable sur cette fenêtre"
                    notes.append("Le rendement/risque est dégradé : performance faible et/ou Sharpe négatif.")

                # drawdown
                if abs(mdd_s) < abs(mdd_b) * 0.85:
                    notes.append("Point positif : drawdown plus contenu que Buy & Hold.")
                elif abs(mdd_s) > abs(mdd_b) * 1.05:
                    notes.append("Point faible : drawdown plus important que Buy & Hold.")
                else:
                    notes.append("Drawdown comparable à Buy & Hold.")

                # lecture régime
                if sh_s < 0 and sh_b > 0:
                    notes.append("Marché plutôt directionnel : Buy & Hold capte la tendance, SMA peut se faire piéger (whipsaw).")
                elif sh_s > 0 and sh_b <= 0:
                    notes.append("Marché chahuté : SMA peut filtrer une partie des phases défavorables.")
                else:
                    notes.append("Réaction assez similaire des deux approches sur le régime actuel.")

                # décision
                if level == "🟢":
                    decision = "Décision : garder SMA comme baseline utile et tester une amélioration (filtre RSI/vol) pour stabiliser."
                elif level == "🟡":
                    decision = "Décision : conserver SMA comme référence et ajuster (fast/slow) ou la période d’étude."
                else:
                    decision = "Décision : éviter SMA telle quelle ici ; privilégier Buy & Hold sur cette fenêtre ou recalibrer (paramètres/période)."

                return level, title, notes, decision

            level, title, notes, decision = _bt_verdict(stats_sma, stats_bh)

            st.markdown("### 🧠 Lecture & décision")
            st.markdown(f"**{level} {title}**")
            for n in notes:
                st.write(f"- {n}")
            st.info(decision)

            with st.expander("🔎 Pourquoi la SMA peut sous-performer ?"):
                st.write(
                    "- Marché en tendance forte : Buy & Hold profite, SMA sort/entre trop tard.\n"
                    "- Marché en range : beaucoup d’allers-retours (whipsaw) → pertes + frais.\n"
                    "- Frais (bps) et signaux trop fréquents : impact direct sur la perf.\n"
                    "- Paramètres (fast/slow) non adaptés à la volatilité actuelle."
                )

            st.markdown("---")

            # =========================
            # RL EN OPTION (UX clean)
            # =========================
            with st.expander("🤖 Renforcement Learning (optionnel)"):
                st.caption("Modules pédagogiques (démonstration). Pas destinés à la production.")

                ep = st.slider("Épisodes Q-learning", 10, 200, 50, 10)

                run_rl = st.button("Lancer l’entraînement Q-learning", use_container_width=True)
                if run_rl:
                    with st.spinner("Apprentissage Q-learning…"):
                        rl_df = bt.dropna().copy()
                        q_table, pnl_hist = _train_q_learning_sma(rl_df, episodes=ep)

                    if not q_table or pnl_hist is None:
                        st.warning("Impossible d’entraîner l’agent (données insuffisantes ou colonnes manquantes).")
                    else:
                        st.success("Entraînement terminé.")
                        st.markdown("**PnL cumulé par épisode**")
                        st.line_chart(pd.Series(pnl_hist, name="PnL épisode"))

    # ===== TAB 5 : Données brutes & glossaire =====
    with tab_data:
        st.markdown("### 📄 Données brutes")

        cols_show = [
            "time",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "sma20",
            "sma50",
            "ema20",
            "rsi14",
            "macd",
            "macd_signal",
            "vol20",
        ]
        cols_show = [c for c in cols_show if c in df.columns]
        st.dataframe(df[cols_show].tail(15), use_container_width=True)

        st.markdown("---")
        _glossary_ui()
       
            # ===== TAB 6 : Daily Market Intelligence Report =====
    # ===== TAB 6 : Daily Market Intelligence Report =====
    # ===== TAB 6 : Daily Market Intelligence Report =====
    with tab_report:
        st.markdown("### 📰 Daily Market Intelligence Report")
        st.caption(
            "Synthèse quotidienne construite à partir de toutes les briques du Market Watch : "
            "prix, indicateurs techniques, anomalies ML, tendance, régimes de marché et backtest SMA."
        )

        st.markdown(
            "Clique sur le bouton ci-dessous pour analyser automatiquement les 6 actifs suivis "
            "et obtenir des **pistes de décision** lisibles (court / moyen terme)."
        )

        if st.button("🔍 Analyser le marché aujourd'hui", key="btn_daily_report"):
            with st.spinner("Analyse du marché en cours..."):

                symbols = ["^FCHI", "BNP.PA", "AIR.PA", "MC.PA", "OR.PA", "ORA.PA"]
                results: list[dict] = []

                for sym in symbols:
                    data_sym = api_get(f"/v1/ohlcv/{sym}", interval="1d", period="1y")
                    if not data_sym or "candles" not in data_sym:
                        continue

                    df_sym = pd.DataFrame(data_sym["candles"])
                    df_sym = _compute_indicators(df_sym, interval="1d")

                    if df_sym.empty or "close" not in df_sym.columns:
                        continue

                    # ---------- 1) Infos prix & indicateurs ----------
                    last = df_sym.iloc[-1]

                    price = float(last["close"])
                    last_ret = float(last.get("ret", 0.0)) if not pd.isna(last.get("ret", np.nan)) else 0.0

                    sma_gap = (
                        float(last["close"] / last["sma20"] - 1.0)
                        if "sma20" in df_sym.columns and not pd.isna(last.get("sma20", np.nan))
                        else None
                    )
                    rsi = float(last["rsi14"]) if "rsi14" in df_sym.columns and not pd.isna(last.get("rsi14", np.nan)) else None
                    vol = float(last["vol20"]) if "vol20" in df_sym.columns and not pd.isna(last.get("vol20", np.nan)) else None

                    # Plus haut / bas 55 périodes (pour zones support/résistance)
                    hh55 = (
                        float(last["hh_55"])
                        if "hh_55" in df_sym.columns and not pd.isna(last.get("hh_55", np.nan))
                        else None
                    )
                    ll55 = (
                        float(last["ll_55"])
                        if "ll_55" in df_sym.columns and not pd.isna(last.get("ll_55", np.nan))
                        else None
                    )

                    # ---------- 2) Signal global (ACHAT / NEUTRE / VENTE) ----------
                    reco = _score_and_reco(df_sym)

                    # ---------- 3) Anomalies (z-score) ----------
                    z_mask = _rolling_zscore_anomalies(df_sym, window=20, z_thresh=2.0)
                    anom_rate = float(z_mask.tail(60).mean())

                    # ---------- 4) Tendance (régression linéaire) ----------
                    trend = _trend_slope_and_projection(df_sym, lookback=60, horizon=10)
                    slope_pct = trend[4] if trend else 0.0  # annualisé en %

                    # Cibles très simples (projection linéaire → 1 et 3 mois)
                    monthly_drift = slope_pct / 100.0 / 12.0
                    target_1m = price * (1.0 + monthly_drift)
                    target_3m = price * (1.0 + monthly_drift * 3.0)

                    # ---------- 5) Régimes (K-Means sur [ret, vol20]) ----------
                    reg_risk_share = None
                    labels, _colors = _kmeans_regimes(df_sym, n_clusters=3)
                    if labels is not None and "vol20" in df_sym.columns:
                        try:
                            reg_df = pd.DataFrame(
                                {"vol20": df_sym["vol20"].fillna(df_sym["vol20"].median()), "regime": labels},
                                index=df_sym.index,
                            )
                            vol_by_reg = reg_df.groupby("regime")["vol20"].mean()
                            high_reg = vol_by_reg.idxmax()
                            high_mask = reg_df["regime"] == high_reg
                            reg_risk_share = float(high_mask.tail(60).mean())
                        except Exception:
                            reg_risk_share = None

                    # ---------- 6) Backtest SMA 20/50 par défaut ----------
                    stats_sma = None
                    stats_bh = None
                    base_sym = df_sym.dropna(subset=["close"]).copy()
                    if len(base_sym) > 80:
                        bt_sym = _backtest_sma(base_sym, fast=20, slow=50, fee_bps=5.0)
                        stats_sma = _bt_stats(bt_sym["strat_ret"].fillna(0.0), interval="1d")
                        stats_bh = _bt_stats(bt_sym["bh_ret"].fillna(0.0), interval="1d")

                    results.append(
                        {
                            "symbol": sym,
                            "price": price,
                            "last_ret": last_ret,
                            "sma_gap": sma_gap,
                            "rsi": rsi,
                            "vol": vol,
                            "hh55": hh55,
                            "ll55": ll55,
                            "label": reco["label"],
                            "score": reco["score"],
                            "bullets": reco["bullets"],
                            "anom_rate": anom_rate,
                            "slope_pct": slope_pct,
                            "target_1m": target_1m,
                            "target_3m": target_3m,
                            "reg_risk_share": reg_risk_share,
                            "stats_sma": stats_sma,
                            "stats_bh": stats_bh,
                        }
                    )

                if not results:
                    st.warning("Impossible de générer le rapport : aucune donnée exploitable.")
                else:
                    df_rep = pd.DataFrame(results)

                    # ==========================
                    # 0) Texte de décision à partir des signaux
                    # ==========================
                    def _decision_from_row(row) -> str:
                        label = row.get("label", "NEUTRE")
                        slope = float(row.get("slope_pct", 0.0))
                        anom = float(row.get("anom_rate", 0.0))
                        rsi_v = float(row.get("rsi", 50.0) or 50.0)

                        if label == "ACHAT":
                            if slope > 5 and anom < 0.08 and 50 <= rsi_v <= 70:
                                return "Biais haussier propre → conserver / renforcer sur repli léger."
                            elif anom >= 0.12:
                                return "Signal haussier mais contexte volatil → taille de position modérée."
                            else:
                                return "Léger avantage haussier → conserver, entrées progressives possibles."
                        elif label == "VENTE":
                            if slope < -5:
                                return "Biais baissier marqué → réduire l'exposition / sécuriser les gains."
                            else:
                                return "Tonalité fragile → alléger sur rebond, vigilance renforcée."
                        else:  # NEUTRE
                            if abs(slope) < 2 and anom < 0.08:
                                return "Marché neutre et calme → observer, pas de prise de position forte."
                            elif slope > 0:
                                return "Neutre mais légèrement haussier → petites entrées progressives possibles."
                            else:
                                return "Neutre avec biais baissier → attendre un meilleur point d'entrée."

                    df_rep["decision"] = df_rep.apply(_decision_from_row, axis=1)

                    # ==========================
                    # 1) Vue globale du marché (jolie)
                    # ==========================
                    nb_achat = (df_rep["label"] == "ACHAT").sum()
                    nb_vente = (df_rep["label"] == "VENTE").sum()
                    nb_neutre = (df_rep["label"] == "NEUTRE").sum()

                    mean_anom = float(df_rep["anom_rate"].mean()) if "anom_rate" in df_rep else 0.0
                    mean_vol = float(df_rep["vol"].mean()) if "vol" in df_rep else 0.0

                    if mean_anom < 0.05 and mean_vol < 0.2:
                        risk_label = "Faible"
                        risk_icon = "🟢"
                        risk_comment = "Marché globalement calme : peu d'anomalies et volatilité modérée."
                    elif mean_anom < 0.12 and mean_vol < 0.3:
                        risk_label = "Modéré"
                        risk_icon = "🟡"
                        risk_comment = "Quelques tensions ou mouvements atypiques, mais rien d'extrême."
                    else:
                        risk_label = "Élevé"
                        risk_icon = "🔴"
                        risk_comment = "Multiples signaux d’anomalies et/ou volatilité marquée sur plusieurs valeurs."

                    st.markdown("""
                    <div style="
                        font-size: 1.4rem; 
                        font-weight: 600; 
                        margin-bottom: 0.5rem;
                    ">
                    🌍 Vue globale du marché — <span style='color:#888'>(6 actifs suivis)</span>
                    </div>
                    """, unsafe_allow_html=True)

                    col1, col2, col3, col4 = st.columns(4)

                    # ----- ACHAT -----
                    with col1:
                        st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #0f5132, #198754);
                            padding: 18px;
                            border-radius: 12px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        ">
                            <div style="font-size: 1.1rem; font-weight: 600;">📈 Signaux ACHAT</div>
                            <div style="font-size: 2rem; font-weight: 700; margin-top: 5px;">{}</div>
                        </div>
                        """.format(nb_achat), unsafe_allow_html=True)

                    # ----- NEUTRE -----
                    with col2:
                        st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #6c757d, #adb5bd);
                            padding: 18px;
                            border-radius: 12px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        ">
                            <div style="font-size: 1.1rem; font-weight: 600;">⚖️ Signaux NEUTRE</div>
                            <div style="font-size: 2rem; font-weight: 700; margin-top: 5px;">{}</div>
                        </div>
                        """.format(nb_neutre), unsafe_allow_html=True)

                    # ----- VENTE -----
                    with col3:
                        st.markdown("""
                        <div style="
                            background: linear-gradient(135deg, #842029, #dc3545);
                            padding: 18px;
                            border-radius: 12px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        ">
                            <div style="font-size: 1.1rem; font-weight: 600;">📉 Signaux VENTE</div>
                            <div style="font-size: 2rem; font-weight: 700; margin-top: 5px;">{}</div>
                        </div>
                        """.format(nb_vente), unsafe_allow_html=True)

                    # ----- RISQUE GLOBAL -----
                    with col4:
                        if risk_label == "Faible":
                            bg = "linear-gradient(135deg, #0f5132, #198754)"
                            icon = "🟢"
                        elif risk_label == "Modéré":
                            bg = "linear-gradient(135deg, #664d03, #ffc107)"
                            icon = "🟡"
                        else:
                            bg = "linear-gradient(135deg, #842029, #dc3545)"
                            icon = "🔴"

                        st.markdown(f"""
                        <div style="
                            background: {bg};
                            padding: 18px;
                            border-radius: 12px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                        ">
                            <div style="font-size: 1.1rem; font-weight: 600;">{icon} Risque global</div>
                            <div style="font-size: 1.9rem; font-weight: 700; margin-top: 5px;">{risk_label}</div>
                        </div>
                        """, unsafe_allow_html=True)

                    st.markdown(f"""
                    <div style="margin-top: 1rem; font-size: 1rem; color: #555;">
                    <strong>Analyse IA :</strong> {risk_comment}<br>
                    Anomalies ML moyennes : <strong>{mean_anom*100:.1f}%</strong> — 
                    Volatilité 20j annualisée : <strong>{mean_vol*100:.0f}%</strong>
                    </div>
                    """, unsafe_allow_html=True)

                    st.markdown("---")

                    # ==========================
                    # 2) Tableau récap (index à partir de 1)
                    # ==========================
                    st.markdown("### 📊 Résumé par actif (decision-friendly)")

                    def _safe_cagr(stats):
                        if not isinstance(stats, dict):
                            return None
                        return float(stats.get("cagr", 0.0))

                    df_rep_display = pd.DataFrame(
                        {
                            "Actif": df_rep["symbol"],
                            "Prix": df_rep["price"].round(2),
                            "Var. jour %": (df_rep["last_ret"] * 100).round(2),
                            "Signal": df_rep["label"],
                            "Score": df_rep["score"].round(2),
                            "RSI(14)": df_rep["rsi"].round(1),
                            "Vol 20j ann. %": (df_rep["vol"] * 100).round(0),
                            "Anomalies (60j) %": (df_rep["anom_rate"] * 100).round(1),
                            "Tendance ann. %": df_rep["slope_pct"].round(1),
                            "CAGR SMA(20/50) %": df_rep["stats_sma"].apply(_safe_cagr).astype(float).round(1),
                            "Décision suggérée": df_rep["decision"],
                        }
                    )

                    df_to_show = df_rep_display.reset_index(drop=True)
                    df_to_show.index = df_to_show.index + 1  # index qui commence à 1
                    st.dataframe(df_to_show, use_container_width=True)

                    st.markdown(
                        "_Lecture rapide :_  \n"
                        "- **Signal** = synthèse de tendance, momentum, MACD, breakouts et volatilité.  \n"
                        "- **Décision suggérée** = phrase en français qui résume la posture : renforcer, alléger, observer…  \n"
                        "- **Tendance ann.** = pente approximative de la régression linéaire sur ~60 points.  \n"
                        "- **Anomalies (60j)** = fréquence des retours extrêmes (z-score).  \n"
                        "- **CAGR SMA(20/50)** = performance annualisée d’une stratégie de croisement de moyennes (pédagogique, pas un conseil d’investissement)."
                    )

                    st.markdown("---")

                    # ==========================
                    # 3) Focus par actif (expanders)
                    # ==========================
                    st.markdown("### 🔍 Détail lisible par actif (court / moyen terme)")

                    for r in results:
                        with st.expander(f"{r['symbol']} — détail des signaux & pistes de décision"):
                            c1, c2, c3 = st.columns(3)
                            with c1:
                                st.metric("Prix", f"{r['price']:.2f}")
                                st.metric("Variation jour", f"{r['last_ret']*100:+.2f}%")
                            with c2:
                                if r["sma_gap"] is not None:
                                    st.metric("Écart vs SMA20", f"{r['sma_gap']*100:+.2f}%")
                                if r["rsi"] is not None:
                                    st.metric("RSI(14)", f"{r['rsi']:.1f}")
                            with c3:
                                if r["vol"] is not None:
                                    st.metric("Vol 20j (ann.)", f"{r['vol']*100:.0f}%")
                                st.metric("Anomalies (60j)", f"{r['anom_rate']*100:.1f}%")

                            # Zones techniques
                            st.markdown("**Zones techniques clés :**")
                            zt = []
                            if r["ll55"] is not None:
                                zt.append(f"- Support 55 périodes ≈ **{r['ll55']:.2f}**")
                            if r["hh55"] is not None:
                                zt.append(f"- Résistance 55 périodes ≈ **{r['hh55']:.2f}**")
                            if zt:
                                st.markdown("\n".join(zt))
                            else:
                                st.markdown("_Pas de support/résistance 55 périodes disponibles._")

                            st.markdown(
                                f"\n**Signal global : {r['label']}** (score {r['score']:+.2f})  \n"
                                f"- Tendance annualisée estimée : **{r['slope_pct']:+.1f}%**  \n"
                                f"- Part du régime le plus volatil (60 derniers points) : "
                                f"**{(r['reg_risk_share'] or 0.0)*100:.1f}%**"
                            )

                            # Pistes décisionnelles
                            st.markdown("**🧭 Suggestion de décision court terme (1–5 jours)**")
                            st.markdown(f"➡️ {_decision_from_row(pd.Series(r))}")

                            st.markdown("**🎯 Piste de scénario moyen terme (1–3 mois)**")
                            st.markdown(
                                f"- Cible 1 mois (projection linéaire simple) : **{r['target_1m']:.2f}**  \n"
                                f"- Cible 3 mois (projection linéaire simple) : **{r['target_3m']:.2f}**  \n"
                                "_Ces cibles sont des extrapolations techniques simplifiées, à manier avec prudence, "
                                "uniquement à des fins pédagogiques._"
                            )

                            st.markdown("**Signaux techniques clés :**")
                            for b in r["bullets"]:
                                st.markdown(f"- {b}")

                            stats_sma = r["stats_sma"]
                            stats_bh = r["stats_bh"]
                            if isinstance(stats_sma, dict) and isinstance(stats_bh, dict):
                                st.markdown("**Backtest SMA 20/50 vs Buy & Hold (1 an) :**")
                                cb1, cb2, cb3, cb4 = st.columns(4)
                                with cb1:
                                    st.metric("CAGR SMA", f"{stats_sma.get('cagr', 0.0)*100:.1f}%")
                                with cb2:
                                    st.metric("CAGR BH", f"{stats_bh.get('cagr', 0.0)*100:.1f}%")
                                with cb3:
                                    st.metric("Sharpe SMA", f"{stats_sma.get('sharpe', 0.0):.2f}")
                                with cb4:
                                    st.metric("MaxDD SMA", f"{stats_sma.get('maxdd', 0.0)*100:.1f}%")

                    st.info(
                        "Ce rapport reste volontairement lisible : une vue globale, un tableau synthétique "
                        "avec des phrases de décision, puis un focus par actif (court terme / moyen terme) "
                        "avec zones techniques et scénarios de cibles. "
                        "Il ne constitue pas un conseil d’investissement mais un support pédagogique de lecture du marché."
                    )
                        # ===== TAB n8n : Market Radar via workflow externe =====
    # ===== TAB n8n : Market Radar via workflow externe =====
    # ===== TAB n8n : Market Radar via workflow externe =====
    with tab_n8n:
        st.markdown("### 🌐 Market Radar (via n8n)")
        st.caption(
            "Test du workflow n8n « Market Radar - IT-STORM » via le webhook `/webhook/market-radar`."
        )

        col1, col2, col3 = st.columns([3, 1, 1])
        with col1:
            symbols_input = st.text_input(
                "Universe (tickers séparés par des virgules)",
                "^FCHI, BNP.PA, AIR.PA, MC.PA, OR.PA, ORA.PA",
                key="n8n_symbols",
            )
        with col2:
            interval_input = st.selectbox(
                "Intervalle",
                ["1d", "1h"],
                index=0,
                key="n8n_interval",
            )
        with col3:
            period_input = st.selectbox(
                "Période",
                ["6mo", "1y", "2y"],
                index=1,
                key="n8n_period",
            )

        if st.button("🚀 Lancer Market Radar (n8n)", key="btn_n8n_market_radar"):
            df_radar = call_n8n_market_radar(
                symbols=symbols_input,
                interval=interval_input,
                period=period_input,
            )

            if df_radar is None or df_radar.empty:
                st.error("Impossible de récupérer les données de marché.")
            else:
                st.success("Réponse n8n reçue ✅")

                # ------------------ 🧊 Cartes de synthèse (HTML) ------------------
                n_ok = int(df_radar["error_message"].isna().sum())
                n_err = int(len(df_radar) - n_ok)

                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.markdown(
                        f"""
                        <div style="
                            background: linear-gradient(135deg,#0d6efd,#4dabf7);
                            padding: 18px;
                            border-radius: 18px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 10px 30px rgba(13,110,253,0.30);
                        ">
                            <div style="font-size:0.9rem;opacity:0.9;">🌍 Actifs total</div>
                            <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{len(df_radar)}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_b:
                    st.markdown(
                        f"""
                        <div style="
                            background: linear-gradient(135deg,#198754,#51cf66);
                            padding: 18px;
                            border-radius: 18px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 10px 30px rgba(25,135,84,0.30);
                        ">
                            <div style="font-size:0.9rem;opacity:0.9;">✅ OK (avec données)</div>
                            <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{n_ok}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )
                with col_c:
                    st.markdown(
                        f"""
                        <div style="
                            background: linear-gradient(135deg,#842029,#dc3545);
                            padding: 18px;
                            border-radius: 18px;
                            color: white;
                            text-align: center;
                            box-shadow: 0 10px 30px rgba(220,53,69,0.30);
                        ">
                            <div style="font-size:0.9rem;opacity:0.9;">⚠️ En erreur / sans données</div>
                            <div style="font-size:2.2rem;font-weight:700;margin-top:4px;">{n_err}</div>
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

                st.markdown("#### 📊 Détail brut par symbole (réponse n8n)")
                df_raw = df_radar.copy()
                df_raw.index = np.arange(1, len(df_raw) + 1)
                st.dataframe(df_raw, use_container_width=True)

                if n_err > 0:
                    st.markdown("#### ⚠️ Symboles sans données OHLCV")
                    st.write(
                        df_radar[df_radar["error_message"].notna()][
                            ["symbol", "error_status", "error_message"]
                        ].set_index("symbol")
                    )

                # ------------------ 🧠 Lecture IA rapide : enrichissement local ------------------
                ok_syms = (
                    df_radar[df_radar["error_message"].isna()]["symbol"]
                    .dropna()
                    .tolist()
                )

                enriched: list[dict] = []

                if ok_syms:
                    st.markdown("#### 🧠 Lecture IA rapide sur les actifs OK")
                    with st.spinner("Calcul des signaux techniques (indicateurs + tendance + vol)…"):
                        for sym in ok_syms:
                            data_sym = api_get(
                                f"/v1/ohlcv/{sym}",
                                interval=interval_input,
                                period=period_input,
                            )
                            if not data_sym or "candles" not in data_sym:
                                continue

                            df_sym = pd.DataFrame(data_sym["candles"])
                            df_sym = _compute_indicators(df_sym, interval=interval_input)
                            if df_sym.empty or "close" not in df_sym.columns:
                                continue

                            last = df_sym.iloc[-1]
                            price = float(last["close"])

                            rsi = (
                                float(last["rsi14"])
                                if "rsi14" in df_sym.columns and not pd.isna(last.get("rsi14", np.nan))
                                else None
                            )
                            vol = (
                                float(last["vol20"])
                                if "vol20" in df_sym.columns and not pd.isna(last.get("vol20", np.nan))
                                else None
                            )

                            reco = _score_and_reco(df_sym)
                            trend = _trend_slope_and_projection(df_sym, horizon=60)
                            slope_pct = trend[4] if trend else 0.0  # pente annualisée en %

                            # Libellés lisibles
                            if slope_pct > 5:
                                trend_label = "Haussière"
                            elif slope_pct < -5:
                                trend_label = "Baissière"
                            else:
                                trend_label = "Neutre"

                            if vol is None:
                                vol_label = "N/A"
                            elif vol < 0.15:
                                vol_label = "Calme"
                            elif vol < 0.30:
                                vol_label = "Normal"
                            else:
                                vol_label = "Tendue"

                            comment = (
                                f"{reco['label']} • tendance {trend_label.lower()} "
                                f"• volatilité {vol_label.lower()}"
                            )

                            enriched.append(
                                {
                                    "symbol": sym,
                                    "prix": round(price, 2),
                                    "signal": reco["label"],
                                    "score": round(float(reco["score"]), 2),
                                    "tendance_annuelle_%": round(float(slope_pct), 1),
                                    "vol20_annuelle_%": round(vol * 100.0, 1) if vol is not None else None,
                                    "RSI14": round(rsi, 1) if rsi is not None else None,
                                    "lecture": comment,
                                }
                            )

                if enriched:
                    df_enriched = pd.DataFrame(enriched)
                    df_enriched.index = np.arange(1, len(df_enriched) + 1)

                    # -------- Résumé global du marché --------
                    bullish = int((df_enriched["signal"] == "ACHAT").sum())
                    bearish = int((df_enriched["signal"] == "VENTE").sum())
                    neutral = int((df_enriched["signal"] == "NEUTRE").sum())

                    mean_trend = df_enriched["tendance_annuelle_%"].mean()
                    mean_vol = df_enriched["vol20_annuelle_%"].mean()

                    bias = "plutôt haussière" if bullish > bearish else (
                        "plutôt baissière" if bearish > bullish else "équilibrée"
                    )

                    st.markdown("#### 🧬 Synthèse IA globale")
                    st.markdown(
                        f"""
                        - 🟢 **{bullish}** actifs en signal **ACHAT**  
                        - 🔴 **{bearish}** actifs en signal **VENTE**  
                        - ⚪ **{neutral}** actifs en signal **NEUTRE**  

                        Le marché apparaît **{bias}**, avec une tendance moyenne de 
                        **{mean_trend:.1f} %** par an et une volatilité moyenne autour de 
                        **{mean_vol:.1f} %**.
                        """
                    )

                    # -------- Heatmap (score + tendance) --------
                    def _heat_color(val):
                        if pd.isna(val):
                            return ""
                        if val > 5:
                            return "color:#0a7d05;font-weight:600;"
                        if val < -5:
                            return "color:#b00000;font-weight:600;"
                        return "color:#b8860b;"

                    st.markdown("#### 🧾 Détail IA par symbole")
                    styled = df_enriched.style.applymap(
                        _heat_color, subset=["tendance_annuelle_%", "score"]
                    )
                    st.dataframe(styled, use_container_width=True)

                    