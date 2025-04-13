# SEC Subsidiaries Scraper

A Python script to scrape subsidiary information from SEC 10-K filings.

## Description

This script automates the process of extracting subsidiary information from SEC 10-K filings. It:
- Looks up company CIK numbers from ticker symbols
- Retrieves 10-K filings for specified years
- Extracts Exhibit 21 (subsidiaries) information
- Generates an Excel file with one sheet per year

## Requirements

- Python 3.7+
- Required packages listed in `requirements.txt`

## Installation

1. Clone this repository:
```bash
git clone [your-repository-url]
cd sec-subsidiaries-scraper
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

## Usage

1. Update the `HEADERS` dictionary in `sec_subsidiaries.py` with your information:
```python
HEADERS = {
    'User-Agent': 'Your Name your.email@example.com'
}
```

2. Run the script:
```bash
python sec_subsidiaries.py
```

## Example

```python
extract_subsidiaries_for_company("EMN", "EASTMAN CHEMICAL CO")
```

This will create an Excel file named "EASTMAN_CHEMICAL_CO.xlsx" with subsidiary information from 2018-2024.

## Features

- Automatic CIK lookup
- Multi-year data extraction
- Error handling and logging
- Rate limiting to respect SEC guidelines
- Excel output with yearly sheets

## License

MIT License 