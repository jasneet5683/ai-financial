"""
prompt_builder.py
Builds system and user prompts for the AI engine, ensuring consistent
McKinsey/Bain-style structured JSON output across stock and portfolio analysis.
"""

import json

# ---------- JSON schema definitions ----------

STOCK_SCHEMA = """
{
  "executive_summary": "2-3 sentence high-level view",
  "key_metrics_commentary": "Brief note on P/E, growth, valuation vs peers",
  "risks": [
    {"risk": "short risk name", "detail": "1-2 sentence explanation", "severity": "Low|Medium|High"}
  ],
  "opportunities": [
    {"opportunity": "short name", "detail": "1-2 sentence explanation"}
  ],
  "scenario_analysis": {
    "bull_case": "brief description",
    "base_case": "brief description",
    "bear_case": "brief description"
  },
  "recommendation": "Buy|Hold|Sell|Accumulate|Reduce",
  "rationale": "2-3 sentence justification for the recommendation",
  "confidence_level": "Low|Medium|High"
}
"""

PORTFOLIO_SCHEMA = """
{
  "executive_summary": "2-3 sentence high-level view of portfolio health",
  "diversification_assessment": "Comment on sector/stock concentration risk",
  "top_performers": [
    {"ticker": "symbol", "reason": "why it's performing well"}
  ],
  "underperformers": [
    {"ticker": "symbol", "reason": "why it's lagging", "action_suggested": "short suggestion"}
  ],
  "risks": [
    {"risk": "short risk name", "detail": "1-2 sentence explanation", "severity": "Low|Medium|High"}
  ],
  "rebalancing_suggestions": [
    {"suggestion": "short text", "rationale": "1-2 sentence reasoning"}
  ],
  "overall_recommendation": "2-3 sentence portfolio-level guidance",
  "confidence_level": "Low|Medium|High"
}
"""

BASE_PERSONA = """You are a seasoned financial advisor with 20+ years of experience 
at top-tier firms like McKinsey & Company and Bain & Company. You analyze stocks and 
portfolios with institutional rigor, precision, and no fluff. You always ground your 
analysis in the data provided — never invent numbers not given to you. If a field is 
marked "Not available", acknowledge the gap instead of guessing.

You are advising an investor based in India. Prices/values are typically in INR unless 
the ticker indicates a foreign exchange (e.g. no .NS/.BO suffix)."""


def build_stock_system_prompt() -> str:
    return f"""{BASE_PERSONA}

Respond ONLY with valid JSON in exactly this structure (no markdown, no extra text):

{STOCK_SCHEMA}"""


def build_portfolio_system_prompt() -> str:
    return f"""{BASE_PERSONA}

Respond ONLY with valid JSON in exactly this structure (no markdown, no extra text):

{PORTFOLIO_SCHEMA}"""


def build_stock_user_prompt(stock_data: dict, user_question: str = None) -> str:
    """
    user_question: optional free-text question from the user
    (e.g. "should I buy more at this price?") to give the AI extra context.
    """
    question_block = f"\nInvestor's specific question: {user_question}\n" if user_question else ""
    return (
        f"Analyze this stock based on the following live data:\n\n"
        f"{json.dumps(stock_data, indent=2)}\n"
        f"{question_block}\n"
        f"Provide your analysis strictly in the JSON schema described in the system prompt."
    )


def build_portfolio_user_prompt(portfolio_data: list, user_question: str = None) -> str:
    question_block = f"\nInvestor's specific question: {user_question}\n" if user_question else ""
    return (
        f"Analyze this investment portfolio based on the following holdings "
        f"and their live data (including P&L):\n\n"
        f"{json.dumps(portfolio_data, indent=2)}\n"
        f"{question_block}\n"
        f"Consider diversification, concentration risk, sector exposure, and overall "
        f"portfolio health. Provide your analysis strictly in the JSON schema described."
    )
