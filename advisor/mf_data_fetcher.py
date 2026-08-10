import signal
import threading

def fetch_mstarpy_fund_details(fund_name: str):
    """
    Fetches deep mutual fund metrics using mstarpy (Morningstar data).
    Thread-safe wrapper to handle Flask worker thread signal issue.
    """
    mf_data = {
        "aum": "N/A",
        "expense_ratio": "N/A",
        "1y_return": "N/A",
        "3y_return": "N/A",
        "top_holdings": "N/A",
        "fund_category": "N/A"
    }

    result_container = {"data": mf_data, "error": None}

    def _fetch():
        try:
            # Import mstarpy INSIDE the thread to avoid signal issues
            import mstarpy

            print(f"[mstarpy] Searching Morningstar for: {fund_name}")
            fund = mstarpy.Funds(term=fund_name, country="in")

            # Get Expense Ratio
            try:
                if hasattr(fund, 'ongoingCharge') and fund.ongoingCharge:
                    mf_data["expense_ratio"] = f"{fund.ongoingCharge:.2f}%"
            except Exception as e:
                print(f"[mstarpy] Error fetching expense ratio: {e}")

            # Get AUM
            try:
                info = fund.feeAndInfo()
                if info and 'fundSize' in info and info['fundSize']:
                    size_in_cr = float(info['fundSize']) / 10000000
                    mf_data["aum"] = f"₹{size_in_cr:,.2f} Cr"
            except Exception as e:
                print(f"[mstarpy] Error fetching AUM: {e}")

            # Get Fund Category
            try:
                if hasattr(fund, 'category') and fund.category:
                    mf_data["fund_category"] = fund.category
            except Exception as e:
                print(f"[mstarpy] Error fetching category: {e}")

            # Get Top 3 Holdings
            try:
                holdings_df = fund.holdings(holdingType='all')
                if holdings_df is not None and not holdings_df.empty:
                    top_3 = holdings_df.head(3)
                    holdings_list = []
                    for index, row in top_3.iterrows():
                        name = row.get('securityName', 'Unknown')
                        weight = row.get('weighting', 0)
                        holdings_list.append(f"{name} ({weight:.2f}%)")
                    if holdings_list:
                        mf_data["top_holdings"] = " | ".join(holdings_list)
            except Exception as e:
                print(f"[mstarpy] Error fetching holdings: {e}")

            # Get Historical Returns
            try:
                returns_df = fund.trailingReturns()
                if returns_df is not None and not returns_df.empty:
                    first_row = returns_df.iloc[0]
                    if '1 Year' in returns_df.columns:
                        val = first_row['1 Year']
                        if val and str(val) != 'nan':
                            mf_data["1y_return"] = f"{float(val):.2f}%"
                    if '3 Years' in returns_df.columns:
                        val = first_row['3 Years']
                        if val and str(val) != 'nan':
                            mf_data["3y_return"] = f"{float(val):.2f}%"
            except Exception as e:
                print(f"[mstarpy] Error fetching returns: {e}")

            result_container["data"] = mf_data
            print(f"[mstarpy] Successfully fetched data for {fund_name}")

        except Exception as e:
            print(f"[mstarpy] Critical error: {e}")
            result_container["error"] = str(e)

    # Run mstarpy in a separate thread with a 15 second timeout
    thread = threading.Thread(target=_fetch)
    thread.start()
    thread.join(timeout=15)

    if thread.is_alive():
        print("[mstarpy] Timeout! Morningstar took too long to respond.")

    return result_container["data"]
