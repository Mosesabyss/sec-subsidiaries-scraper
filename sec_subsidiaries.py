import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import logging
from typing import Optional, List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# SEC requires a valid user-agent
HEADERS = {
    'User-Agent': 'Your Name your.email@example.com'
}

def get_cik(ticker: str) -> Optional[str]:
    """
    Retrieves the CIK for a given ticker symbol from SEC-provided JSON file.
    Note: This covers only major companies. You can skip this and enter CIK directly.
    
    Args:
        ticker (str): Stock ticker symbol
        
    Returns:
        Optional[str]: CIK number if found, None otherwise
    """
    url = "https://www.sec.gov/files/company_tickers_exchange.json"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        data = response.json()
        for item in data.values():
            if item['ticker'].lower() == ticker.lower():
                return str(item['cik_str']).zfill(10)
        logger.warning(f"CIK not found for ticker: {ticker}")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching CIK: {e}")
        return None

def get_10k_accession(cik: str, year: int) -> Optional[str]:
    """
    Gets accession number for the 10-K filing made in the specified year.
    
    Args:
        cik (str): Company CIK number
        year (int): Year of filing
        
    Returns:
        Optional[str]: Accession number if found, None otherwise
    """
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        filings = response.json().get("filings", {}).get("recent", {})
        for i, form_type in enumerate(filings.get("form", [])):
            filing_date = filings["filingDate"][i]
            if form_type == "10-K" and filing_date.startswith(str(year)):
                return filings["accessionNumber"][i].replace("-", "")
        logger.warning(f"No 10-K found for CIK {cik} in year {year}")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching 10-K accession: {e}")
        return None

def get_exhibit_21_url(cik: str, accession_number: str) -> Optional[str]:
    """
    Returns the URL of Exhibit 21 (subsidiaries list) if found.
    
    Args:
        cik (str): Company CIK number
        accession_number (str): Filing accession number
        
    Returns:
        Optional[str]: URL of Exhibit 21 if found, None otherwise
    """
    filing_index_url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number}/index.json"
    try:
        response = requests.get(filing_index_url, headers=HEADERS)
        response.raise_for_status()
        for file in response.json().get("directory", {}).get("item", []):
            name = file.get("name", "").lower()
            if "21" in name and name.endswith(".htm"):
                return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession_number}/{file['name']}"
        logger.warning(f"Exhibit 21 not found for CIK {cik} with accession {accession_number}")
        return None
    except requests.RequestException as e:
        logger.error(f"Error fetching Exhibit 21 URL: {e}")
        return None

def parse_exhibit_21_table(url: str) -> Optional[List[Dict[str, str]]]:
    """
    Parses the Exhibit 21 HTML to extract subsidiary name and jurisdiction.
    
    Args:
        url (str): URL of the Exhibit 21 HTML file
        
    Returns:
        Optional[List[Dict[str, str]]]: List of dictionaries containing subsidiary data if found, None otherwise
    """
    try:
        response = requests.get(url, headers=HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        tables = soup.find_all("table")
        data = []
        for table in tables:
            rows = table.find_all("tr")
            for row in rows:
                cols = row.find_all(["td", "th"])
                text = [col.get_text(strip=True) for col in cols]
                if len(text) >= 2:
                    data.append({
                        "Name of Subsidiary": text[0],
                        "Jurisdiction of Incorporation or Organization": text[1]
                    })
        return data if data else None
    except requests.RequestException as e:
        logger.error(f"Error parsing Exhibit 21 table: {e}")
        return None

def extract_subsidiaries_for_company(ticker: str, company_name: str) -> None:
    """
    Main runner function: builds Excel file with one sheet per year (2018–2024).
    
    Args:
        ticker (str): Stock ticker symbol
        company_name (str): Company name for the output file
    """
    logger.info(f"Starting extraction for {company_name} ({ticker})")
    
    cik = get_cik(ticker)
    if not cik:
        logger.error(f"Could not find CIK for {ticker}. You can also hardcode it if known.")
        return

    output_file = f"{company_name.replace(' ', '_')}.xlsx"
    writer = pd.ExcelWriter(output_file, engine="openpyxl")

    for year in range(2018, 2025):
        logger.info(f"Processing year {year}...")
        accession = get_10k_accession(cik, year)

        if not accession:
            pd.DataFrame([{
                "Year": year,
                "Name of Subsidiary": "",
                "Jurisdiction of Incorporation or Organization": "",
                "Notes": "10-K filing not found"
            }]).to_excel(writer, sheet_name=str(year), index=False)
            continue

        exhibit_url = get_exhibit_21_url(cik, accession)
        if not exhibit_url:
            pd.DataFrame([{
                "Year": year,
                "Name of Subsidiary": "",
                "Jurisdiction of Incorporation or Organization": "",
                "Notes": "Exhibit 21.01 not found"
            }]).to_excel(writer, sheet_name=str(year), index=False)
            continue

        rows = parse_exhibit_21_table(exhibit_url)
        if not rows:
            pd.DataFrame([{
                "Year": year,
                "Name of Subsidiary": "",
                "Jurisdiction of Incorporation or Organization": "",
                "Notes": "Exhibit 21 found but data could not be extracted"
            }]).to_excel(writer, sheet_name=str(year), index=False)
            continue

        df = pd.DataFrame(rows)
        df["Year"] = year
        df["Notes"] = ""
        df = df[["Year", "Name of Subsidiary", "Jurisdiction of Incorporation or Organization", "Notes"]]
        df.to_excel(writer, sheet_name=str(year), index=False)

        time.sleep(1)  # Respect SEC rate limit

    writer.close()
    logger.info(f"✅ Excel file saved as {output_file}")

if __name__ == "__main__":
    # Example usage
    extract_subsidiaries_for_company("EMN", "EASTMAN CHEMICAL CO") 