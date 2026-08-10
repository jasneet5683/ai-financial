from mftool import Mftool
from ddgs import DDGS
import re


def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    """
    Fetches basic details from mftool, and uses DuckDuckGo Search
    to extract AUM, Expense Ratio, and Returns from public search snippets.
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
                cat = details.get("scheme_category", "")
                type_ = details.get("scheme_type", "")
                mf_data["fund_category"] = f"{cat} {type_}".strip() or "N/A"
    except Exception as e:
        print(f"[mf_fetcher] mftool error: {e}")

    # 2. Use DuckDuckGo to find AUM, Expense Ratio, and Returns
    try:
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )

        query = f"{search_name} mutual fund AUM expense ratio 1Y 3Y return"

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

            combined_text = ""
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                combined_text += f"{title} {body} "

            combined_text = combined_text.strip()
            print(f"[mf_fetcher] Search snippet: {combined_text[:800]}")

            # --- Extract Expense Ratio ---
            exp_patterns = [
                r'(?i)expense ratio\s*(?:of|is)?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
                r'(?i)scheme expense ratio\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
            ]
            for pattern in exp_patterns:
                exp_match = re.search(pattern, combined_text)
                if exp_match:
                    mf_data["expense_ratio"] = f"{exp_match.group(1)}%"
                    break

            # --- Extract AUM ---
            aum_patterns = [
                r'(?i)AUM\s*\(.*?crores?.*?\)\s*([0-9,]+(?:\.[0-9]+)?)',
                r'(?i)AUM\s*[:\-]?\s*(?:₹|Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:Cr|Crore|Crores)',
                r'(?i)fund size\s*[:\-]?\s*(?:₹|Rs\.?|INR)?\s*([0-9,]+(?:\.[0-9]+)?)\s*(?:Cr|Crore|Crores)',
            ]
            for pattern in aum_patterns:
                aum_match = re.search(pattern, combined_text)
                if aum_match:
                    mf_data["aum"] = f"₹{aum_match.group(1)} Cr"
                    break

            # --- Extract 1Y Return ---
            r1_patterns = [
                r'(?i)1Y(?:ear)?\s*(?:return)?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
                r'(?i)returns?\s+for\s+1\s+year\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
            ]
            for pattern in r1_patterns:
                r1_match = re.search(pattern, combined_text)
                if r1_match:
                    mf_data["1y_return"] = f"{r1_match.group(1)}%"
                    break

            # --- Extract 3Y Return ---
            r3_patterns = [
                r'(?i)3Y(?:ear)?\s*(?:return)?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
                r'(?i)returns?\s+for\s+3\s+years?\s*[:\-]?\s*([0-9]+(?:\.[0-9]+)?)\s*%',
            ]
            for pattern in r3_patterns:
                r3_match = re.search(pattern, combined_text)
                if r3_match:
                    mf_data["3y_return"] = f"{r3_match.group(1)}%"
                    break

            # Keep raw snippet for AI fallback
            mf_data["_raw_search_snippet"] = combined_text[:800]

            print(f"[mf_fetcher] Parsed AUM: {mf_data['aum']}")
            print(f"[mf_fetcher] Parsed Expense Ratio: {mf_data['expense_ratio']}")
            print(f"[mf_fetcher] Parsed 1Y Return: {mf_data['1y_return']}")
            print(f"[mf_fetcher] Parsed 3Y Return: {mf_data['3y_return']}")

    except Exception as e:
        print(f"[mf_fetcher] DDGS Search error: {e}")

    print(f"[mf_fetcher] Fetched Data: {mf_data}")
    return mf_data
