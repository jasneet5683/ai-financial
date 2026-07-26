"""
stock_analyzer.py
Fetches and structures live stock data for Indian (NSE/BSE) and global tickers
using yfinance, with in-memory caching and safe fallbacks.
"""

import yfinance as yf
import time
from datetime import datetime


# ---------- Simple in-memory cache (avoids Yahoo rate-limiting) ----------
_cache = {}
CACHE_TTL_SECONDS = 600  # 10 minutes


def _get_cached(key):
    entry = _cache.get(key)
    if entry and (time.time() - entry["timestamp"] < CACHE_TTL_SECONDS):
        return entry["data"]
    return None


def _set_cache(key, data):
    _cache[key] = {"data": data, "timestamp": time.time()}


# ---------- Ticker resolution for Indian markets ----------
def resolve_ticker(symbol: str, exchange: str = "NSE") -> str:
    """
    Adds the correct suffix for Indian tickers if not already present.
    exchange: "NSE" or "BSE"
    """
    symbol = symbol.strip().upper()
    if symbol.endswith(".NS") or symbol.endswith(".BO"):
        return symbol
    # If it already looks like a US ticker (no dot), leave as-is unless exchange forces India
    if exchange.upper() == "BSE":
        return f"{symbol}.BO"
    return f"{symbol}.NS"  # default to NSE for Indian context


# ---------- Safe field extractor ----------
def _safe_get(info: dict, key: str, default="Not available"):
    value = info.get(key)
    if value is None or value == "":
        return default
    return value


# ---------- Core function ----------
def get_stock_data(symbol: str, exchange: str = "NSE", period: str = "6mo") -> dict:
    """
    Returns structured stock data for a given symbol.
    Falls back gracefully if any field is missing.
    """
    ticker_symbol = resolve_ticker(symbol, exchange)
    cache_key = f"{ticker_symbol}_{period}"

    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        stock = yf.Ticker(ticker_symbol)
        info = stock.info or {}
        hist = stock.history(period=period)

        # Price trend summary
        price_change_pct = None
        if not hist.empty and len(hist) > 1:
            start_price = hist["Close"].iloc[0]
            end_price = hist["Close"].iloc[-1]
            if start_price:
                price_change_pct = round(((end_price - start_price) / start_price) * 100, 2)

        data = {
            "ticker": ticker_symbol,
            "company_name": _safe_get(info, "longName", symbol),
            "sector": _safe_get(info, "sector"),
            "industry": _safe_get(info, "industry"),
            "current_price": _safe_get(info, "currentPrice"),
            "currency": _safe_get(info, "currency", "INR"),
            "day_change_pct": _safe_get(info, "regularMarketChangePercent"),
            "volume": _safe_get(info, "volume"),
            "market_cap": _safe_get(info, "marketCap"),
            "pe_ratio": _safe_get(info, "trailingPE"),
            "forward_pe": _safe_get(info, "forwardPE"),
            "eps": _safe_get(info, "trailingEps"),
            "dividend_yield": _safe_get(info, "dividendYield"),
            "beta": _safe_get(info, "beta"),
            "52_week_high": _safe_get(info, "fiftyTwoWeekHigh"),
            "52_week_low": _safe_get(info, "fiftyTwoWeekLow"),
            "analyst_target_price": _safe_get(info, "targetMeanPrice"),
            "recommendation": _safe_get(info, "recommendationKey"),
            "revenue_growth": _safe_get(info, "revenueGrowth"),
            "profit_margins": _safe_get(info, "profitMargins"),
            "period_price_change_pct": price_change_pct if price_change_pct is not None else "Not available",
            "fetched_at": datetime.now().isoformat(),
        }

        _set_cache(cache_key, data)
        return data

    except Exception as e:
        return {
            "ticker": ticker_symbol,
            "error": f"Failed to fetch data: {str(e)}",
            "fetched_at": datetime.now().isoformat(),
        }


# ---------- Batch fetch for portfolio analysis ----------
def get_portfolio_data(holdings: list) -> list:
    """
    holdings: list of dicts like
    [{"symbol": "RELIANCE", "quantity": 10, "buy_price": 2400, "exchange": "NSE"}, ...]

    Returns list of dicts with live data + P&L merged in.
    """
    results = []
    for h in holdings:
        stock_data = get_stock_data(
            symbol=h["symbol"],
            exchange=h.get("exchange", "NSE")
        )

        # Add P&L calculation if price is available
        current_price = stock_data.get("current_price")
        if isinstance(current_price, (int, float)) and h.get("buy_price") and h.get("quantity"):
            invested = h["buy_price"] * h["quantity"]
            current_value = current_price * h["quantity"]
            pnl = round(current_value - invested, 2)
            pnl_pct = round((pnl / invested) * 100, 2) if invested else None
            stock_data.update({
                "quantity": h["quantity"],
                "buy_price": h["buy_price"],
                "invested_value": invested,
                "current_value": round(current_value, 2),
                "pnl": pnl,
                "pnl_pct": pnl_pct,
            })
        else:
            stock_data.update({
                "quantity": h.get("quantity"),
                "buy_price": h.get("buy_price"),
                "pnl": "Not available",
            })

        results.append(stock_data)

    return results


# ---------- Quick test (remove/comment out in production) ----------
if __name__ == "__main__":
    print(get_stock_data("RELIANCE"))
    print(get_portfolio_data([
        {"symbol": "TCS", "quantity": 5, "buy_price": 3500, "exchange": "NSE"},
        {"symbol": "INFY", "quantity": 10, "buy_price": 1400, "exchange": "NSE"},
    ]))
