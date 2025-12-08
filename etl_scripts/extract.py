import logging
from typing import Iterator
import os
import pandas as pd
import glob
from lxml import etree
from pathlib import Path

logger = logging.getLogger(__name__)

# Data had to be chunked to prevent memory crashes or freezes
FI_DATA_PATH = os.getenv("FI_DATA_PATH", "xml_files")
OUTPUT_CSV = "swedish_funds_complete.csv"
CHUNKSIZE = 100_000

def parse_fi_holdings(xml_file: str) -> pd.DataFrame:
    holdings = []
    try:
        tree = etree.parse(xml_file)
        root = tree.getroot()
        ns = {'fi': 'http://schemas.fi.se/publika/vardepappersfonder/20200331'}
        
        fund_name = root.xpath('.//fi:Fond_namn/text()', namespaces=ns)
        fund_isin = root.xpath('.//fi:Fond_ISIN-kod/text()', namespaces=ns)
        quarter_end = root.xpath('.//fi:Kvartalsslut/text()', namespaces=ns)
        
        if not fund_name:
            return pd.DataFrame()
        # Defined safe traversal of the xml tree
        def safe_xpath(element, xpath_expr):
            res = element.xpath(xpath_expr, namespaces=ns)
            return res[0] if res else ''
        
        for inst in root.xpath('.//fi:FinansielltInstrument', namespaces=ns):
            holdings.append({
                'quarter': Path(xml_file).parent.parent.name,
                'fund_name': fund_name[0],
                'fund_isin': fund_isin[0] if fund_isin else '',
                'quarter_end': quarter_end[0] if quarter_end else '',
                'isin': safe_xpath(inst, 'fi:ISIN-kod_instrument/text()'),
                'name': safe_xpath(inst, 'fi:Instrumentnamn/text()'),
                'country': safe_xpath(inst, 'fi:Landkod_Emittent/text()'),
                'currency': safe_xpath(inst, 'fi:Valuta/text()'),
                'shares': float(safe_xpath(inst, 'fi:Antal/text()') or 0),
                'market_value_sek': float(safe_xpath(inst, 'fi:Marknadsvärde_instrument/text()') or 0),
                'weight_pct': float(safe_xpath(inst, 'fi:Andel_av_fondförmögenhet_instrument/text()') or 0)
            })
    except Exception as e:
        logger.error(f"Error parsing {xml_file}: {e}")
        return pd.DataFrame()
    
    return pd.DataFrame(holdings)

def extract_holdings() -> Iterator[pd.DataFrame]:
    xml_files = glob.glob(f"{FI_DATA_PATH}/**/*.xml", recursive=True)
    logger.info(f"Found {len(xml_files)} FI XML files")
    
    all_dfs = []
    for xml_file in xml_files:
        df = parse_fi_holdings(xml_file)
        if not df.empty:
            all_dfs.append(df)
    
    if all_dfs:
        full_df = pd.concat(all_dfs, ignore_index=True)
        full_df.to_csv(OUTPUT_CSV, index=False)
        logger.info(f"Saved {len(full_df):,} holdings to {OUTPUT_CSV}")
        
        for i in range(0, len(full_df), CHUNKSIZE):
            yield full_df.iloc[i:i+CHUNKSIZE]
    else:
        logger.warning("No holdings extracted")

if __name__ == "__main__":
    chunks = list(extract_holdings())
    total_rows = sum(len(chunk) for chunk in chunks)
    print(f"Extracted {total_rows:,} holdings in {len(chunks)} chunks")


extract_data = extract_holdings
