import requests
from mftool import Mftool
from googlesearch import search
import time

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    mf_data = {
        "fund_name": fund_name,
        "scheme_code": scheme_code or "Unknown",
        "fund_category": "Unknown",
        "fund_house": "Unknown",
        "raw_search_text": ""
    }

    print(f"[mf_fetcher] Fetching data for: {fund_name} (Code: {scheme_code})")

    # 1. Base Data from mftool (Category & House)
    if scheme_code:
        try:
            obj = Mftool()
            details = obj.get_scheme_details(scheme_code)
            if details:
                mf_data["fund_category"] = details.get("scheme_category", "Unknown")
                mf_data["fund_house"] = details.get("mutual_fund_family", "Unknown")
        except Exception as e:
            print(f"[mf_fetcher] mftool error: {e}")

    # 2. Get Live NAV from MFAPI.in (Very Reliable, Unblocked)
    current_nav = "Unknown"
    nav_date = "Unknown"
    if scheme_code:
        try:
            mfapi_url = f"https://api.mfapi.in/mf/{scheme_code}"
            response = requests.get(mfapi_url, timeout=10)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0:
                    current_nav = data["data"][0]["nav"]
                    nav_date = data["data"][0]["date"]
        except Exception as e:
            print(f"[mf_fetcher] MFAPI error: {e}")

    # 3. Safely Google for AUM and Expense Ratio (Bypasses IP blocks)
    # We clean the name to make the search highly specific
    search_name = fund_name.replace(" - Direct Plan - Growth", "").strip()
    google_text = ""
    
    try:
        query = f'"{search_name}" AUM expense ratio moneycontrol'
        print(f"[mf_fetcher] Googling: {query}")
        
        # advanced=True returns the snippet text. pause=2.0 prevents Railway IP block.
        results = search(query, num=2, stop=2, pause=2.0, advanced=True)
        
        for r in results:
            title = getattr(r, 'title', '')
            desc = getattr(r, 'description', '')
            google_text += f"{title}: {desc} | "
            
    except Exception as e:
        print(f"[mf_fetcher] Google Search failed (likely rate limit): {e}")

    # 4. Compile the final block for the AI
    # We provide the guaranteed API data, plus the Google snippets if available.
    final_text = (
        f"Verified Data from AMFI/MFAPI:\n"
        f"Fund House: {mf_data['fund_house']}\n"
        f"Category: {mf_data['fund_category']}\n"
        f"Latest NAV: ₹{current_nav} (Date: {nav_date})\n\n"
    )

    if google_text:
        final_text += (
            f"Web Search Results for AUM & Expense Ratio:\n"
            f"{google_text}\n"
            f"Please extract the AUM and Expense Ratio from the text above if present."
        )
    else:
        final_text += "AUM and Expense Ratio data is currently unavailable. Base your analysis on the category and NAV."

    mf_data["raw_search_text"] = final_text
    
    print(f"[mf_fetcher] Final text sent to AI: {mf_data['raw_search_text'][:200]}...")

    return mf_data
