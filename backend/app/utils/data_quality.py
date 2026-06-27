from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd


@dataclass
class DailyQualityResult:
    frame: pd.DataFrame
    removed_trade_dates: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def sanitize_daily_frame(df: pd.DataFrame) -> DailyQualityResult:
    """过滤真实行情与演示行情混用造成的异常K线。

    系统早期会在空库时写入演示数据，随后 AKShare/Tushare 同步真实数据。
    如果真实同步只覆盖交易日或只覆盖最新快照，演示行可能残留在节假日或历史段里，
    形成 10 元跳到 90 元再跳回 10 元这类不可能的走势。这里优先保留成交额量级更可信
    的真实行情，并移除价格/成交额量级明显不一致的行。
    """

    if df.empty or len(df) < 3:
        return DailyQualityResult(frame=df.copy())

    data = df.sort_values("trade_date").copy()
    for column in ["open", "high", "low", "close", "pre_close", "change", "pct_chg", "vol", "amount"]:
        if column in data.columns:
            data[column] = pd.to_numeric(data[column], errors="coerce")

    close = data["close"].dropna()
    if close.empty:
        return DailyQualityResult(frame=data)

    positive_close = close[close > 0]
    if positive_close.empty:
        return DailyQualityResult(frame=data)

    median_close = float(positive_close.median())
    amount = data["amount"].fillna(0).astype(float) if "amount" in data.columns else pd.Series(0.0, index=data.index)
    positive_amount = amount[amount > 0]
    median_amount = float(positive_amount.median()) if not positive_amount.empty else 0.0
    upper_amount = float(positive_amount.quantile(0.75)) if not positive_amount.empty else 0.0

    remove_mask = pd.Series(False, index=data.index)

    # 最新快照成交额远大于历史段时，历史段大概率是演示K线，优先保留最新真实快照。
    latest = data.iloc[-1]
    latest_close = float(latest.get("close") or 0)
    latest_amount = float(latest.get("amount") or 0)
    if (
        median_close > 0
        and median_amount > 0
        and latest_close > median_close * 4
        and latest_amount > median_amount * 50
    ):
        remove_mask |= amount < latest_amount / 300

    price_outlier = (data["close"] > median_close * 4) | (data["close"] < median_close / 4)
    if upper_amount > 0:
        remove_mask |= price_outlier & (amount < upper_amount / 20)
    else:
        remove_mask |= price_outlier

    # 连续前后价格都跳变且成交额量级明显偏低的点，也按污染点处理。
    previous_close = data["close"].shift(1)
    reported_pre_close = data["pre_close"].fillna(0).astype(float) if "pre_close" in data.columns else pd.Series(0.0, index=data.index)
    pct_chg = data["pct_chg"].fillna(0).astype(float).abs() if "pct_chg" in data.columns else pd.Series(0.0, index=data.index)
    pre_close_ratio = previous_close / reported_pre_close.replace(0, pd.NA)
    pre_close_ratio = pre_close_ratio.replace([float("inf"), float("-inf")], pd.NA)
    trade_dates = pd.to_datetime(data["trade_date"].astype(str), format="%Y%m%d", errors="coerce")
    date_gap_days = (trade_dates - trade_dates.shift(1)).dt.days.abs()
    scale_break = ((pre_close_ratio > 1.25) | (pre_close_ratio < 0.8)) & (pct_chg < 35) & (date_gap_days <= 10)
    break_indices = data.index[scale_break.fillna(False)].tolist()
    for break_index in break_indices:
        position = data.index.get_loc(break_index)
        before_index = data.index[:position]
        after_index = data.index[position:]
        if len(before_index) == 0 or len(after_index) == 0:
            continue
        before_amount = float(amount.loc[before_index].replace(0, pd.NA).dropna().median() or 0)
        after_amount = float(amount.loc[after_index].replace(0, pd.NA).dropna().median() or 0)
        if len(after_index) <= 5:
            remove_mask.loc[after_index] = True
        elif len(before_index) <= 5 and after_amount > 0 and before_amount > after_amount * 20:
            remove_mask.loc[before_index] = True
        elif before_amount > 0 and after_amount > before_amount * 100:
            remove_mask.loc[after_index[:1]] = True
        elif after_amount > 0 and before_amount > after_amount * 100:
            remove_mask.loc[before_index[-1:]] = True
        else:
            remove_mask.loc[break_index] = True

    next_close = data["close"].shift(-1)
    jump_from_prev = (data["close"] / previous_close.replace(0, pd.NA)).abs()
    jump_to_next = (data["close"] / next_close.replace(0, pd.NA)).abs()
    isolated_jump = ((jump_from_prev > 3) | (jump_from_prev < 1 / 3)) & ((jump_to_next > 3) | (jump_to_next < 1 / 3))
    if upper_amount > 0:
        remove_mask |= isolated_jump.fillna(False) & (amount < upper_amount / 20)

    removed_dates = [str(value) for value in data.loc[remove_mask, "trade_date"].tolist()]
    cleaned = data.loc[~remove_mask].copy()
    warnings: list[str] = []
    if removed_dates:
        warnings.append(f"已过滤 {len(removed_dates)} 条疑似演示/异常K线：{', '.join(removed_dates[:8])}{'...' if len(removed_dates) > 8 else ''}")
    return DailyQualityResult(frame=cleaned, removed_trade_dates=removed_dates, warnings=warnings)
