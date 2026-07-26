"""
portfolio_engine.py
Manages portfolio holdings stored in a Google Sheet, using a service-account
credential loaded from an environment variable (matches existing infra pattern).

Expected Google Sheet columns (row 1 headers):
Symbol | Exchange | Quantity | Buy_Price | Buy_Date
"""

import os
import json
import gspread
from google.oauth2.service_account import Credentials

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

# ---------- Config via environment variables ----------
GOOGLE_SHEET_ID = os.getenv("PORTFOLIO_SHEET_ID")           # the Sheet's ID from its URL
GOOGLE_SHEET_TAB = os.getenv("PORTFOLIO_SHEET_TAB", "Holdings")
SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")  # full JSON as a string

REQUIRED_COLUMNS = ["Symbol", "Exchange", "Quantity", "Buy_Price", "Buy_Date"]


def _get_client():
    if not SERVICE_ACCOUNT_JSON:
        raise EnvironmentError(
            "GOOGLE_SERVICE_ACCOUNT_JSON environment variable is not set."
        )
    creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_worksheet():
    if not GOOGLE_SHEET_ID:
        raise EnvironmentError("PORTFOLIO_SHEET_ID environment variable is not set.")
    client = _get_client()
    sheet = client.open_by_key(GOOGLE_SHEET_ID)
    return sheet.worksheet(GOOGLE_SHEET_TAB)


def get_holdings() -> list:
    """
    Returns list of dicts, e.g.:
    [{"symbol": "TCS", "exchange": "NSE", "quantity": 5, "buy_price": 3500, "buy_date": "2024-01-15"}]
    """
    ws = _get_worksheet()
    records = ws.get_all_records()  # uses row 1 as headers

    holdings = []
    for row in records:
        if not row.get("Symbol"):
            continue
        holdings.append({
            "symbol": str(row.get("Symbol", "")).strip().upper(),
            "exchange": str(row.get("Exchange", "NSE")).strip().upper(),
            "quantity": _to_number(row.get("Quantity")),
            "buy_price": _to_number(row.get("Buy_Price")),
            "buy_date": row.get("Buy_Date", ""),
        })
    return holdings


def add_holding(symbol: str, exchange: str, quantity: float, buy_price: float, buy_date: str) -> dict:
    ws = _get_worksheet()
    ws.append_row([symbol.upper(), exchange.upper(), quantity, buy_price, buy_date])
    return {"status": "success", "message": f"Added {symbol.upper()} to portfolio."}


def update_holding(symbol: str, updates: dict) -> dict:
    """
    updates: dict of fields to change, e.g. {"quantity": 15, "buy_price": 3600}
    Updates the FIRST matching row for that symbol.
    """
    ws = _get_worksheet()
    all_rows = ws.get_all_records()
    headers = ws.row_values(1)

    for idx, row in enumerate(all_rows, start=2):  # row 1 = headers
        if str(row.get("Symbol", "")).strip().upper() == symbol.upper():
            for field, value in updates.items():
                col_name = field.capitalize() if field != "buy_price" else "Buy_Price"
                if col_name in headers:
                    col_idx = headers.index(col_name) + 1
                    ws.update_cell(idx, col_idx, value)
            return {"status": "success", "message": f"Updated {symbol.upper()}."}

    return {"status": "error", "message": f"{symbol.upper()} not found in portfolio."}


def remove_holding(symbol: str) -> dict:
    ws = _get_worksheet()
    all_rows = ws.get_all_records()

    for idx, row in enumerate(all_rows, start=2):
        if str(row.get("Symbol", "")).strip().upper() == symbol.upper():
            ws.delete_rows(idx)
            return {"status": "success", "message": f"Removed {symbol.upper()} from portfolio."}

    return {"status": "error", "message": f"{symbol.upper()} not found in portfolio."}


def _to_number(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
