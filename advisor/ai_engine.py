"""
ai_engine.py
Sends structured stock/portfolio data to OpenRouter and returns
McKinsey/Bain-style analysis as validated JSON.
"""

import os
import json
import requests

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

PRIMARY_MODEL = "deepseek/deepseek-r1"
FALLBACK_MODEL = "mistralai/mistral-7b-instruct"

# ---------- JSON schema the AI must follow ----------
RESPONSE_SCHEMA_HINT = """
Respond ONLY with valid JSON in exactly this structure (no markdown, no extra text):

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

SYSTEM_PROMPT = f"""You are a seasoned financial advisor with 20+ years of experience 
at top-tier firms like McKinsey & Company and Bain & Company. You analyze stocks and 
portfolios with institutional rigor, precision, and no fluff. You always ground your 
analysis in the data provided — never invent numbers not given to you. If data is 
marked "Not available", acknowledge the gap instead of guessing.

{RESPONSE_SCHEMA_HINT}
"""


def _call_openrouter(model: str, user_content: str) -> str:
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.4,
    }
    response = requests.post(OPENROUTER_URL, headers=headers, json=payload, timeout=60)
    response.raise_for_status()
    result = response.json()
    return result["choices"][0]["message"]["content"]


def _extract_json(raw_text: str) -> dict:
    """
    Handles cases where the model wraps JSON in markdown fences or adds stray text.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:].strip()

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Fallback: extract first {...} block
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start:end + 1])
        except json.JSONDecodeError:
            pass

    raise ValueError("Could not parse valid JSON from model response")


def analyze_stock(stock_data: dict) -> dict:
    """
    Takes structured stock data (from stock_analyzer.get_stock_data)
    and returns AI-generated structured analysis.
    """
    user_content = (
        f"Analyze this stock based on the following live data:\n\n"
        f"{json.dumps(stock_data, indent=2)}\n\n"
        f"Provide your analysis strictly in the JSON schema described."
    )
    return _run_with_fallback(user_content)


def analyze_portfolio(portfolio_data: list) -> dict:
    """
    Takes structured portfolio data (from stock_analyzer.get_portfolio_data)
    and returns AI-generated structured portfolio-level analysis.
    """
    user_content = (
        f"Analyze this investment portfolio based on the following holdings "
        f"and their live data (including P&L):\n\n"
        f"{json.dumps(portfolio_data, indent=2)}\n\n"
        f"Consider diversification, concentration risk, and overall portfolio health. "
        f"Provide your analysis strictly in the JSON schema described."
    )
    return _run_with_fallback(user_content)


def _run_with_fallback(user_content: str) -> dict:
    """
    Tries primary model first, falls back to secondary model on failure.
    Returns parsed JSON dict, or an error dict if both fail.
    """
    for model in (PRIMARY_MODEL, FALLBACK_MODEL):
        try:
            raw_response = _call_openrouter(model, user_content)
            parsed = _extract_json(raw_response)
            parsed["_model_used"] = model
            return parsed
        except Exception as e:
            last_error = str(e)
            continue

    return {
        "error": "AI analysis failed on both primary and fallback models.",
        "details": last_error,
    }
