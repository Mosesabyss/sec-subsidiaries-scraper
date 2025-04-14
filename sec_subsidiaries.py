import requests
import pandas as pd
import logging
import time
import json
from bs4 import BeautifulSoup
import re
from datetime import datetime
import os
from typing import List, Dict, Any

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('subsidiaries.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Constants for rate limiting
REQUEST_DELAY = 0.5  # Delay between requests in seconds
MAX_RETRIES = 3
RATE_LIMIT_WAIT = 30  # Seconds to wait when rate limited

# Create a session object with proper headers
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept': 'application/json, text/html, */*',
    'Accept-Encoding': 'gzip, deflate',
    'Host': 'www.sec.gov',
    'Connection': 'keep-alive'
})

def get_with_retry(url, method="GET", json=None, max_retries=3, initial_wait=1):
    """Make an HTTP request with retry logic."""
    headers = {
        'User-Agent': 'Subsidiaries/1.0 (contact@example.com)',
        'Accept': 'application/json, text/html, application/xml, */*',
        'Accept-Encoding': 'gzip, deflate'
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    for attempt in range(max_retries):
        try:
            time.sleep(0.1)  # Basic rate limiting
            if method.upper() == "GET":
                response = session.get(url)
            else:
                response = session.post(url, json=json)
                
            if response.status_code == 429:  # Rate limited
                wait_time = initial_wait * (2 ** attempt)  # Exponential backoff
                logging.warning(f"Rate limited, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
                
            if response.status_code == 403:  # Forbidden
                wait_time = 10  # Fixed wait time for forbidden responses
                logging.warning(f"Request forbidden, waiting {wait_time} seconds...")
                time.sleep(wait_time)
                continue
                
            return response
            
        except requests.exceptions.RequestException as e:
            logging.error(f"Request failed: {str(e)}")
            if attempt < max_retries - 1:
                wait_time = initial_wait * (2 ** attempt)
                logging.info(f"Retrying in {wait_time} seconds...")
                time.sleep(wait_time)
            else:
                logging.error("Max retries reached")
                return None
                
    return None

def get_cik(ticker):
    """Get the CIK number for a company ticker."""
    try:
        # Try to get CIK from the SEC's company lookup
        url = f"https://www.sec.gov/cgi-bin/browse-edgar?CIK={ticker}&owner=exclude&action=getcompany&output=atom"
        response = get_with_retry(url)
        
        if response and response.status_code == 200:
            # Parse the XML response
            soup = BeautifulSoup(response.text, 'xml')
            
            # Find the CIK in the company info
            cik_tag = soup.find('cik')
            if cik_tag:
                cik = str(int(cik_tag.text)).zfill(10)
                logging.info(f"Found CIK for {ticker}: {cik}")
                return cik
                
        logging.warning(f"Could not find CIK for ticker: {ticker}")
        return None
        
    except Exception as e:
        logging.error(f"Error getting CIK: {str(e)}")
        return None

def get_10k_accession(cik, year):
    """Get the accession number for a company's 10-K filing for a specific year."""
    try:
        # Format CIK to 10 digits
        cik = str(cik).zfill(10)
        
        # Construct the URL for the SEC submissions API
        url = f"https://data.sec.gov/submissions/CIK{cik}.json"
        
        # Make the request with retry logic
        response = get_with_retry(url)
        if not response:
            return None
            
        # Parse the response
        data = response.json()
        filings = data.get('filings', {}).get('recent', {})
        
        # Get the list of forms and dates
        forms = filings.get('form', [])
        dates = filings.get('filingDate', [])
        accessions = filings.get('accessionNumber', [])
        
        # Find the most recent 10-K filing for the specified year
        for form, date, accession in zip(forms, dates, accessions):
            if form == '10-K' and date.startswith(str(year)):
                logging.info(f"Found 10-K for {year} with accession: {accession}")
                return accession.replace('-', '')
                
        logging.warning(f"No 10-K filing found for {year}")
        return None
        
    except Exception as e:
        logging.error(f"Error getting 10-K accession: {str(e)}")
        return None

def get_exhibit_21_url(cik, accession):
    """Get the URL for Exhibit 21 from a company's 10-K filing."""
    try:
        # Format CIK and accession number
        cik = str(cik).zfill(10)
        accession = accession.replace('-', '')
        
        # Construct the URL for the filing detail page
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/index.json"
        
        # Make the request with retry logic
        response = get_with_retry(url)
        if not response:
            return None
            
        # Parse the response
        data = response.json()
        
        # Find the Exhibit 21 file
        for file in data.get('directory', {}).get('item', []):
            if 'ex21' in file.get('name', '').lower():
                return f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession}/{file.get('name')}"
                
        return None
        
    except Exception as e:
        logging.error(f"Error getting Exhibit 21 URL: {str(e)}")
        return None

def parse_subsidiaries(url):
    """Parse subsidiaries from Exhibit 21"""
    try:
        response = get_with_retry(url)
        if not response:
            return []
            
        soup = BeautifulSoup(response.text, 'html.parser')
        subsidiaries = []
        
        # Try to find subsidiaries in tables
        for table in soup.find_all('table'):
            for row in table.find_all('tr'):
                cells = row.find_all(['td', 'th'])
                if cells:
                    for cell in cells:
                        text = cell.get_text().strip()
                        if text and len(text) > 2:
                            subsidiaries.append(text)
                            
        # If no subsidiaries found in tables, try parsing text
        if not subsidiaries:
            text = soup.get_text()
            lines = text.split('\n')
            for line in lines:
                line = line.strip()
                if line and len(line) > 2:
                    # Look for common patterns in subsidiary listings
                    if re.match(r'^[\s•]*[A-Z].*', line):
                        subsidiaries.append(line)
                        
        return list(set(subsidiaries))  # Remove duplicates
    except Exception as e:
        logger.error(f"Error parsing subsidiaries: {str(e)}")
        return []

def process_company(company_name, ticker):
    """Process a single company"""
    logger.info(f"Processing {company_name} ({ticker})")
    results = []
    
    try:
        cik = get_cik(ticker)
        if not cik:
            logger.error(f"Could not find CIK for {company_name}")
            return results
            
        # Process each year from 2018 to current
        current_year = datetime.now().year
        for year in range(2018, current_year + 1):
            logger.info(f"Processing year {year}")
            
            accession = get_10k_accession(cik, year)
            if not accession:
                logger.warning(f"No 10-K filing found for {year}")
                continue
                
            url = get_exhibit_21_url(cik, accession)
            if not url:
                logger.warning(f"No Exhibit 21 found for {year}")
                continue
                
            subsidiaries = parse_subsidiaries(url)
            if subsidiaries:
                for subsidiary in subsidiaries:
                    results.append({
                        'company': company_name,
                        'year': year,
                        'subsidiary': subsidiary
                    })
                logger.info(f"Found {len(subsidiaries)} subsidiaries for {year}")
                
    except Exception as e:
        logger.error(f"Error processing {company_name}: {str(e)}")
        
    return results

def save_results(results: List[Dict[str, Any]], company_name: str) -> None:
    """Save results to Excel with each year in a separate sheet"""
    try:
        # Create subsidiaries directory if it doesn't exist
        os.makedirs('subsidiaries', exist_ok=True)
        
        # Sanitize company name for filename
        safe_name = re.sub(r'[^\w\-_\. ]', '_', company_name)
        filename = f'subsidiaries/{safe_name}.xlsx'
        
        # Convert to DataFrame
        df = pd.DataFrame(results)
        
        if not df.empty:
            # Create Excel writer
            with pd.ExcelWriter(filename, engine='openpyxl') as writer:
                # Group by year and save each year to a separate sheet
                for year, year_data in df.groupby('year'):
                    # Sort subsidiaries alphabetically
                    year_data = year_data.sort_values('subsidiary')
                    
                    # Create sheet name (max 31 characters as per Excel limitation)
                    sheet_name = f'{year}'
                    if len(sheet_name) > 31:
                        sheet_name = sheet_name[:31]
                    
                    # Save to sheet
                    year_data.to_excel(writer, sheet_name=sheet_name, index=False)
                    
                    # Auto-adjust column widths
                    worksheet = writer.sheets[sheet_name]
                    for idx, col in enumerate(year_data.columns):
                        max_length = max(
                            year_data[col].astype(str).apply(len).max(),
                            len(str(col))
                        )
                        worksheet.column_dimensions[chr(65 + idx)].width = min(max_length + 2, 50)
            
            logger.info(f"Saved {len(results)} subsidiaries to {filename}")
        else:
            logger.warning(f"No subsidiaries found for {company_name}")
            
    except Exception as e:
        logger.error(f"Error saving results for {company_name}: {str(e)}")

def main():
    """Main function"""
    print("Starting script...")
    
    # Read companies from CSV
    companies_df = pd.read_csv('companies.csv')
    total_companies = len(companies_df)
    print(f"Found {total_companies} companies to process")
    
    # Process each company
    for index, row in companies_df.iterrows():
        print(f"\nProcessing company {index + 1}/{total_companies}: {row['company_name']}")
        results = process_company(row['company_name'], row['ticker'])
        save_results(results, row['company_name'])
        print(f"Completed processing {row['company_name']}")
        time.sleep(1)  # Add delay between companies

if __name__ == "__main__":
    main() 