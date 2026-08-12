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
    return """You are a friendly, highly knowledgeable AI financial mentor. Your job is to analyze stock data and explain it simply to an everyday retail investor (the 'common man'). 
Do not use overly complex Wall Street jargon. Instead, explain *why* the numbers matter using simple language and analogies.

You must ALWAYS return your analysis in the following strict JSON format. 

JSON Schema:
{
  "executive_summary": "A simple, easy-to-understand 2-3 sentence overview of what the company does and how it's currently performing.",
  "key_metrics_commentary": "Explain the P/E ratio, EPS, etc. in simple terms. What do these numbers actually mean for a regular investor? Is the stock currently expensive or cheap?",
  "risks": [
    {"risk": "Geopolitical Impact", "severity": "High/Medium/Low", "detail": "Explain how current global events (wars, trade policies, supply chains, elections) affect this specific company."},
    {"risk": "Company Risk", "severity": "High/Medium/Low", "detail": "A specific internal or market risk to this company."}
  ],
  "opportunities": [
    {"opportunity": "Future Growth Prospects", "detail": "Explain the company's future growth plans, new products, or market expansion in simple terms."},
    {"opportunity": "Industry Trend", "detail": "Explain a broader trend that is helping this company grow."}
  ],
  "scenario_analysis": {
    "bull_case": "Best case scenario over the next 1-2 years.",
    "base_case": "Most likely scenario.",
    "bear_case": "Worst case scenario."
  },
  "recommendation": "Buy, Hold, or Sell (or 'Wait and Watch')",
  "rationale": "A simple explanation of why you make this recommendation.",
  "confidence_level": "High/Medium/Low"
}
IMPORTANT: Return ONLY the raw JSON object. No markdown, no code fences, no explanation before or after. Start your response directly with { and end with }.
"""


def build_stock_user_prompt(stock_data: dict, user_question: str = None) -> str:
    base_prompt = f"""
Please analyze the following stock data for a beginner investor.
Company: {stock_data.get('company_name', stock_data.get('ticker'))}
Current Price: {stock_data.get('current_price')}
P/E Ratio: {stock_data.get('pe_ratio')}
EPS: {stock_data.get('eps')}
Market Cap: {stock_data.get('market_cap')}
52-Week High/Low: {stock_data.get('52_week_high', 'N/A')} / {stock_data.get('52_week_low', 'N/A')}

CRITICAL INSTRUCTIONS:
1. Translate these numbers into plain English. 
2. Explicitly analyze how CURRENT GEOPOLITICAL ISSUES might impact this specific company. Put this in the 'risks' section.
3. Explicitly analyze the FUTURE GROWTH PROSPECTS of this company. Put this in the 'opportunities' section.
"""
    if user_question:
        base_prompt += f"\nAdditionally, the user asked this specific question: '{user_question}'. Make sure to weave the answer to this question into your summary or rationale in simple terms."

    return base_prompt

def build_portfolio_system_prompt() -> str:
    return f"""{BASE_PERSONA}

Respond ONLY with valid JSON in exactly this structure (no markdown, no extra text):

{PORTFOLIO_SCHEMA}"""


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

def build_followup_prompt(stock_data: dict, analysis: dict, question: str) -> str:
    return f"""
We just analyzed a stock for a beginner investor. 
Here is the stock data:
{stock_data}

Here is the analysis we provided them:
{analysis}

The user has a follow-up question: "{question}"

Answer their question directly in 3-4 short, easy-to-understand paragraphs. 
Use plain English. Do not output JSON. Do not use Wall Street jargon. 
If the question is about geopolitical issues or future growth, give a clear, realistic scenario.
"""

def build_mf_system_prompt() -> str:
    return """You are a highly analytical, objective financial data extraction AI.
Your task is to analyze raw mutual fund data and extract factual metrics into a strict JSON structure.

Instructions:
1. Extract AUM and Expense Ratio from the 'raw_search_text'.
2. If a metric is NOT mentioned, state "Data unavailable". Do NOT invent numbers.
3. Write a summary, pros, and cons based on the Fund Name, Category, and the provided text.
4. Even if numbers are missing in the search text, you MUST write a descriptive summary, pros, and cons based on the fund's name and category.

You MUST return EXACTLY this JSON structure, and nothing else:
{
  "summary": "A 2-3 sentence objective overview of what this fund is based on its category and name.",
  "fund_profile": {
    "category": "The fund category",
    "expense_ratio_context": "Extracted Expense Ratio or 'Data unavailable'",
    "aum_context": "Extracted AUM or 'Data unavailable'"
  },
  "pros": [
    "Factual positive point based on category",
    "Factual positive point 2"
  ],
  "cons": [
    "Factual risk or negative point based on category",
    "Factual risk or negative point 2"
  ],
  "verdict": "A brief objective conclusion."
}"""

def build_mf_user_prompt(mf_data: dict, user_question: str = None) -> str:
    """
    Constructs the user prompt for Mutual Fund analysis.
    Ensures the raw_search_text (which contains AMFI calculations and Google snippets)
    is explicitly passed to the AI.
    """
    fund_name = mf_data.get("fund_name", "Unknown Fund")
    fund_category = mf_data.get("fund_category", "Unknown Category")
    fund_house = mf_data.get("fund_house", "Unknown House")
    
    # This is the magic line that was missing/incorrect before
    raw_search_text = mf_data.get("raw_search_text", "No live data available.")

    prompt = (
        f"Analyze the following Mutual Fund/ETF:\n"
        f"Fund Name: {fund_name}\n"
        f"Fund House: {fund_house}\n"
        f"Category: {fund_category}\n\n"
        f"Here is the latest live data retrieved from AMFI and web search:\n"
        f"--- LIVE DATA START ---\n"
        f"{raw_search_text}\n"
        f"--- LIVE DATA END ---\n\n"
        f"Using the live data provided above, provide a comprehensive analysis."
    )

    if user_question:
        prompt += f"\n\nThe user asked a specific question: '{user_question}'\nPlease address this question specifically in your analysis summary."

    return prompt
