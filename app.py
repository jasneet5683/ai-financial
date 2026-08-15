"""
app.py
Main entry point for AI-finance. 
Handles routes for stock lookup and portfolio analysis.
"""

import os
import csv
import io
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
from flask_cors import CORS
import traceback
import requests 
import json
from rapidfuzz import process, fuzz
import jwt
import bcrypt
import os
from datetime import datetime, timedelta, timezone
from functools import wraps


# Load environment variables from .env
load_dotenv()

from advisor.stock_analyzer import get_stock_data, get_portfolio_data
#from advisor.portfolio_engine import get_holdings, add_holding
from advisor.ai_engine import analyze_stock, analyze_portfolio, chat_market_advisor, analyze_portfolio
from advisor.portfolio_sheets import get_equity_holdings, get_fund_holdings, log_portfolio_view


app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app)

import math

@app.after_request
def fix_nan(response):
    if response.content_type == 'application/json':
        fixed = response.get_data(as_text=True)
        fixed = fixed.replace('NaN', 'null').replace('Infinity', 'null').replace('-Infinity', 'null')
        response.set_data(fixed)
    return response


#==== Search Function =========
# ── NSE Symbol Map (loaded once at startup) ──────────────
_NSE_MAP   = {}   # { "INFOSYS LTD": "INFY" }
_NSE_NAMES = []   # for fuzzy search

def load_nse_symbols():
    global _NSE_MAP, _NSE_NAMES
    try:
        url = "https://archives.nseindia.com/content/equities/EQUITY_L.csv"
        resp = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.com"},
            timeout=15
        )
        reader = csv.DictReader(io.StringIO(resp.text))
        for row in reader:
            name   = row['NAME OF COMPANY'].strip().upper()
            symbol = row['SYMBOL'].strip().upper()
            _NSE_MAP[name] = symbol
        _NSE_NAMES = list(_NSE_MAP.keys())
        print(f"NSE symbols loaded: {len(_NSE_NAMES)}")
    except Exception as e:
        print(f"NSE load failed: {e}")


def resolve_company_to_symbol(query: str, exchange: str) -> str:
    """
    Resolves any company name or partial name to its NSE/BSE symbol.
    Priority: exact symbol → fuzzy NSE list → Yahoo Finance → as typed
    """
    query_upper = query.strip().upper()

    # 1. Already a valid symbol
    if query_upper in _NSE_MAP.values():
        return query_upper

    # 2. Fuzzy match on full NSE list
    if _NSE_NAMES:
        match, score, _ = process.extractOne(
            query_upper, _NSE_NAMES, scorer=fuzz.WRatio
        )
        if score >= 70:
            resolved = _NSE_MAP[match]
            print(f"Resolved '{query}' → '{resolved}' (matched '{match}', score={score})")
            return resolved

    # 3. Yahoo Finance fallback
    try:
        suffix = ".NS" if exchange == "NSE" else ".BO"
        url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
        resp = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        quotes = resp.json().get('quotes', [])
        for q in quotes:
            sym = q.get('symbol', '')
            if sym.endswith(suffix):
                return sym.replace(suffix, "")
        for q in quotes:
            sym = q.get('symbol', '')
            if sym.endswith('.NS') or sym.endswith('.BO'):
                return sym[:-3]
    except Exception as e:
        print(f"Yahoo fallback failed: {e}")

    # 4. Last resort
    return query_upper

# Load NSE symbol list once at startup
with app.app_context():
    load_nse_symbols()

# ── Portfolio Auth Setup ──────────────────────────────────
_RAW_PASSWORD = os.environ.get('PORTFOLIO_PASSWORD', '').encode('utf-8')
_HASHED_PASSWORD = bcrypt.hashpw(_RAW_PASSWORD, bcrypt.gensalt()) if _RAW_PASSWORD else None
_JWT_SECRET = os.environ.get('JWT_SECRET', 'fallback-secret-change-me')
_JWT_EXPIRY_DAYS = 7

def verify_portfolio_token(f):
    """Decorator to protect portfolio endpoints with JWT."""
    @wraps(f)
    def decorated(*args, **kwargs):
        token = request.headers.get('Authorization', '').replace('Bearer ', '')
        if not token:
            return jsonify({"error": "Unauthorized"}), 401
        try:
            jwt.decode(token, _JWT_SECRET, algorithms=['HS256'])
        except jwt.ExpiredSignatureError:
            return jsonify({"error": "Session expired"}), 401
        except jwt.InvalidTokenError:
            return jsonify({"error": "Invalid token"}), 401
        return f(*args, **kwargs)
    return decorated


# --- WEB ROUTES ---

@app.route('/')
def index():
    """Serves the main frontend interface from repo root."""
    return send_from_directory('.', 'index.html')

# --- API ENDPOINTS ---

@app.route('/api/search-stocks', methods=['GET'])
def search_stocks():
    query = request.args.get('q', '').strip().upper()
    if not query or len(query) < 2:
        return jsonify([])

    if not _NSE_NAMES:
        return jsonify([])

    results = process.extract(query, _NSE_NAMES, scorer=fuzz.WRatio, limit=8)

    suggestions = []
    for match, score, _ in results:
        if score >= 50:
            suggestions.append({
                "name": match.title(),         # "Infosys Ltd"
                "symbol": _NSE_MAP[match]       # "INFY"
            })

    return jsonify(suggestions)


@app.route('/api/analyze-stock', methods=['POST', 'OPTIONS'])
def api_analyze_stock():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    data = request.json
    raw_symbol = data.get('symbol', '').strip()
    exchange = data.get('exchange', 'NSE')
    question = data.get('question', '')

    # ✅ Resolve company name to actual stock symbol
    symbol = resolve_company_to_symbol(raw_symbol, exchange)


    if not symbol:
        return jsonify({"error": "Symbol is required"}), 400

    # Format the symbol based on the exchange (for Yahoo Finance)
    if exchange == 'NSE':
        yf_symbol = f"{symbol}.NS"
    elif exchange == 'BSE':
        yf_symbol = f"{symbol}.BO"
    else:
        yf_symbol = symbol

    try:
        import yfinance as yf
        from advisor.ai_engine import analyze_stock
        
        # 1. Initialize the stock object
        stock = yf.Ticker(yf_symbol)
        stock_info = stock.info
        
        if 'longName' not in stock_info and 'shortName' not in stock_info:
            return jsonify({"error": f"Could not find data for {yf_symbol}"}), 404

        # 2. Fetch 1-year historical data for the chart
        hist = stock.history(period="1y")
        
        # Fetch Nifty 50 benchmark data
        nifty = yf.Ticker("^NSEI")
        nifty_hist = nifty.history(period="1y")
        
        # Build a date -> price map for Nifty
        nifty_map = {}
        if not nifty_hist.empty:
            for date, row in nifty_hist.iterrows():
                nifty_map[date.strftime('%Y-%m-%d')] = round(float(row["Close"]), 2)
        
        # If ^NSEI failed, try ETF fallback
        if not nifty_map:
            nifty2 = yf.Ticker("NIFTYBEES.NS")
            nifty2_hist = nifty2.history(period="1y")
            if not nifty2_hist.empty:
                for date, row in nifty2_hist.iterrows():
                    nifty_map[date.strftime('%Y-%m-%d')] = round(float(row["Close"]), 2)

        chart_data = {"dates": [], "prices": [], "benchmark_prices": []}
        if not hist.empty:
            chart_data["dates"] = [d.strftime('%Y-%m-%d') for d in hist.index]
            chart_data["prices"] = hist['Close'].tolist()
            # Match Nifty price to each stock date
            chart_data["benchmark_prices"] = [
                nifty_map.get(d, None) for d in chart_data["dates"]
            ]

        # 3. MAP THE DATA (This is what was missing! Convert Yahoo keys to our keys)
        current_price = stock_info.get('currentPrice', stock_info.get('regularMarketPrice', 0))
        prev_close = stock_info.get('previousClose', stock_info.get('regularMarketPreviousClose', current_price))
        day_change = round(((current_price - prev_close) / prev_close) * 100, 2) if prev_close and prev_close > 0 else 0

        mapped_stock_data = {
            "ticker": yf_symbol,
            "company_name": stock_info.get('longName', stock_info.get('shortName', symbol)),
            "current_price": current_price,
            "currency": stock_info.get('currency', 'INR' if exchange in ['NSE', 'BSE'] else 'USD'),
            "day_change_pct": day_change,
            "pe_ratio": stock_info.get('trailingPE', stock_info.get('forwardPE', 'N/A')),
            "eps": stock_info.get('trailingEps', stock_info.get('forwardEps', 'N/A')),
            "market_cap": stock_info.get('marketCap', 'N/A'),
            "52_week_high": stock_info.get('fiftyTwoWeekHigh', 'N/A'),
            "52_week_low": stock_info.get('fiftyTwoWeekLow', 'N/A')
        }

        # 4. Run AI Analysis using the MAPPED data
        analysis = analyze_stock(mapped_stock_data, question)
        
        if "error" in analysis:
            return jsonify(analysis), 500

        # 5. Return everything to the frontend
        response = jsonify({
            "stock_data": mapped_stock_data, 
            "chart_data": chart_data,
            "analysis": analysis
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500
     
@app.route('/api/portfolio-auth', methods=['POST', 'OPTIONS'])
def portfolio_auth():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    if not _HASHED_PASSWORD:
        return jsonify({"error": "Portfolio auth not configured"}), 500

    data = request.json or {}
    password = data.get('password', '').encode('utf-8')

    if not bcrypt.checkpw(password, _HASHED_PASSWORD):
        return jsonify({"error": "Invalid password"}), 401

    token = jwt.encode(
        {
            "sub": "portfolio",
            "iat": datetime.now(timezone.utc),
            "exp": datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRY_DAYS)
        },
        _JWT_SECRET,
        algorithm='HS256'
    )
    return jsonify({"token": token}), 200

@app.route('/api/analyze-portfolio', methods=['POST'])
@verify_portfolio_token          
def api_analyze_portfolio():
    """
    Analyzes the entire portfolio from Google Sheets.
    JSON input: { "question": "optional" }
    """
    data = request.json or {}
    user_question = data.get('question')

    try:
        # 1. Get holdings from Google Sheet
        equity = get_equity_holdings()
        funds  = get_fund_holdings()
        # Normalize equity keys
        equity_normalized = [
            {
                "symbol":    h["symbol"],
                "exchange":  h.get("broker", "NSE"),   # use broker as exchange hint, default NSE
                "quantity":  h["quantity"],
                "buy_price": h["purchase_price"],       # ← key rename
            }
            for h in equity
        ]

        # Normalize funds — use Fund_Name as symbol, no exchange
        funds_normalized = [
            {
                "symbol":    f["fund_name"],            # ← funds have no ticker
                "exchange":  "MF",
                "quantity":  f.get("units_purchased"),
                "buy_price": f.get("amount_invested"),
            }
            for f in funds
        ]

        holdings = equity_normalized + funds_normalized
        
        if not holdings:
            return jsonify({"message": "Portfolio is empty. Add stocks to your Google Sheet first."}), 200

        # 2. Get live data and P&L for all holdings
        portfolio_live_data = get_portfolio_data(holdings)

        # 3. Get AI Analysis
        analysis = analyze_portfolio(portfolio_live_data, user_question)

        return jsonify({
            "portfolio_data": portfolio_live_data,
            "analysis": analysis
        })
    except Exception as e:
        traceback.print_exc() 
        return jsonify({"error": str(e)}), 500

@app.route('/api/add-stock', methods=['POST'])
@verify_portfolio_token       
def api_add_stock():
    """
    Adds a new stock to the Google Sheet.
    JSON input: { "symbol": "INFY", "exchange": "NSE", "quantity": 10, "buy_price": 1500, "buy_date": "2024-07-29" }
    """
    data = request.json
    try:
        res = add_holding(
            symbol=data['symbol'],
            exchange=data.get('exchange', 'NSE'),
            quantity=data['quantity'],
            buy_price=data['buy_price'],
            buy_date=data.get('buy_date', '')
        )
        return jsonify(res)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/portfolio-login', methods=['POST', 'OPTIONS'])
def portfolio_login():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    if not _HASHED_PASSWORD:
        return jsonify({"error": "Portfolio password not configured"}), 500

    data = request.json or {}
    password = data.get('password', '').encode('utf-8')

    if bcrypt.checkpw(password, _HASHED_PASSWORD):
        token = jwt.encode({
            'sub': 'jasneet',
            'exp': datetime.now(timezone.utc) + timedelta(days=_JWT_EXPIRY_DAYS)
        }, _JWT_SECRET, algorithm='HS256')
        return jsonify({"token": token})
    else:
        return jsonify({"error": "Incorrect password"}), 401


@app.route('/api/portfolio-logout', methods=['POST'])
def portfolio_logout():
    # JWT is stateless — client just deletes the token
    return jsonify({"message": "Logged out"})


@app.route("/api/portfolio-data", methods=["GET"])
def portfolio_data():
    try:
        equity = get_equity_holdings()
        funds = get_fund_holdings()
        log_portfolio_view("All")
        return jsonify({
            "status": "success",
            "equity": equity,
            "mutual_funds": funds
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500

@app.route('/api/ask-stock-question', methods=['POST', 'OPTIONS'])
def api_ask_stock_question():
    """
    Handles follow-up questions about a stock after the initial analysis.
    JSON input: { "stock_data": {...}, "analysis": {...}, "question": "What if a recession hits?" }
    """
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    data = request.json
    stock_data = data.get('stock_data')
    analysis = data.get('analysis')
    question = data.get('question')

    if not question:
        return jsonify({"error": "Question is required"}), 400

    try:
        from advisor.prompt_builder import build_followup_prompt
        import json
        import requests
        import os
        
        system_prompt = "You are a friendly financial mentor explaining stocks to a beginner. Reply with plain conversational text only. DO NOT output JSON. DO NOT wrap your answer in brackets or braces."
        user_content = build_followup_prompt(stock_data, analysis, question)
        
        OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
        if not OPENROUTER_API_KEY:
            return jsonify({"error": "Missing OpenRouter API key"}), 500

        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "model": "openrouter/free",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content}
            ]
        }
        
        r = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=30)
        r.raise_for_status()
        result = r.json()
        answer = result['choices'][0]['message']['content']

        # Clean up <think> tags if Deepseek was used
        if "<think>" in answer and "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        # Parse JSON if the AI still stubbornly returned it
        if isinstance(answer, str):
            clean_ans = answer.strip()
            if clean_ans.startswith("```json"):
                clean_ans = clean_ans.replace("```json", "").replace("```", "").strip()
                
            if clean_ans.startswith("{"):
                try:
                    parsed = json.loads(clean_ans)
                    answer = parsed.get('response', parsed.get('answer', parsed.get('text', answer)))
                except json.JSONDecodeError:
                    pass

        response = jsonify({"answer": answer})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


@app.route('/api/analyze-fund', methods=['POST', 'OPTIONS'])
def api_analyze_fund():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    data = request.json
    search_query = data.get('ticker', '').strip() 
    question = data.get('question', '')

    if not search_query:
        return jsonify({"error": "Fund name is required"}), 400

    try:
        import requests
        from advisor.ai_engine import analyze_mutual_fund
        from advisor.mf_data_fetcher import fetch_mstarpy_fund_details  # NEW IMPORT
        
        # 1. Search the official Indian Mutual Fund API (MFAPI) for NAV
        search_url = f"https://api.mfapi.in/mf/search?q={requests.utils.quote(search_query)}"
        search_res = requests.get(search_url).json()

        if not search_res or len(search_res) == 0:
            return jsonify({"error": f"Could not find any Indian Mutual Fund matching '{search_query}'. Try checking the spelling."}), 404

        # 2. Try to find the "Direct" and "Growth" variant, otherwise just take the first result
        best_match = search_res[0]
        for item in search_res:
            name_lower = item['schemeName'].lower()
            if 'direct' in name_lower and 'growth' in name_lower:
                best_match = item
                break

        # 3. Fetch the latest details and NAV (Price) for this specific fund
        scheme_code = best_match['schemeCode']
        detail_url = f"https://api.mfapi.in/mf/{scheme_code}"
        detail_res = requests.get(detail_url).json()

        meta = detail_res.get("meta", {})
        fund_data = detail_res.get("data", [])

        # --- Format 1-year historical data for the chart ---
        chart_data = {"dates": [], "prices": []}
        if fund_data:
            history_subset = fund_data[:250]
            history_subset.reverse()
            for item in history_subset:
                chart_data["dates"].append(item['date'])
                chart_data["prices"].append(float(item['nav']))

        # --- Format 1-year historical data for the chart ---
        chart_data = {"dates": [], "prices": []}
        if fund_data:
            history_subset = fund_data[:250]
            history_subset.reverse()
            for item in history_subset:
                chart_data["dates"].append(item['date'])
                chart_data["prices"].append(float(item['nav']))

        current_nav = fund_data[0]['nav'] if fund_data else "N/A"
        nav_date = fund_data[0]['date'] if fund_data else "N/A"

        # --- NEW: Fetch Nifty 50 Benchmark Data for Comparison ---
        import yfinance as yf
        import pandas as pd
        try:
            # Fetch 1 year of Nifty 50 data (^NSEI)
            nifty = yf.download('^NSEI', period='1y', progress=False)
            
            nifty_dict = {}
            if not nifty.empty:
                for idx, row in nifty.iterrows():
                    date_str = idx.strftime('%d-%m-%Y')
                    # Handle yfinance multi-index/series variations safely
                    close_val = row['Close']
                    if isinstance(close_val, pd.Series):
                        close_val = close_val.iloc[0]
                    nifty_dict[date_str] = float(close_val)
            
            chart_data["benchmark_prices"] = []
            last_known_nifty = None
            
            # Align Nifty prices with the exact dates the Mutual Fund traded
            for d in chart_data["dates"]:
                if d in nifty_dict:
                    last_known_nifty = nifty_dict[d]
                chart_data["benchmark_prices"].append(last_known_nifty)

        except Exception as e:
            print(f"Failed to fetch Nifty 50 data: {e}")
            chart_data["benchmark_prices"] = [None] * len(chart_data["dates"])

        # 4. NEW: Fetch rich data from Morningstar using mstarpy
        print(f"[app.py] Fetching mstarpy data for: {best_match['schemeName']}")
        #mstarpy_data = fetch_mstarpy_fund_details(best_match['schemeName'])
        mstarpy_data = fetch_mstarpy_fund_details(best_match['schemeName'], scheme_code)

        # 5. Format the data so the frontend and AI can understand it easily
        fund_info = {
            "symbol": str(scheme_code),
            "longName": meta.get("scheme_name", best_match['schemeName']),
            "category": mstarpy_data.get("fund_category", meta.get("scheme_category", "Mutual Fund")),
            "fundHouse": meta.get("fund_house", "Unknown"),
            "regularMarketPrice": current_nav,
            "currency": "INR",
            "navDate": nav_date,
            
            # This passes all our calculated returns and DDG search snippets directly to the prompt!
            "raw_search_text": mstarpy_data.get("raw_search_text", ""),
            
            # (Required by prompt_builder.py)
            "fund_name": meta.get("scheme_name", best_match['schemeName']),
            "fund_category": mstarpy_data.get("fund_category", meta.get("scheme_category", "Mutual Fund")),
            "fund_house": meta.get("fund_house", "Unknown")
        }

        # 6. Run AI Analysis
        analysis = analyze_mutual_fund(fund_info, question)
        
        if "error" in analysis:
            return jsonify(analysis), 500

        response = jsonify({
            "stock_data": fund_info, 
            "chart_data": chart_data,
            "analysis": analysis
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-movers', methods=['POST', 'OPTIONS'])
def api_market_movers():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    try:
        import yfinance as yf
        
        # Get the sector from the request (default to NIFTY_50)
        data = request.get_json() or {}
        sector = data.get('sector', 'NIFTY_50')
        
        # Define all sectors with their stock symbols
        sectors_data = {
            'NIFTY_50': {
                'name': 'NIFTY 50',
                'symbols': [
                    "RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "ICICIBANK.NS", "INFY.NS",
                    "SBIN.NS", "BHARTIARTL.NS", "ITC.NS", "LT.NS", "TMPV.NS", # Replaced TATAMOTORS with TMPV
                    "SUNPHARMA.NS", "MARUTI.NS", "TATASTEEL.NS", "BAJFINANCE.NS", "AXISBANK.NS",
                    "M&M.NS", "ASIANPAINT.NS", "HCLTECH.NS", "NTPC.NS", "KOTAKBANK.NS",
                    "WIPRO.NS", "ONGC.NS", "POWERGRID.NS", "HINDUNILVR.NS", "ADANIENT.NS",
                    "BAJAJFINSV.NS", "JSWSTEEL.NS", "BPCL.NS", "GAIL.NS", "ULTRACEMCO.NS",
                    "BRITANNIA.NS", "NESTLEIND.NS", "DIVISLAB.NS", "CIPLA.NS", "DRREDDY.NS",
                    "EICHERMOT.NS", "HEROMOTOCO.NS", "BOSCHLTD.NS", "TITAN.NS", "SBICARD.NS", # Replaced BOSCHIND with BOSCHLTD
                    "INDIGO.NS", "LTM.NS", "TECHM.NS", "BAJAJHLDNG.NS", # Replaced LTIM with LTIMINDTR
                    "IDFCFIRSTB.NS", "APOLLOHOSP.NS", "BIOCON.NS", "SIEMENS.NS", "LUPIN.NS" # Replaced IDFCBANK with IDFCFIRSTB, SIEMENSIND with SIEMENS
                ]
            },
            'PETRO': {
                'name': 'Petroleum & Energy',
                'symbols': [
                    "RELIANCE.NS", "ONGC.NS", "BPCL.NS", "HINDPETRO.NS", "IOC.NS", # Replaced HPCL with HINDPETRO
                    "GAIL.NS", "NTPC.NS", "POWERGRID.NS", "DLF.NS", "ADANIGREEN.NS",
                    "ADANIPOWER.NS", "TORNTPHARM.NS", "CUMMINSIND.NS", "ABB.NS", "SIEMENS.NS",
                    "BHEL.NS", "SJVN.NS", "NHPC.NS", "NHPC.NS" # Replaced NATIONALHYDRO with NHPC
                ]
            },
            'PHARMA': {
                'name': 'Pharmaceuticals',
                'symbols': [
                    "SUNPHARMA.NS", "CIPLA.NS", "DRREDDY.NS", "LUPIN.NS", "DIVISLAB.NS",
                    "BIOCON.NS", "TORNTPHARM.NS", "AUROPHARMA.NS", "ZYDUSLIFE.NS",
                    "APOLLOHOSP.NS", "FORTIS.NS", "MAXHEALTH.NS", "PFIZER.NS",
                    "GLAXO.NS", "LAURUSLABS.NS", "MANKIND.NS", "NATCOPHARM.NS" # Cleaned up various pharma names
                ]
            },
            'AI_TECH': {
                'name': 'AI & Tech',
                'symbols': [
                    "TCS.NS", "INFY.NS", "WIPRO.NS", "HCLTECH.NS", "LTIMINDTR.NS",
                    "TECHM.NS", "MPHASIS.NS", "PERSISTENT.NS", "COFORGE.NS",
                    "KPITTECH.NS", "NAUKRI.NS", "ZOMATO.NS",
                    "PAYTM.NS", "ZENTEC.NS" # Removed unrecognised/delisted AI/Tech stocks
                ]
            },
            'GREEN_ENERGY': {
                'name': 'Green Energy',
                'symbols': [
                    "ADANIGREEN.NS", "ADANIPOWER.NS", "NTPC.NS", "POWERGRID.NS", "NHPC.NS",
                    "SJVN.NS", "RELIANCE.NS", "SIEMENS.NS",
                    "ABB.NS", "SUZLON.NS", "RENUKA.NS", "TATAPOWER.NS",
                    "CUMMINSIND.NS", "EXIDEIND.NS", "GENSOL.NS", "MOIL.NS"
                ]
            },
            'FINANCE': {
                'name': 'Banking & Finance',
                'symbols': [
                    "HDFCBANK.NS", "ICICIBANK.NS", "SBIN.NS", "AXISBANK.NS", "KOTAKBANK.NS",
                    "IDFCFIRSTB.NS", "INDUSINDBK.NS", "YESBANK.NS", "FEDERALBNK.NS", # Replaced INDUSIND with INDUSINDBK
                    "ICICIPRULI.NS", "BAJAJFINSV.NS", "BAJFINANCE.NS", "LT.NS", "SBICARD.NS",
                    "SBILIFE.NS", "MUTHOOTFIN.NS", "MANAPPURAM.NS", "CHOLAFIN.NS", "MOTILALOFS.NS"
                ]
            },
            'FINTECH': {
                'name': 'FinTech & Payments',
                'symbols': [
                    "PAYTM.NS", "NYKAA.NS", "ZOMATO.NS", "POLICYBZR.NS",
                    "SBICARD.NS", "ICICIBANK.NS", "HDFCBANK.NS", "AXISBANK.NS", "INDIGO.NS",
                    "BHARTIARTL.NS", "ZEEL.NS", "OFSS.NS", "SHRIRAMFIN.NS", # Replaced SRTRANSFIN with SHRIRAMFIN
                    "IDFCFIRSTB.NS", "YESBANK.NS", "FEDERALBNK.NS", "INDIANB.NS"
                ]
            }
        }

        
        # Get the stocks for the selected sector
        if sector not in sectors_data:
            return jsonify({"error": f"Unknown sector: {sector}"}), 400
        
        sector_info = sectors_data[sector]
        symbols = sector_info['symbols']
        
        tickers = yf.Tickers(" ".join(symbols))
        movers = []
        
        for sym in symbols:
            try:
                info = tickers.tickers[sym].info
                
                current_price = info.get('currentPrice', info.get('regularMarketPrice'))
                prev_close = info.get('previousClose', info.get('regularMarketPreviousClose'))
                short_name = info.get('shortName', sym.replace('.NS', ''))
                
                if current_price and prev_close:
                    change_pct = ((current_price - prev_close) / prev_close) * 100
                    movers.append({
                        "symbol": sym.replace(".NS", ""),
                        "name": short_name,
                        "price": round(current_price, 2),
                        "change": round(change_pct, 2)
                    })
            except Exception:
                continue
        
        if not movers:
            return jsonify({"error": "No market data available for this sector"}), 404
            
        # Sort by percentage change
        movers.sort(key=lambda x: x["change"], reverse=True)
        
        # Get top 5 Gainers and top 5 Losers
        gainers = movers[:5]
        losers = movers[-5:]
        losers.sort(key=lambda x: x["change"])
        
        response = jsonify({
            "sector": sector_info['name'],
            "gainers": gainers,
            "losers": losers
        })
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500

@app.route('/api/market-ticker', methods=['GET'])
def market_ticker():
    try:
        import yfinance as yf

        indices = [
            {"label": "NIFTY 50",    "ticker": "^NSEI"},
            {"label": "SENSEX",      "ticker": "^BSESN"},
            {"label": "BANK NIFTY",  "ticker": "^NSEBANK"},
            {"label": "NIFTY IT",    "ticker": "^CNXIT"},
        ]

        result = []
        for idx in indices:
            try:
                t = yf.Ticker(idx["ticker"])
                hist = t.history(period="2d")

                if len(hist) >= 2:
                    prev_close = round(float(hist["Close"].iloc[-2]), 2)
                    closing    = round(float(hist["Close"].iloc[-1]), 2)
                elif len(hist) == 1:
                    prev_close = round(float(hist["Close"].iloc[0]), 2)
                    closing    = prev_close
                else:
                    continue

                change     = round(closing - prev_close, 2)
                change_pct = round((change / prev_close) * 100, 2) if prev_close else 0

                if change_pct >= 1.5:
                    emoji = "🎉"
                elif change_pct >= 0:
                    emoji = "😊"
                elif change_pct >= -1.5:
                    emoji = "😟"
                else:
                    emoji = "😢"

                result.append({
                    "label":      idx["label"],
                    "closing":    closing,
                    "change":     change,
                    "change_pct": change_pct,
                    "emoji":      emoji,
                    "direction":  "up" if change >= 0 else "down"
                })
            except Exception as e:
                print(f"Ticker fetch failed for {idx['label']}: {str(e)}")
                continue

        response = jsonify({"indices": result})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/api/market-advisor', methods=['POST'])
def market_advisor():
    try:
        data = request.get_json()
        messages = data.get('messages', [])

        if not messages:
            return jsonify({"error": "No messages provided"}), 400

        result = chat_market_advisor(messages)
        return jsonify(result)

    except Exception as e:
        print(f"Market advisor error: {str(e)}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    # Railway typically uses the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

