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
import json
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
        from advisor.prompt_builder import build_followup_prompt
        from advisor.ai_engine import _call_openrouter, PRIMARY_MODEL, FALLBACK_MODEL
        
        # Explicitly tell the AI NOT to use JSON here
        system_prompt = "You are a friendly financial mentor explaining stocks to a beginner. Reply with plain conversational text only. DO NOT output JSON. DO NOT wrap your answer in brackets or braces."
        user_content = build_followup_prompt(stock_data, analysis, question)
        
        try:
            answer = _call_openrouter(FALLBACK_MODEL, system_prompt, user_content)
        except:
            answer = _call_openrouter(PRIMARY_MODEL, system_prompt, user_content)
            
        # Clean up <think> tags if Deepseek was used
        if "<think>" in answer and "</think>" in answer:
            answer = answer.split("</think>")[-1].strip()

        # --- FIX: Parse JSON if the AI still stubbornly returned it ---
        if isinstance(answer, str):
            clean_ans = answer.strip()
            if clean_ans.startswith("```json"):
                clean_ans = clean_ans.replace("```json", "").replace("```", "").strip()
                
            if clean_ans.startswith("{"):
                try:
                    parsed = json.loads(clean_ans)
                    # Extract the text, falling back through common keys
                    answer = parsed.get('response', parsed.get('answer', parsed.get('text', answer)))
                except json.JSONDecodeError:
                    pass # Not valid JSON, keep original string
        # --------------------------------------------------------------

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

        current_nav = fund_data[0]['nav'] if fund_data else "N/A"
        nav_date = fund_data[0]['date'] if fund_data else "N/A"

        # 4. NEW: Fetch rich data from Morningstar using mstarpy
        print(f"[app.py] Fetching mstarpy data for: {best_match['schemeName']}")
        mstarpy_data = fetch_mstarpy_fund_details(best_match['schemeName'])

        # 5. Format the data so the frontend and AI can understand it easily
        fund_info = {
            "symbol": str(scheme_code),
            "longName": meta.get("scheme_name", best_match['schemeName']),
            "category": mstarpy_data.get("fund_category", meta.get("scheme_category", "Mutual Fund")),
            "fundHouse": meta.get("fund_house", "Unknown"),
            "regularMarketPrice": current_nav,
            "currency": "INR",
            "navDate": nav_date,
            # NEW: Add all the mstarpy metrics
            "aum": mstarpy_data.get("aum", "N/A"),
            "expense_ratio": mstarpy_data.get("expense_ratio", "N/A"),
            "1y_return": mstarpy_data.get("1y_return", "N/A"),
            "3y_return": mstarpy_data.get("3y_return", "N/A"),
            "top_holdings": mstarpy_data.get("top_holdings", "N/A")
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
                    "INDIGO.NS", "LTIMINDTR.NS", "TECHM.NS", "BAJAJHLDNG.NS", # Replaced LTIM with LTIMINDTR
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


if __name__ == '__main__':
    # Railway typically uses the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

