from mftool import Mftool
from ddgs import DDGS
import re

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    """
    Fetches basic details from mftool, and uses DuckDuckGo Search 
    to extract AUM and Expense Ratio from public search snippets.
    """
    mf_data = {
        "aum": "N/A",
        "expense_ratio": "N/A",
        "1y_return": "N/A",
        "3y_return": "N/A",
        "top_holdings": "N/A",
        "fund_category": "N/A"
    }

    print(f"[mf_fetcher] Fetching deep data for: {fund_name} ({scheme_code})")

    # 1. Get Category from mftool
    try:
        if scheme_code:
            obj = Mftool()
            details = obj.get_scheme_details(scheme_code)
            if details:
                cat = details.get('scheme_category', '')
                type_ = details.get('scheme_type', '')
                mf_data["fund_category"] = f"{cat} {type_}".strip() or "N/A"
    except Exception as e:
        print(f"[mf_fetcher] mftool error: {e}")

    # 2. Use DuckDuckGo to find AUM, Expense Ratio, and Returns
    try:
        # Clean the fund name for better search results
        search_name = fund_name.replace(" - Direct Plan - Growth", "").replace(" Direct Growth", "")
        
        # Search query designed to pull up Groww/ValueResearch snippets
        query = f"{search_name} mutual fund AUM Expense Ratio 1Y 3Y return"
        
        with DDGS() as ddgs:
            # Get the top 3 search results
            results = list(ddgs.text(query, max_results=3))
            
            combined_text = ""
            for r in results:
                combined_text += r.get('body', '') + " "

            # --- Extract Expense Ratio (e.g., 0.55%, 1.2%) ---
            exp_match = re.search(r'(?i)(?:expense ratio\s*(?:of|is)?\s*[:\-]?\s*)([0-9]+\.[0-9]+)\s*%', combined_text)
            if exp_match:
                mf_data["expense_ratio"] = f"{exp_match.group(1)}%"

            # --- Extract AUM (e.g., ₹10,000 Cr, 5000 crores) ---
            aum_match = re.search(r'(?i)(?:aum|fund size)\s*(?:of|is)?\s*[:\-]?\s*(?:rs\.?|₹|inr)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:cr|crore)', combined_text)
            if aum_match:
                mf_data["aum"] = f"₹{aum_match.group(1)} Cr"

            # --- Extract Returns (Look for 1Y and 3Y patterns) ---
            # This is a bit looser, but AI can use the combined text if regex fails
            r1_match = re.search(r'(?i)1y(?:ear)?\s*(?:return)?\s*[:\-]?\s*([0-9]+\.[0-9]+)\s*%', combined_text)
            if r1_match:
                mf_data["1y_return"] = f"{r1_match.group(1)}%"
                
            r3_match = re.search(r'(?i)3y(?:ear)?\s*(?:return)?\s*[:\-]?\s*([0-9]+\.[0-9]+)\s*%', combined_text)
            if r3_match:
                mf_data["3y_return"] = f"{r3_match.group(1)}%"

            # Give the AI the raw text snippet to figure out Top Holdings 
            # since regexing exact company names from snippets is hard.
            mf_data["_raw_search_snippet"] = combined_text[:500] 

    except Exception as e:
        print(f"[mf_fetcher] DDGS Search error: {e}")

    print(f"[mf_fetcher] Fetched Data: {mf_data}")
    return mf_data
