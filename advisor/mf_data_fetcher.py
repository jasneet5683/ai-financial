import requests
from bs4 import BeautifulSoup
from mftool import Mftool

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    mf_data = {
        "fund_name": fund_name,
        "scheme_code": scheme_code or "Unknown",
        "fund_category": "N/A",
        "fund_house": "N/A",
        "raw_search_text": ""
    }

    print(f"[mf_fetcher] Fetching data for: {fund_name}")

    # 1. Get exact Category and Fund House from mftool (Very reliable for India)
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

    # 2. Scrape DuckDuckGo HTML directly (Bypasses the 'ddgs' library block)
    try:
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )
        
        # Formulate a highly specific query
        query = f'"{search_name}" mutual fund AUM expense ratio moneycontrol groww'
        
        url = "https://html.duckduckgo.com/html/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        # POST request to the HTML search endpoint
        response = requests.post(url, headers=headers, data={"q": query}, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            # Extract all search result snippets
            snippets = soup.find_all(class_='result__snippet')
            
            if snippets:
                # Combine the top 4 snippets into one text block for the AI
                extracted_text = " | ".join([s.get_text(separator=" ", strip=True) for s in snippets[:4]])
                mf_data["raw_search_text"] = extracted_text
            else:
                print("[mf_fetcher] No snippets found in DDG HTML.")
        else:
            print(f"[mf_fetcher] DDG blocked request. Status: {response.status_code}")

    except Exception as e:
        print(f"[mf_fetcher] HTML Search error: {e}")

    # 3. Fallback to ensure AI never fails completely
    if not mf_data["raw_search_text"] or len(mf_data["raw_search_text"]) < 20:
         mf_data["raw_search_text"] = (
             f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. "
             f"Category: {mf_data['fund_category']}. "
             f"Live numerical data could not be fetched due to network blocking. "
             f"Please write a summary based on the fund category."
         )

    print(f"[mf_fetcher] Text sent to AI: {mf_data['raw_search_text'][:200]}...")
    
    return mf_data
