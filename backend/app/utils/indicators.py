from __future__ import annotations

import numpy as np
import pandas as pd


def clamp(value: float | None, minimum: float = 0, maximum: float = 100) -> float:
    if value is None or np.isnan(value):
        return 0
    return float(max(minimum, min(maximum, value)))


def normalize_series(series: pd.Series, inverse: bool = False) -> pd.Series:
    """把一列指标归一化到0-100，inverse用于PE/PB/负债率等越低越好的指标。"""
    clean = pd.to_numeric(series, errors="coerce")
    if clean.notna().sum() == 0:
        return pd.Series(50.0, index=series.index)
    low = clean.quantile(0.02)
    high = clean.quantile(0.98)
    if high == low:
        return pd.Series(50.0, index=series.index)
    score = (clean.clip(low, high) - low) / (high - low) * 100
    if inverse:
        score = 100 - score
    return score.fillna(50).astype(float)


def add_technical_indicators(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    data = df.sort_values("trade_date").copy()
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    volume = data["vol"].astype(float)

    for window in [5, 10, 20, 60, 120]:
        data[f"ma{window}"] = close.rolling(window, min_periods=1).mean()
        data[f"pct_chg_{window}"] = close.pct_change(window) * 100

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    data["macd_dif"] = ema12 - ema26
    data["macd_dea"] = data["macd_dif"].ewm(span=9, adjust=False).mean()
    data["macd"] = (data["macd_dif"] - data["macd_dea"]) * 2
    data["macd_cross"] = np.where(
        (data["macd_dif"] > data["macd_dea"]) & (data["macd_dif"].shift(1) <= data["macd_dea"].shift(1)),
        "golden",
        np.where(
            (data["macd_dif"] < data["macd_dea"]) & (data["macd_dif"].shift(1) >= data["macd_dea"].shift(1)),
            "dead",
            "",
        ),
    )

    low_n = low.rolling(9, min_periods=1).min()
    high_n = high.rolling(9, min_periods=1).max()
    rsv = (close - low_n) / (high_n - low_n).replace(0, np.nan) * 100
    data["kdj_k"] = rsv.ewm(com=2, adjust=False).mean().fillna(50)
    data["kdj_d"] = data["kdj_k"].ewm(com=2, adjust=False).mean().fillna(50)
    data["kdj_j"] = 3 * data["kdj_k"] - 2 * data["kdj_d"]
    data["kdj_cross"] = np.where(
        (data["kdj_k"] > data["kdj_d"]) & (data["kdj_k"].shift(1) <= data["kdj_d"].shift(1)),
        "golden",
        np.where(
            (data["kdj_k"] < data["kdj_d"]) & (data["kdj_k"].shift(1) >= data["kdj_d"].shift(1)),
            "dead",
            "",
        ),
    )

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14, min_periods=1).mean()
    loss = (-delta.clip(upper=0)).rolling(14, min_periods=1).mean()
    rs = gain / loss.replace(0, np.nan)
    data["rsi"] = (100 - 100 / (1 + rs)).fillna(50)

    mid = close.rolling(20, min_periods=1).mean()
    std = close.rolling(20, min_periods=1).std().fillna(0)
    data["boll_mid"] = mid
    data["boll_upper"] = mid + 2 * std
    data["boll_lower"] = mid - 2 * std

    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(axis=1)
    data["atr"] = tr.rolling(14, min_periods=1).mean()

    data["volume_ma5"] = volume.rolling(5, min_periods=1).mean()
    data["volume_ratio_calc"] = volume / data["volume_ma5"].replace(0, np.nan)
    data["amplitude"] = (high - low) / close.replace(0, np.nan) * 100
    data["breakout_20"] = close >= high.shift(1).rolling(20, min_periods=1).max()
    data["limit_up"] = data["pct_chg"].fillna(0) >= 9.8
    return data


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        number = float(value)
        if np.isnan(number):
            return default
        return number
    except (TypeError, ValueError):
        return default
