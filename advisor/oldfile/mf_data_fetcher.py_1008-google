from mftool import Mftool
from googlesearch import search
import time

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    mf_data = {
        "fund_name": fund_name,
        "scheme_code": scheme_code or "Unknown",
        "fund_category": "N/A",
        "fund_house": "N/A",
        "raw_search_text": ""
    }

    print(f"[mf_fetcher] Fetching data for: {fund_name}")

    # 1. Get exact Category and Fund House from mftool
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

    # 2. Grab text from Google Search (highly reliable, bypasses DDG blocks)
    try:
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )

        query = f'"{search_name}" mutual fund AUM expense ratio moneycontrol groww'
        print(f"[mf_fetcher] Searching Google for: {query}")
        
        # We use advanced=True to get the title and the snippet descriptions
        # We pause for 2 seconds to ensure Google doesn't block the Railway IP
        results = search(query, num=3, stop=3, pause=2.0, advanced=True)
        
        combined_text = ""
        for r in results:
            # googlesearch-python returns objects with .title and .description
            title = getattr(r, 'title', '')
            desc = getattr(r, 'description', '')
            combined_text += f"{title}: {desc} | "

        mf_data["raw_search_text"] = combined_text.strip()
        
    except Exception as e:
        print(f"[mf_fetcher] Google Search error: {e}")

    # 3. Fallback to ensure AI never fails
    if not mf_data["raw_search_text"] or len(mf_data["raw_search_text"]) < 20:
         mf_data["raw_search_text"] = (
             f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. "
             f"Category: {mf_data['fund_category']}. "
             f"Live numerical data could not be fetched. "
             f"Please write a summary based on the fund category."
         )

    print(f"[mf_fetcher] Final text sent to AI: {mf_data['raw_search_text'][:250]}...")
    
    return mf_data
