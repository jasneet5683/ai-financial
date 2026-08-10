import requests
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

    # 2. Fetch directly from Groww's Search API
    try:
        # Clean the name for better searching
        search_name = (
            fund_name
            .replace(" - Direct Plan - Growth", "")
            .replace(" Direct Growth", "")
            .replace(" Regular Plan", "")
            .strip()
        )

        print(f"[mf_fetcher] Searching Groww API for: {search_name}")

        # Groww's public search endpoint
        url = f"https://groww.in/v1/api/search/v1/derived/scheme?available_for_investment=true&doc_type=scheme&q={search_name}"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Accept": "application/json"
        }

        response = requests.get(url, headers=headers, timeout=10)
        
        if response.status_code == 200:
            data = response.json()
            content = data.get("content", [])
            
            if content:
                # The first result is usually the correct fund
                best_match = content[0]
                
                # Groww returns these values natively in the search JSON!
                aum = best_match.get("aum", "Data unavailable")
                expense_ratio = best_match.get("expense_ratio", "Data unavailable")
                return_1y = best_match.get("return1y", "N/A")
                return_3y = best_match.get("return3y", "N/A")
                
                # Format AUM nicely
                if isinstance(aum, (int, float)):
                    aum_formatted = f"₹{aum:,.2f} Cr"
                else:
                    aum_formatted = str(aum)
                    
                # Format Expense Ratio
                if isinstance(expense_ratio, (int, float)):
                    er_formatted = f"{expense_ratio}%"
                else:
                    er_formatted = str(expense_ratio)

                mf_data["raw_search_text"] = (
                    f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. "
                    f"Category: {mf_data['fund_category']}. "
                    f"AUM: {aum_formatted}. "
                    f"Expense Ratio: {er_formatted}. "
                    f"1-Year Return: {return_1y}%. 3-Year Return: {return_3y}%."
                )
                print(f"[mf_fetcher] Successfully got Groww API Data!")
            else:
                print("[mf_fetcher] Groww API returned empty content list.")
        else:
             print(f"[mf_fetcher] Groww API failed with status {response.status_code}")

    except Exception as e:
        print(f"[mf_fetcher] Groww API error: {e}")

    # 3. Final Fallback
    if not mf_data["raw_search_text"]:
         mf_data["raw_search_text"] = (
             f"Basic Info: This is the {fund_name} managed by {mf_data['fund_house']}. "
             f"Category: {mf_data['fund_category']}. "
             f"Live numerical data could not be fetched. "
             f"Please write a summary based on the fund category."
         )

    return mf_data
