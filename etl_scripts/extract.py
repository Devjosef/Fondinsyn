import requests
import logging
from typing import List, Dict, Any

# this is set as an example: Will be replaced shortly
FUND_API_ENDPOINTS = {
    "fund_1": "https://api.swedishfund1.se/holdings",
    "fund_2": "https://api.swedishfund2.se/holdings",
}

def fetch_holdings_from_api(url: str, timeout: int = 10) -> List[Dict[str, Any]]:
    """Fetch holdings JSON data from a given API endpoint """
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list):
            return data
        elif isinstance(data,dict) and 'holdings' in data:
            return data['holdings']
        else:
            logging.warning(f"Unexpected JSON structure from {url}, returning empty list")
            return []
    except requests.RequestException as e:
        logging.error(f"Error fetching holdings data from {url}: {e}")
        return []
    except ValueError as e:
        logging.error(f"Invalid JSON received from {url}: {e}")
        return []
    

def extract_holdings() -> List[Dict[str, Any]]:
    all_holdings: List[Dict[str, Any]] = []
    for fund_id, api_url in FUND_API_ENDPOINTS.items():
        logging.info(f"Fetching holdings for {fund_id} from {api_url}")
        holdings = fetch_holdings_from_api(api_url)
        for holding in holdings:
            holding['fund_id'] = fund_id
        all_holdings.extend(holdings)
    
    logging.info(f"Successfully extracted total {len(all_holdings)} holdings across {len(FUND_API_ENDPOINTS)} funds.")
    return all_holdings


if __name__ == "__main__":
    holdings = extract_holdings()
    print(f"Total holdings extracted: {len(holdings)}")
    if holdings:
        print("Sample holding:", holdings[0])