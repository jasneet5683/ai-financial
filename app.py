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

@app.route('/api/analyze-stock', methods=['POST'])
def api_analyze_stock():
    """
    Analyzes a specific stock.
    JSON input: { "symbol": "TCS", "exchange": "NSE", "question": "optional" }
    """
    try:
        data = request.json
        raw_input = data.get('symbol') # The user might type "Tata Motors"
        exchange = data.get('exchange', 'NSE')
        user_question = data.get('question')

        if not raw_input:
            return jsonify({"error": "Company name or symbol is required"}), 400

    # MAGIC HAPPENS HERE: Convert company name to exact symbol
        symbol = resolve_company_to_symbol(raw_input, exchange)
        print(f"Resolved user input '{raw_input}' to symbol '{symbol}'")


        if not symbol:
            return jsonify({"error": "Stock symbol is required"}), 400

        # 1. Fetch live data
        stock_live_data = get_stock_data(symbol, exchange)
        
        if "error" in stock_live_data:
            return jsonify(stock_live_data), 500

        # 2. Get AI Analysis
        analysis = analyze_stock(stock_live_data, user_question)
        
        return jsonify({
            "stock_data": stock_live_data,
            "analysis": analysis
        })
    except Exception as e:
        # Get the full error trace
        error_details = traceback.format_exc()
        print(error_details) # This prints to Railway logs
        
        # Send the exact error back to the frontend
        return jsonify({
            "error": "Server crashed. See details below.",
            "details": str(e),
            "traceback": error_details 
        }), 500
     
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
            "analysis": analysis
        })
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

