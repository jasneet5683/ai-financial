from mftool import Mftool
from ddgs import DDGS

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    """
    Fetches basic details from mftool, and uses DuckDuckGo Search
    to grab text snippets about AUM, Expense Ratio, and Returns.
    Passes all raw text to the AI for intelligent extraction.
    """
    mf_data = {
        "fund_name": fund_name,
        "scheme_code": scheme_code or "Unknown",
        "fund_category": "N/A",
        "fund_house": "N/A",
        "raw_search_text": ""
    }

    print(f"[mf_fetcher] Fetching basic text for: {fund_name} ({scheme_code})")

    # 1. Get Category from mftool
    try:
        if scheme_code:
            obj = Mftool()
            details = obj.get_scheme_details(scheme_code)
            if details:
                cat = details.get("scheme_category", "")
                type_ = details.get("scheme_type", "")
                mf_data["fund_category"] = f"{cat} {type_}".strip() or "N/A"
                mf_data["fund_house"] = details.get("mutual_fund_family", "N/A")
    except Exception as e:
        print(f"[mf_fetcher] mftool error: {e}")

    # 2. Grab text from DDGS (DuckDuckGo) for AI to read later
    try:
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )

        # Search specifically for the metrics we need
        query = f'"{search_name}" direct growth AUM expense ratio 1 year return 3 year return'

        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=5))

            combined_text = ""
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                combined_text += f"[{title}] {body} | "

            mf_data["raw_search_text"] = combined_text.strip()
            print(f"[mf_fetcher] Grabbed Search Text: {combined_text[:300]}...")

    except Exception as e:
        print(f"[mf_fetcher] DDGS Search error: {e}")

    return mf_data
