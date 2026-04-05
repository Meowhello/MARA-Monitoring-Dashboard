from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from .config import settings
from .data_fetchers import (
    FetchError,
    fetch_btc_prices,
    fetch_mara_holdings_chart,
    fetch_mara_stock_prices,
    fetch_mara_transactions,
    fetch_shares_outstanding,
)


@dataclass(slots=True)
class BuildResult:
    output_path: Path
    generated_at: str
    row_count: int



def build_dashboard_payload(days: int | None = None) -> dict[str, Any]:
    days = days or settings.date_range_days
    today = datetime.now(timezone.utc).date()
    start_date = today - timedelta(days=days)

    btc_df = fetch_btc_prices(days)
    holdings_df = fetch_mara_holdings_chart(days)
    stock_df = fetch_mara_stock_prices()
    shares_sparse_df = fetch_shares_outstanding()
    transactions = fetch_mara_transactions(limit=100)

    calendar = pd.DataFrame(
        {
            "date": pd.date_range(start=start_date, end=today, freq="D").strftime("%Y-%m-%d")
        }
    )

    stock_df = stock_df[stock_df["date"] >= str(start_date)].copy()
    shares_sparse_df = shares_sparse_df[shares_sparse_df["date"] >= str(start_date - timedelta(days=120))].copy()

    merged = calendar.merge(btc_df, on="date", how="left")
    merged = merged.merge(holdings_df[["date", "btc_holdings", "holding_value_usd"]], on="date", how="left")
    merged = merged.merge(stock_df[["date", "stock_price", "stock_close", "stock_volume"]], on="date", how="left")
    merged = merged.merge(shares_sparse_df[["date", "shares_outstanding"]], on="date", how="left")

    merged = merged.sort_values("date").reset_index(drop=True)
    for column in ["btc_price", "btc_holdings", "holding_value_usd", "stock_price", "stock_close", "stock_volume", "shares_outstanding"]:
        merged[column] = pd.to_numeric(merged[column], errors="coerce")

    merged["btc_price"] = merged["btc_price"].ffill()
    merged["btc_holdings"] = merged["btc_holdings"].ffill()
    merged["holding_value_usd"] = merged["holding_value_usd"].ffill()
    merged["stock_price"] = merged["stock_price"].ffill()
    merged["stock_close"] = merged["stock_close"].ffill()
    merged["stock_volume"] = merged["stock_volume"].fillna(0)
    merged["shares_outstanding"] = merged["shares_outstanding"].ffill()

    merged["total_asset_value"] = merged["btc_holdings"] * merged["btc_price"]
    merged["realized_mnav"] = (merged["shares_outstanding"] * merged["stock_price"]) / merged["total_asset_value"]
    merged["btc_per_share"] = merged["btc_holdings"] / merged["shares_outstanding"]

    merged["market_cap_proxy"] = merged["shares_outstanding"] * merged["stock_price"]

    for base_col, out_col in [
        ("stock_price", "stock_price_pct"),
        ("btc_price", "btc_price_pct"),
        ("btc_holdings", "btc_holdings_pct"),
        ("shares_outstanding", "shares_outstanding_pct"),
        ("realized_mnav", "realized_mnav_pct"),
    ]:
        merged[out_col] = merged[base_col].pct_change() * 100

    # Approximate log-change decomposition: d ln(mNAV) ≈ d ln(stock) + d ln(shares) - d ln(BTC price) - d ln(holdings)
    merged["contrib_stock_price"] = _log_pct_change(merged["stock_price"])
    merged["contrib_shares"] = _log_pct_change(merged["shares_outstanding"])
    merged["contrib_btc_price"] = -_log_pct_change(merged["btc_price"])
    merged["contrib_btc_holdings"] = -_log_pct_change(merged["btc_holdings"])
    merged["contrib_total"] = (
        merged["contrib_stock_price"]
        + merged["contrib_shares"]
        + merged["contrib_btc_price"]
        + merged["contrib_btc_holdings"]
    )

    valid = merged.dropna(subset=["realized_mnav", "stock_price", "btc_price", "btc_holdings", "shares_outstanding"]).copy()
    if valid.empty:
        raise FetchError("Merged dataset is empty after alignment. Please check the remote APIs and date window.")

    latest = valid.iloc[-1]
    last_7 = valid.iloc[-8] if len(valid) >= 8 else valid.iloc[0]
    last_30 = valid.iloc[-31] if len(valid) >= 31 else valid.iloc[0]

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "company": {
            "name": settings.company_name,
            "symbol": settings.company_symbol,
            "coin": settings.treasury_coin_id,
            "coingecko_entity_id": settings.coingecko_entity_id,
            "sec_cik": settings.sec_cik,
        },
        "methodology": {
            "indicator": "Realized mNAV",
            "formula": "(shares_outstanding * stock_price) / (btc_holdings * btc_price)",
            "notes": [
                "本網站以公開資料自行重建 MARA 的 realized mNAV，而非直接依賴付費 DAT API。",
                "公式為：股價 × 股數 ÷（BTC 持幣量 × BTC 價格）；其中 BTC 資產價值近似為 BTC 持幣量乘以 BTC 價格。",
                "BTC 持幣量與 treasury 事件來自 CoinGecko Public Treasury 資料。",
                "BTC 價格來自 CoinGecko market chart；MARA 股價優先使用 Alpha Vantage，若受免費額度限制則改用 Yahoo Finance 備援。",
                "股數資料來自 SEC CompanyFacts，因屬申報資料，所以會以申報日為節點並在區間內前向填補。",
                "因此，股數／稀釋因子通常呈現階梯狀，而非每天連續變動。",
            ],
        },
        "date_range": {
            "start": valid["date"].iloc[0],
            "end": valid["date"].iloc[-1],
            "days": int(days),
        },
        "latest": {
            "date": latest["date"],
            "realized_mnav": _safe_round(latest["realized_mnav"], 4),
            "stock_price": _safe_round(latest["stock_price"], 4),
            "btc_price": _safe_round(latest["btc_price"], 2),
            "btc_holdings": _safe_round(latest["btc_holdings"], 4),
            "shares_outstanding": _safe_round(latest["shares_outstanding"], 0),
            "total_asset_value": _safe_round(latest["total_asset_value"], 2),
            "btc_per_share": _safe_round(latest["btc_per_share"], 8),
            "market_cap_proxy": _safe_round(latest["market_cap_proxy"], 2),
            "mnav_change_7d_pct": _pct_change(latest["realized_mnav"], last_7["realized_mnav"]),
            "mnav_change_30d_pct": _pct_change(latest["realized_mnav"], last_30["realized_mnav"]),
        },
        "quick_summary": build_rule_based_summary(valid),
        "transactions": transactions[:20],
        "series": _records_for_json(valid),
        "sources": [
            {
                "name": "CoinGecko Public Treasury Entity Chart",
                "purpose": "MARA BTC holdings over time",
            },
            {
                "name": "CoinGecko Coins Market Chart",
                "purpose": "BTC/USD daily prices",
            },
            {
                "name": "Alpha Vantage / Yahoo Finance",
                "purpose": "MARA daily stock prices",
            },
            {
                "name": "SEC CompanyFacts",
                "purpose": "Shares outstanding facts",
            },
        ],
    }
    return payload



def save_dashboard_payload(payload: dict[str, Any], output_path: Path | None = None) -> BuildResult:
    output_path = output_path or settings.dashboard_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    sanitized = _sanitize_for_json(payload)
    with output_path.open("w", encoding="utf-8") as fh:
        json.dump(sanitized, fh, ensure_ascii=False, indent=2, allow_nan=False)
    return BuildResult(output_path=output_path, generated_at=sanitized["generated_at"], row_count=len(sanitized["series"]))



def run_pipeline(days: int | None = None, output_path: Path | None = None) -> BuildResult:
    payload = build_dashboard_payload(days=days)
    return save_dashboard_payload(payload, output_path=output_path)



def load_dashboard_payload(path: Path | None = None) -> dict[str, Any]:
    path = path or settings.dashboard_path
    if not path.exists():
        raise FileNotFoundError(path)
    with path.open("r", encoding="utf-8") as fh:
        return _sanitize_for_json(json.load(fh))



def build_rule_based_summary(frame: pd.DataFrame) -> list[str]:
    latest = frame.iloc[-1]
    lookback_7 = frame.iloc[-8] if len(frame) >= 8 else frame.iloc[0]
    lookback_30 = frame.iloc[-31] if len(frame) >= 31 else frame.iloc[0]

    mnav_7d = _pct_change(latest["realized_mnav"], lookback_7["realized_mnav"])
    mnav_30d = _pct_change(latest["realized_mnav"], lookback_30["realized_mnav"])
    stock_30d = _pct_change(latest["stock_price"], lookback_30["stock_price"])
    btc_30d = _pct_change(latest["btc_price"], lookback_30["btc_price"])

    contribution_cols = {
        "股價": "contrib_stock_price",
        "股數/稀釋": "contrib_shares",
        "BTC 價格": "contrib_btc_price",
        "BTC 持幣量": "contrib_btc_holdings",
    }
    recent = frame.tail(7)
    avg_contrib = {
        label: recent[col].dropna().mean() if col in recent else np.nan
        for label, col in contribution_cols.items()
    }
    valid_contrib = {k: v for k, v in avg_contrib.items() if not pd.isna(v)}
    dominant_name, dominant_value = (max(valid_contrib.items(), key=lambda item: abs(item[1])) if valid_contrib else ("無", 0.0))

    trend_7d = "上升" if mnav_7d >= 0 else "下降"
    trend_30d = "上升" if mnav_30d >= 0 else "下降"

    messages = [
        f"目前 MARA 的 realized mNAV 為 {latest['realized_mnav']:.2f}；近 7 天約 {trend_7d} {abs(mnav_7d):.2f}%，近 30 天約 {trend_30d} {abs(mnav_30d):.2f}%。",
        f"近 30 天 MARA 股價變動約 {stock_30d:+.2f}%，BTC 價格變動約 {btc_30d:+.2f}%。",
        f"為避免單日缺值干擾，下方柱狀圖改看最近 7 天平均貢獻；目前影響最大的因子是「{dominant_name}」，平均近似貢獻約 {dominant_value:+.2f}%。",
        "此摘要為規則式自動生成：根據近 7 天、30 天變化與四因子平均貢獻套用固定句型，並非 LLM 生成。",
    ]
    return messages



def _records_for_json(frame: pd.DataFrame) -> list[dict[str, Any]]:
    records = frame.to_dict(orient="records")
    cleaned = []
    for row in records:
        cleaned.append({key: _sanitize_scalar(value, digits=8) for key, value in row.items()})
    return cleaned


def _sanitize_scalar(value: Any, digits: int | None = None) -> Any:
    if value is None or pd.isna(value):
        return None
    if isinstance(value, (np.integer, int)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        value = float(value)
        if pd.isna(value) or np.isinf(value):
            return None
        return round(value, digits) if digits is not None else value
    return value


def _sanitize_for_json(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _sanitize_for_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_sanitize_for_json(v) for v in value]
    return _sanitize_scalar(value)


def _log_pct_change(series: pd.Series) -> pd.Series:
    values = series.where(series > 0)
    ratio = values / values.shift(1)
    return ratio.apply(lambda x: pd.NA if pd.isna(x) or x <= 0 else np.log(x) * 100)



def _pct_change(current: float, previous: float) -> float:
    if previous in (None, 0) or pd.isna(previous) or pd.isna(current):
        return 0.0
    return round(((current / previous) - 1) * 100, 4)



def _safe_round(value: Any, digits: int) -> Any:
    sanitized = _sanitize_scalar(value, digits=None)
    if sanitized is None:
        return None
    if digits == 0:
        return int(round(float(sanitized)))
    return round(float(sanitized), digits)
