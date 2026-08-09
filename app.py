"""
app.py
Main entry point for AI-finance. 
Handles routes for stock lookup and portfolio analysis.
"""

import os
from flask import Flask, request, jsonify, send_from_directory
from dotenv import load_dotenv
#from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
#from dotenv import load_dotenv
import traceback # Add this at the top with your other imports
import requests 
# Load environment variables from .env
load_dotenv()

from advisor.stock_analyzer import get_stock_data, get_portfolio_data
from advisor.portfolio_engine import get_holdings, add_holding
from advisor.ai_engine import analyze_stock, analyze_portfolio

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app) 


#==== Search Function =========

def resolve_company_to_symbol(query: str, exchange: str) -> str:
    """
    Takes a company name (e.g., "Tata Motors") and returns its stock symbol (e.g., "TATAMOTORS").
    Uses Yahoo Finance's public search API.
    """
    # If the user typed a short symbol with no spaces, assume it's already a symbol
    if len(query) <= 15 and " " not in query:
        # We will still search just in case, but keep the original as fallback
        pass 

    url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}"
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(url, headers=headers, timeout=5)
        data = response.json()
        quotes = data.get('quotes', [])
        
        if not quotes:
            return query.upper() # Fallback to what the user typed
            
        suffix = ".NS" if exchange == "NSE" else ".BO"
        
        # 1. Look for a matching stock on the requested Indian exchange
        for quote in quotes:
            sym = quote.get('symbol', '')
            if sym.endswith(suffix):
                return sym.replace(suffix, "") # Return just the base symbol (e.g., "TATAMOTORS")
                
        # 2. If no exact exchange match, just return the first result's symbol
        best_match = quotes[0].get('symbol', '')
        if best_match.endswith('.NS') or best_match.endswith('.BO'):
            return best_match[:-3]
            
        return best_match

    except Exception as e:
        print(f"Search API failed: {e}")
        return query.upper() # Fallback to what the user typed if search fails


# --- WEB ROUTES ---

@app.route('/')
def index():
    """Serves the main frontend interface from repo root."""
    return send_from_directory('.', 'index.html')

# --- API ENDPOINTS ---

@app.route('/api/analyze-stock', methods=['POST', 'OPTIONS'])
def api_analyze_stock():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'POST,OPTIONS')
        return response, 204

    data = request.json
    symbol = data.get('symbol', '').strip().upper()
    exchange = data.get('exchange', 'NSE')
    question = data.get('question', '')

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
        chart_data = {"dates": [], "prices": []}
        if not hist.empty:
            chart_data["dates"] = [d.strftime('%Y-%m-%d') for d in hist.index]
            chart_data["prices"] = hist['Close'].tolist()

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
     
@app.route('/api/analyze-portfolio', methods=['POST'])
def api_analyze_portfolio():
    """
    Analyzes the entire portfolio from Google Sheets.
    JSON input: { "question": "optional" }
    """
    data = request.json or {}
    user_question = data.get('question')

    try:
        # 1. Get holdings from Google Sheet
        holdings = get_holdings()
        
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
        return jsonify({"error": str(e)}), 500

@app.route('/api/add-stock', methods=['POST'])
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
        # We need a new prompt for follow-up questions
        from advisor.prompt_builder import build_followup_prompt
        from advisor.ai_engine import _call_openrouter, PRIMARY_MODEL, FALLBACK_MODEL
        
        system_prompt = "You are a friendly financial mentor explaining stocks to a beginner."
        user_content = build_followup_prompt(stock_data, analysis, question)
        
        # We don't need JSON here, just a plain text answer.
        # We'll use Mistral directly for faster chat responses.
        try:
            answer = _call_openrouter(FALLBACK_MODEL, system_prompt, user_content)
        except:
            # Fallback to Deepseek if Mistral fails
            answer = _call_openrouter(PRIMARY_MODEL, system_prompt, user_content)
            
        # Clean up <think> tags if Deepseek was used
        if "<think>" in answer and "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        response = jsonify({"answer": answer})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
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
    # The user is now sending a plain text search query, not a ticker
    search_query = data.get('ticker', '').strip() 
    question = data.get('question', '')

    if not search_query:
        return jsonify({"error": "Fund name is required"}), 400

    try:
        import requests
        from advisor.ai_engine import analyze_mutual_fund
        
        # 1. Search the official Indian Mutual Fund API (MFAPI)
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

        # --- NEW: Format 1-year historical data for the chart ---
        chart_data = {"dates": [], "prices": []}
        if fund_data:
            # The API returns newest first. Take the last ~250 trading days (1 year) and reverse it
            history_subset = fund_data[:250]
            history_subset.reverse()
            for item in history_subset:
                chart_data["dates"].append(item['date'])
                # Convert NAV string to float
                chart_data["prices"].append(float(item['nav']))

        current_nav = fund_data[0]['nav'] if fund_data else "N/A"
        nav_date = fund_data[0]['date'] if fund_data else "N/A"

        # 4. Format the data so the frontend and AI can understand it easily
        fund_info = {
            "symbol": str(scheme_code),
            "longName": meta.get("scheme_name", best_match['schemeName']),
            "category": meta.get("scheme_category", "Mutual Fund"),
            "fundHouse": meta.get("fund_house", "Unknown"),
            "regularMarketPrice": current_nav,
            "currency": "INR",
            "navDate": nav_date,
            "note_to_ai": "This is an Indian Mutual Fund. Please use your internal knowledge to estimate the Expense Ratio, AUM, and Top Holdings for this specific fund name."
        }

        # 5. Run AI Analysis
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

@app.route('/api/market-movers', methods=['GET', 'OPTIONS'])
def api_market_movers():
    if request.method == 'OPTIONS':
        response = jsonify({})
        response.headers.add('Access-Control-Allow-Origin', '*')
        response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
        response.headers.add('Access-Control-Allow-Methods', 'GET,OPTIONS')
        return response, 204

    try:
        import yfinance as yf
        import requests

        # Yahoo Finance provides a hidden API for market movers. 
        # We will use the Indian market (scrIds: day_gainers_in, day_losers_in)
        headers = {'User-Agent': 'Mozilla/5.0'}
        
        # Fetch Gainers
        gainers_url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-IN&region=IN&scrIds=day_gainers_in&count=5"
        g_res = requests.get(gainers_url, headers=headers).json()
        
        gainers = []
        if 'finance' in g_res and 'result' in g_res['finance'] and len(g_res['finance']['result']) > 0:
            quotes = g_res['finance']['result'][0].get('quotes', [])
            for q in quotes:
                gainers.append({
                    "symbol": q.get('symbol', '').replace('.NS', '').replace('.BO', ''),
                    "price": q.get('regularMarketPrice', {}).get('fmt', '0'),
                    "change_pct": q.get('regularMarketChangePercent', {}).get('fmt', '0%'),
                    "raw_pct": q.get('regularMarketChangePercent', {}).get('raw', 0)
                })

        # Fetch Losers
        losers_url = "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-IN&region=IN&scrIds=day_losers_in&count=5"
        l_res = requests.get(losers_url, headers=headers).json()
        
        losers = []
        if 'finance' in l_res and 'result' in l_res['finance'] and len(l_res['finance']['result']) > 0:
            quotes = l_res['finance']['result'][0].get('quotes', [])
            for q in quotes:
                losers.append({
                    "symbol": q.get('symbol', '').replace('.NS', '').replace('.BO', ''),
                    "price": q.get('regularMarketPrice', {}).get('fmt', '0'),
                    "change_pct": q.get('regularMarketChangePercent', {}).get('fmt', '0%'),
                    "raw_pct": q.get('regularMarketChangePercent', {}).get('raw', 0)
                })

        # Fallback if Yahoo API fails/is empty for India currently
        if not gainers:
            gainers = [
                {"symbol": "RELIANCE", "price": "2950", "change_pct": "+2.5%", "raw_pct": 2.5},
                {"symbol": "TCS", "price": "4100", "change_pct": "+1.8%", "raw_pct": 1.8},
                {"symbol": "INFY", "price": "1650", "change_pct": "+1.2%", "raw_pct": 1.2}
            ]
        if not losers:
            losers = [
                {"symbol": "HDFCBANK", "price": "1420", "change_pct": "-1.5%", "raw_pct": -1.5},
                {"symbol": "WIPRO", "price": "480", "change_pct": "-2.1%", "raw_pct": -2.1},
                {"symbol": "ITC", "price": "410", "change_pct": "-0.8%", "raw_pct": -0.8}
            ]

        response = jsonify({"gainers": gainers, "losers": losers})
        response.headers.add('Access-Control-Allow-Origin', '*')
        return response

    except Exception as e:
        import traceback
        print(traceback.format_exc())
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    # Railway typically uses the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

