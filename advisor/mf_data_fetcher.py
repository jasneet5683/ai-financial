from mftool import Mftool
from ddgs import DDGS

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
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

    # 2. Grab text from DDGS
    try:
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )

        query = f'"{search_name}" direct growth AUM expense ratio 1 year return'
        
        with DDGS() as ddgs:
            results = list(ddgs.text(query, max_results=3))
            
            combined_text = ""
            for r in results:
                title = r.get("title", "")
                body = r.get("body", "")
                combined_text += f"{title}: {body} | "

            mf_data["raw_search_text"] = combined_text.strip()
            
            # If DDGS returned nothing, put a fallback message so the AI knows
            if not mf_data["raw_search_text"]:
                mf_data["raw_search_text"] = f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. Category: {mf_data['fund_category']}. No current AUM or expense ratio data could be fetched."
                
            print(f"[mf_fetcher] Final Search Text sent to AI: {mf_data['raw_search_text'][:200]}")

    except Exception as e:
        print(f"[mf_fetcher] DDGS Search error: {e}")
        # Fallback if DDGS crashes completely
        mf_data["raw_search_text"] = f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. Category: {mf_data['fund_category']}. Live search failed."

    return mf_data
