"""
portfolio_sheets.py
Reads Equity and MutualFunds tabs from the Portfolio Google Sheet.
Uses the same service-account pattern as portfolio_engine.py.

Expected Sheet: 'Portfolio' (separate from Task_Manager / Holdings sheet)
Tabs:
  - Equity
  - MutualFunds
  - AuditLog
"""

import os
import json
from datetime import datetime, timezone
import gspread
from google.oauth2.service_account import Credentials

# ── Config ────────────────────────────────────────────────
SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
]

SERVICE_ACCOUNT_JSON   = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON")
PORTFOLIO_SHEET_ID     = os.getenv("PORTFOLIO_NEW_SHEET_ID")   # new Portfolio sheet ID

TAB_EQUITY      = "Equity"
TAB_FUNDS       = "MutualFunds"
TAB_AUDIT       = "AuditLog"


# ── Internal helpers ──────────────────────────────────────
def _get_client():
    if not SERVICE_ACCOUNT_JSON:
        raise EnvironmentError("GOOGLE_SERVICE_ACCOUNT_JSON is not set.")
    creds_dict = json.loads(SERVICE_ACCOUNT_JSON)
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(creds)


def _get_sheet():
    if not PORTFOLIO_SHEET_ID:
        raise EnvironmentError("PORTFOLIO_NEW_SHEET_ID is not set.")
    client = _get_client()
    return client.open_by_key(PORTFOLIO_SHEET_ID)


def _to_float(value):
    try:
        return float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


def _to_int(value):
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ── Equity ────────────────────────────────────────────────
def get_equity_holdings() -> list:
    """
    Reads the Equity tab.
    Returns list of dicts with all equity fields.
    Expected headers:
    Symbol | Company_Name | Broker | Sector | Quantity | Purchase_Price | Purchase_Date | Current_Price | Notes
    """
    ws = _get_sheet().worksheet(TAB_EQUITY)
    records = ws.get_all_records()

    holdings = []
    for row in records:
        if not row.get("Symbol"):
            continue
        holdings.append({
          "symbol":         str(row.get("Symbol", "")).strip().upper(),
          "company_name":   str(row.get("Company_Name", "")).strip(),
          "broker":         str(row.get("Broker", "")).strip(),
          "sector":         str(row.get("Sector", "")).strip(),
          "quantity":       _to_float(row.get("Quantity")),
          "purchase_price": _to_float(row.get("Purchase_Price")),
          "purchase_date":  str(row.get("Purchase_Date", "")).strip(),
          "notes":          str(row.get("Notes", "")).strip(),
    })

    return holdings


def add_equity_holding(data: dict) -> dict:
    """
    Appends a new row to the Equity tab.
    data keys: symbol, company_name, broker, sector,
               quantity, purchase_price, purchase_date, notes
    """
    ws = _get_sheet().worksheet(TAB_EQUITY)
    ws.append_row([
        str(data.get("symbol", "")).upper(),
        data.get("company_name", ""),
        data.get("broker", ""),
        data.get("sector", ""),
        data.get("quantity", ""),
        data.get("purchase_price", ""),
        data.get("purchase_date", ""),
        data.get("notes", ""),
    ])
    _write_audit("ADD", "Equity",
                 f"Added {data.get('symbol','').upper()} x{data.get('quantity')} "
                 f"@ {data.get('purchase_price')}")
    return {"status": "success", "message": f"Added {data.get('symbol','').upper()} to Equity."}


# ── Mutual Funds ──────────────────────────────────────────
def get_fund_holdings() -> list:
    """
    Reads the MutualFunds tab.
    Expected headers:
    Fund_Name | Fund_Type | AMC | Investment_Date | Amount_Invested |
    Units_Purchased | Current_NAV | Exit_Load | Expense_Ratio |
    SIP_Amount | SIP_Date | Stepup_Percent | Notes
    """
    ws = _get_sheet().worksheet(TAB_FUNDS)
    records = ws.get_all_records()
    funds = []
    for row in records:
        if not row.get("Fund_Name"):
            continue
        funds.append({
            "fund_name":       str(row.get("Fund_Name", "")).strip(),
            "scheme_code":     str(row.get("Scheme_Code", "")).strip(),   # ← ADD
            "fund_type":       str(row.get("Fund_Type", "")).strip(),
            "amc":             str(row.get("AMC", "")).strip(),
            "investment_date": str(row.get("Investment_Date", "")).strip(),
            "amount_invested": _to_float(row.get("Amount_Invested")),
            "units_purchased": _to_float(row.get("Units_Purchased")),
            "exit_load":       _to_float(row.get("Exit_Load")),
            "expense_ratio":   _to_float(row.get("Expense_Ratio")),
            "sip_amount":      _to_float(row.get("SIP_Amount")),
            "sip_date":        _to_int(row.get("SIP_Date")),
            "stepup_percent":  _to_float(row.get("Stepup_Percent")),
            "notes":           str(row.get("Notes", "")).strip(),
        })
    return funds

def add_fund_holding(data: dict) -> dict:
    """
    Appends a new row to the MutualFunds tab.
    """
    ws = _get_sheet().worksheet(TAB_FUNDS)
    ws.append_row([
        data.get("fund_name", ""),
        data.get("scheme_code", ""), 
        data.get("fund_type", ""),
        data.get("amc", ""),
        data.get("investment_date", ""),
        data.get("amount_invested", ""),
        data.get("units_purchased", ""),
       
        data.get("exit_load", ""),
        data.get("expense_ratio", ""),
        data.get("sip_amount", ""),
        data.get("sip_date", ""),
        data.get("stepup_percent", ""),
        data.get("notes", ""),
    ])
    _write_audit("ADD", "MutualFund",
                 f"Added {data.get('fund_name','')} — {data.get('fund_type','')}")
    return {"status": "success", "message": f"Added {data.get('fund_name','')} to MutualFunds."}


# ── Audit Log ─────────────────────────────────────────────
def _write_audit(action: str, asset_type: str, details: str, user: str = "Jasneet"):
    """
    Appends a row to the AuditLog tab.
    Silently fails so it never breaks main functionality.
    """
    try:
        ws = _get_sheet().worksheet(TAB_AUDIT)
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        ws.append_row([timestamp, action, asset_type, details, user])
    except Exception:
        pass


def log_portfolio_view(asset_type: str = "All"):
    """Call this whenever portfolio data is read."""
    _write_audit("VIEW", asset_type, f"Portfolio data viewed — {asset_type}")
