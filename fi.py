from lxml import etree
import pandas as pd
import glob
import os

def parse_fi_holdings(xml_file):
    holdings = []
    try:
        tree = etree.parse(xml_file)
        root = tree.getroot()
        ns = {'fi': 'http://schemas.fi.se/publika/vardepappersfonder/20200331'}
        
        fund_company = root.xpath('.//fi:Fondbolag_namn/text()', namespaces=ns)
        fund_name = root.xpath('.//fi:Fond_namn/text()', namespaces=ns)
        fund_isin = root.xpath('.//fi:Fond_ISIN-kod/text()', namespaces=ns)
        quarter_end = root.xpath('.//fi:Kvartalsslut/text()', namespaces=ns)
        
        if not fund_name:
            return pd.DataFrame()
        
        def safe_xpath(element, xpath_expr):
            res = element.xpath(xpath_expr, namespaces=ns)
            return res[0] if res else ''
        
        for inst in root.xpath('.//fi:FinansielltInstrument', namespaces=ns):
            holdings.append({
                'quarter': os.path.basename(os.path.dirname(os.path.dirname(xml_file))),
                'fund_company': fund_company[0] if fund_company else '',
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
        print(f"Error parsing {xml_file}: {e}")
        return pd.DataFrame()
    return pd.DataFrame(holdings)

if __name__ == "__main__":
    output_file = 'swedish_funds_complete.csv'
    
    xml_files = glob.glob('**/*.xml', recursive=True)
    print(f"Found {len(xml_files)} XML files")
    
    dfs = []
    success = 0
    for f in xml_files:
        df = parse_fi_holdings(f)
        if not df.empty:
            dfs.append(df)
            success += 1
        else:
            print(f"Skipped {f}")
    
    print(f"Successfully parsed {success} files")
    
    if dfs:
        all_holdings = pd.concat(dfs, ignore_index=True)
        all_holdings.to_csv(output_file, index=False)
        print(f"Saved {len(all_holdings)} holdings to {output_file}")
        print(f"{all_holdings['fund_name'].nunique()} funds from {all_holdings['fund_company'].nunique()} companies")
