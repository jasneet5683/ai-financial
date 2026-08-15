from mftool import Mftool
from googlesearch import search

def fetch_mstarpy_fund_details(fund_name: str, scheme_code: str = None):
    mf_data = {
        "fund_name": fund_name,
        "scheme_code": scheme_code or "Unknown",
        "fund_category": "Unknown",
        "fund_house": "Unknown",
        "raw_search_text": ""
    }

    print(f"[mf_fetcher] Fetching data for: {fund_name} (Code: {scheme_code})")

    if not scheme_code:
        mf_data["raw_search_text"] = "No scheme code provided. Cannot fetch live data."
        return mf_data

    current_nav = "Unknown"
    nav_date = "Unknown"
    returns_text = "Return data unavailable."

    # 1. Base Data & Return Calculations using pure AMFI (mftool)
    try:
        obj = Mftool()
        
        # Get Category and AMC
        details = obj.get_scheme_details(scheme_code)
        if details:
            mf_data["fund_category"] = details.get("scheme_category", "Unknown")
            mf_data["fund_house"] = details.get("mutual_fund_family", "Unknown")

        # Get Historical NAVs and Calculate Returns
        nav_data = obj.get_scheme_historical_nav(scheme_code, as_json=False)
        
        if nav_data and 'data' in nav_data and len(nav_data['data']) > 0:
            nav_list = nav_data['data']
            current_nav = float(nav_list[0]['nav'])
            nav_date = nav_list[0]['date']
            mf_data["current_nav"] = current_nav
            mf_data["nav_date"]    = nav_date
            
            # Helper to safely get NAV from roughly X trading days ago
            def get_old_nav(days_ago):
                try:
                    if len(nav_list) > days_ago:
                        return float(nav_list[days_ago]['nav'])
                except:
                    pass
                return None

            nav_1y = get_old_nav(250) # Approx 250 trading days in a year
            nav_3y = get_old_nav(750)
            
            ret_1y_str = "N/A"
            if nav_1y:
                ret_1y = ((current_nav - nav_1y) / nav_1y) * 100
                ret_1y_str = f"{ret_1y:.2f}%"

            ret_3y_str = "N/A"
            if nav_3y:
                # CAGR Formula: (Ending Value / Beginning Value) ^ (1/Years) - 1
                cagr_3y = (((current_nav / nav_3y) ** (1/3)) - 1) * 100
                ret_3y_str = f"{cagr_3y:.2f}%"
                
            returns_text = f"1-Year Return: {ret_1y_str} | 3-Year CAGR: {ret_3y_str}"

    except Exception as e:
        print(f"[mf_fetcher] mftool calculation error: {e}")

    # 2. Safely Google for AUM and Expense Ratio (Fixed keyword arg)
    search_name = fund_name.replace(" - Direct Plan - Growth", "").strip()
    google_text = ""
    
    try:
        query = f'"{search_name}" AUM expense ratio moneycontrol'
        print(f"[mf_fetcher] Googling snippets for: {query}")
        
        # FIXED: Removed 'num' and 'pause', using 'num_results' for latest package version
        results = search(query, num_results=2, advanced=True)
        
        for r in results:
            title = getattr(r, 'title', '')
            desc = getattr(r, 'description', '')
            google_text += f"{title}: {desc} | "
            
    except Exception as e:
        print(f"[mf_fetcher] Google Search failed: {e}")

    # 3. Compile the final block for the AI
    final_text = (
        f"Verified Data from AMFI:\n"
        f"Fund House: {mf_data['fund_house']}\n"
        f"Category: {mf_data['fund_category']}\n"
        f"Latest NAV: ₹{current_nav} (Date: {nav_date})\n"
        f"Calculated Performance: {returns_text}\n\n"
    )

    if google_text:
        final_text += (
            f"Web Search Results for AUM & Expense Ratio:\n"
            f"{google_text}\n"
            f"Please extract the AUM and Expense Ratio from the text above if present."
        )
    else:
        final_text += "AUM and Expense Ratio data is currently unavailable. Base your analysis on the calculated performance."

    mf_data["raw_search_text"] = final_text
    
    print(f"[mf_fetcher] Final text sent to AI: {mf_data['raw_search_text'][:200]}...")

    # Ensure keys always exist even if nav fetch failed
    mf_data.setdefault("current_nav", None)
    mf_data.setdefault("nav_date",    None)

    return mf_data
