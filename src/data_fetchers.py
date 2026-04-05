from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Iterable

import pandas as pd
import requests

from .config import settings

TIMEOUT = 30


class FetchError(RuntimeError):
    """Raised when a remote data source cannot be fetched or parsed."""


class HttpClient:
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Accept": "application/json, text/plain;q=0.9, */*;q=0.8",
                "User-Agent": settings.sec_user_agent,
            }
        )

    def get_json(self, url: str, *, headers: dict[str, str] | None = None, params: dict[str, Any] | None = None) -> Any:
        response = self.session.get(url, headers=headers, params=params, timeout=TIMEOUT)
        if response.status_code >= 400:
            raise FetchError(f"GET {url} failed with status {response.status_code}: {response.text[:300]}")
        return response.json()


http = HttpClient()


def _coingecko_headers() -> dict[str, str]:
    if not settings.coingecko_api_key:
        raise FetchError("Missing COINGECKO_API_KEY. Create a Demo or Pro key in CoinGecko and set it in .env.")
    return {settings.coingecko_header_name: settings.coingecko_api_key}



def fetch_btc_prices(days: int) -> pd.DataFrame:
    """Fetch daily BTC/USD prices from CoinGecko."""
    url = f"{settings.coingecko_base_url}/coins/{settings.treasury_coin_id}/market_chart"
    payload = http.get_json(
        url,
        headers=_coingecko_headers(),
        params={"vs_currency": "usd", "days": days, "interval": "daily"},
    )
    prices = payload.get("prices", [])
    if not prices:
        raise FetchError("CoinGecko returned no BTC price data.")

    rows = []
    for ts_ms, price in prices:
        date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
        rows.append({"date": date, "btc_price": float(price)})

    frame = pd.DataFrame(rows).drop_duplicates(subset="date", keep="last")
    return frame.sort_values("date").reset_index(drop=True)



def fetch_mara_holdings_chart(days: int) -> pd.DataFrame:
    """Fetch MARA BTC holdings chart from CoinGecko treasury endpoint."""
    url = (
        f"{settings.coingecko_base_url}/public_treasury/"
        f"{settings.coingecko_entity_id}/{settings.treasury_coin_id}/holding_chart"
    )
    payload = http.get_json(
        url,
        headers=_coingecko_headers(),
        params={"days": days, "include_empty_intervals": "true"},
    )

    holdings = payload.get("holdings", [])
    holding_values = payload.get("holding_value_in_usd", [])
    if not holdings:
        raise FetchError("CoinGecko returned no treasury holdings chart data.")

    value_map: dict[str, float] = {}
    for ts_ms, value in holding_values:
        date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
        value_map[date] = float(value)

    rows = []
    for ts_ms, amount in holdings:
        date = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat()
        rows.append(
            {
                "date": date,
                "btc_holdings": float(amount),
                "holding_value_usd": value_map.get(date),
            }
        )

    frame = pd.DataFrame(rows).drop_duplicates(subset="date", keep="last")
    return frame.sort_values("date").reset_index(drop=True)



def fetch_mara_transactions(limit: int = 100) -> list[dict[str, Any]]:
    """Fetch recent MARA transaction history from CoinGecko treasury endpoint."""
    url = f"{settings.coingecko_base_url}/public_treasury/{settings.coingecko_entity_id}/transaction_history"
    payload = http.get_json(
        url,
        headers=_coingecko_headers(),
        params={
            "per_page": min(max(limit, 1), 250),
            "page": 1,
            "order": "date_desc",
            "coin_ids": settings.treasury_coin_id,
        },
    )
    transactions = payload.get("transactions", [])
    normalized: list[dict[str, Any]] = []
    for row in transactions:
        ts_ms = row.get("date")
        if ts_ms is None:
            continue
        normalized.append(
            {
                "date": datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc).date().isoformat(),
                "type": row.get("type"),
                "coin_id": row.get("coin_id"),
                "holding_net_change": _to_float(row.get("holding_net_change")),
                "holding_balance": _to_float(row.get("holding_balance")),
                "transaction_value_usd": _to_float(row.get("transaction_value_usd")),
                "average_entry_value_usd": _to_float(row.get("average_entry_value_usd")),
                "source_url": row.get("source_url"),
            }
        )
    return normalized



def fetch_mara_stock_prices_from_yahoo() -> pd.DataFrame:
    """Fetch daily stock prices from Yahoo Finance chart endpoint (unofficial fallback)."""
    now = int(datetime.now(tz=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{settings.alpha_vantage_symbol}"
    payload = http.get_json(
        url,
        params={
            "interval": "1d",
            "period1": 0,
            "period2": now,
            "includeAdjustedClose": "true",
            "events": "div,splits",
        },
    )
    result = (payload.get("chart", {}) or {}).get("result", [])
    if not result:
        err = (payload.get("chart", {}) or {}).get("error")
        raise FetchError(f"Yahoo Finance returned no chart data: {err}")

    result0 = result[0]
    timestamps = result0.get("timestamp") or []
    quote = ((result0.get("indicators") or {}).get("quote") or [{}])[0]
    adj = ((result0.get("indicators") or {}).get("adjclose") or [{}])[0]

    closes = quote.get("close") or []
    volumes = quote.get("volume") or []
    adjcloses = adj.get("adjclose") or []

    rows = []
    for i, ts in enumerate(timestamps):
        date = datetime.fromtimestamp(ts, tz=timezone.utc).date().isoformat()
        close = _to_float(closes[i]) if i < len(closes) else None
        adj_close = _to_float(adjcloses[i]) if i < len(adjcloses) else close
        volume = _to_float(volumes[i]) if i < len(volumes) else None
        if close is None and adj_close is None:
            continue
        rows.append(
            {
                "date": date,
                "stock_price": adj_close if adj_close is not None else close,
                "stock_close": close,
                "stock_volume": volume,
                "stock_source_function": "YAHOO_CHART_FALLBACK",
            }
        )

    if not rows:
        raise FetchError("Yahoo Finance returned an empty daily stock series.")

    frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
    return frame


def fetch_mara_stock_prices() -> pd.DataFrame:
    """Fetch daily stock prices from Alpha Vantage.

    Preference order:
    1. TIME_SERIES_DAILY_ADJUSTED (if the key has premium access)
    2. TIME_SERIES_DAILY (free fallback)
    """
    if not settings.alpha_vantage_api_key:
        raise FetchError(
            "Missing ALPHA_VANTAGE_API_KEY. Create a free Alpha Vantage key and set it in .env."
        )

    url = "https://www.alphavantage.co/query"
    functions = ["TIME_SERIES_DAILY_ADJUSTED", "TIME_SERIES_DAILY"]
    last_message = None

    for function_name in functions:
        payload = http.get_json(
            url,
            params={
                "function": function_name,
                "symbol": settings.alpha_vantage_symbol,
                "outputsize": "full",
                "apikey": settings.alpha_vantage_api_key,
            },
        )

        series = payload.get("Time Series (Daily)")
        if not series:
            last_message = payload.get("Information") or payload.get("Note") or payload.get("Error Message")
            continue

        rows = []
        for date, values in series.items():
            rows.append(
                {
                    "date": date,
                    "stock_price": _to_float(values.get("5. adjusted close") or values.get("4. close")),
                    "stock_close": _to_float(values.get("4. close")),
                    "stock_volume": _to_float(values.get("6. volume") or values.get("5. volume")),
                    "stock_source_function": function_name,
                }
            )

        frame = pd.DataFrame(rows).sort_values("date").reset_index(drop=True)
        return frame

    # Free Alpha Vantage keys are capped and often hit daily/second limits; fall back to Yahoo chart data.
    try:
        return fetch_mara_stock_prices_from_yahoo()
    except Exception as yahoo_exc:
        if last_message:
            raise FetchError(f"Alpha Vantage message: {last_message}; Yahoo fallback failed: {yahoo_exc}")
        raise FetchError(f"Alpha Vantage returned no stock price data; Yahoo fallback failed: {yahoo_exc}")



def fetch_shares_outstanding() -> pd.DataFrame:
    """Fetch sparse shares outstanding facts from SEC CompanyFacts."""
    cik = settings.sec_cik.zfill(10)
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    payload = http.get_json(url)

    dei = payload.get("facts", {}).get("dei", {})
    facts = _extract_share_facts(dei)
    if not facts:
        raise FetchError("SEC CompanyFacts did not return shares outstanding facts for MARA.")

    rows: list[dict[str, Any]] = []
    for point in facts:
        end_date = point.get("end") or point.get("fy")
        if not end_date:
            continue
        rows.append(
            {
                "date": str(end_date),
                "shares_outstanding": _to_float(point.get("val")),
                "shares_form": point.get("form"),
                "shares_filed": point.get("filed"),
            }
        )

    frame = pd.DataFrame(rows).dropna(subset=["shares_outstanding"])
    frame = frame.sort_values(["date", "shares_filed"]).drop_duplicates(subset="date", keep="last")
    return frame.reset_index(drop=True)



def _extract_share_facts(dei_facts: dict[str, Any]) -> list[dict[str, Any]]:
    candidate_tags = [
        "EntityCommonStockSharesOutstanding",
        "CommonStockSharesOutstanding",
        "EntityCommonStockSharesOutstandingEntityCommonStockAndAdditionalPaidInCapitalMember",
    ]
    for tag in candidate_tags:
        units = dei_facts.get(tag, {}).get("units", {})
        shares = units.get("shares")
        if shares:
            return list(shares)
    return []



def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(result) or math.isinf(result):
        return None
    return result
