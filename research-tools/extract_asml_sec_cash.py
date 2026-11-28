"""Audit ASML quarter cash flow from issuer 6-K financial statement exhibits."""
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import requests
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'database/ASML/html-research/checks/sec-quarterly-cash-extraction.json'
HEADERS = {'User-Agent': 'earnings-research-tool/1.0 (research bot)'}
SESSION = requests.Session()
BASE = 'https://www.sec.gov/Archives/edgar/data/937966/'


def get(url):
    response = SESSION.get(url, headers=HEADERS, timeout=35)
    response.raise_for_status()
    return response


def row(entry):
    date_str, accession, period = entry
    folder = BASE + accession.replace('-', '') + '/'
    result = {'period_id': period, 'filing_date': date_str, 'filing_url': folder, 'status': 'missing_exhibit'}
    try:
        items = get(folder + 'index.json').json()['directory']['item']
        names = [x['name'] for x in items if x['name'].endswith(('.htm', '.html'))]
        matches = [n for n in names if ('financial' in n.lower() and ('statement' in n.lower() or 'result' in n.lower()))]
        for name in matches:
            url = folder + name
            text = BeautifulSoup(get(url).text, 'html.parser').get_text(' ', strip=True)
            cash = re.search(r'Net cash provided by \(used in\) operating activities\s+((?:\(?-?[\d,]+\.\d+\)?\s+){2,4})', text, re.I)
            ppe = re.search(r'Purchase[s]? of property, plant and equipment\s+((?:\(?-?[\d,]+\.\d+\)?\s+){2,4})', text, re.I)
            intangible = re.search(r'Purchase[s]? of intangible assets\s+((?:\(?-?[\d,]+\.\d+\)?\s+){2,4})', text, re.I)
            def values(match):
                return re.findall(r'\(?-?[\d,]+\.\d+\)?', match.group(1)) if match else []
            if cash and ppe and len(values(cash)) >= 2 and len(values(ppe)) >= 2:
                heading_start = text.rfind('Three months ended', 0, cash.start())
                result.update(status='extracted', source_url=url, cash_flow_values=values(cash), ppe_values=values(ppe),
                              intangible_values=values(intangible),
                              cash_locator='Consolidated Statements of Cash Flows, three months ended',
                              date_context=text[heading_start:heading_start+230] if heading_start >= 0 else None)
                break
    except Exception as exc:
        result['error'] = str(exc)[:180]
    return result


def main():
    data = get('https://data.sec.gov/submissions/CIK0000937966.json').json()['filings']['recent']
    entries = []
    for i, form in enumerate(data['form']):
        if form != '6-K' or data['primaryDocument'][i] != 'form6-kquarterlyfilings.htm':
            continue
        d = datetime.strptime(data['filingDate'][i], '%Y-%m-%d')
        quarter = {1: 4, 4: 1, 7: 2, 10: 3}.get(d.month)
        year = d.year - (d.month == 1)
        if quarter and (year > 2020 or year == 2020 and quarter == 4) and year <= 2026:
            entries.append((data['filingDate'][i], data['accessionNumber'][i], f'{year}Q{quarter}'))
    entries = sorted({e[2]: e for e in entries}.values(), key=lambda e: e[2])
    with ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(row, entries))
    OUT.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('quarters', len(rows), 'extracted', sum(x['status'] == 'extracted' for x in rows))
    print([(x['period_id'], x['status']) for x in rows])


if __name__ == '__main__':
    main()
