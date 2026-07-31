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

# Load environment variables from .env
load_dotenv()

from advisor.stock_analyzer import get_stock_data, get_portfolio_data
from advisor.portfolio_engine import get_holdings, add_holding
from advisor.ai_engine import analyze_stock, analyze_portfolio

app = Flask(__name__, static_folder='.', static_url_path='')
CORS(app) 

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
        symbol = data.get('symbol')
        exchange = data.get('exchange', 'NSE')
        user_question = data.get('question')

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

if __name__ == '__main__':
    # Railway typically uses the PORT environment variable
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)

