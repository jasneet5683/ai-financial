"""
stock_analyzer.py
Fetches and structures live stock data for Indian (NSE/BSE) and global tickers
using yfinance, with in-memory caching and safe fallbacks.
"""

import yfinance as yf
import time
from datetime import datetime
import pandas as pd

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
def get_stock_data(symbol: str, exchange: str = "NSE", period: str = "1y") -> dict:
    """
    Returns structured stock data for a given symbol.
    Fetches historical prices and Nifty 50 (via NIFTYBEES ETF) safely.
    """
    ticker_symbol = resolve_ticker(symbol, exchange)
    cache_key = f"{ticker_symbol}_{period}"

    cached = _get_cached(cache_key)
    if cached:
        return cached

    try:
        # 1. Fetch Stock Data
        stock = yf.Ticker(ticker_symbol)
        info = stock.info or {}
        hist = stock.history(period=period)

        # 2. Fetch Nifty 50 Data using an ETF for reliability (NIFTYBEES)
        nifty = yf.Ticker("NIFTYBEES.NS")
        nifty_hist = nifty.history(period=period)

        nifty_map = {}
        if not nifty_hist.empty and "Close" in nifty_hist:
            for date, row in nifty_hist.iterrows():
                nifty_map[date.strftime('%Y-%m-%d')] = round(float(row["Close"]), 2)
            print(f"✅ Nifty ETF fetched successfully: {len(nifty_map)} days of data.")
        else:
            print("❌ WARNING: Failed to fetch Nifty ETF data from yfinance.")

        dates = []
        prices = []
        benchmark_prices = []
        price_change_pct = None

        if not hist.empty and "Close" in hist:
            for date, row in hist.iterrows():
                d_str = date.strftime('%Y-%m-%d')
                dates.append(d_str)
                
                # Add Stock Price
                s_price = round(float(row["Close"]), 2)
                prices.append(s_price)
                
                # Add matching Nifty ETF Price (or None if missing)
                benchmark_prices.append(nifty_map.get(d_str, None))

            if len(prices) > 1 and prices[0] and prices[-1]:
                price_change_pct = round(((prices[-1] - prices[0]) / prices[0]) * 100, 2)

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
            
            # Chart Data:
            "dates": dates,
            "prices": prices,
            "benchmark_prices": benchmark_prices,
            
            "fetched_at": datetime.now().isoformat(),
        }

        _set_cache(cache_key, data)
        return data

    except Exception as e:
        import traceback
        print("Error fetching stock:", traceback.format_exc())
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
