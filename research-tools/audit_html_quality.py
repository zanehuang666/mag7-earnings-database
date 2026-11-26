"""Audit whether public company HTML reports plot multiple quarters and profit."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROFIT_FIELDS = {'op', 'opIncome', 'operatingIncome', 'operatingProfit', 'netIncome', 'profit'}
REVENUE_FIELDS = {'revenue', 'rev'}


def report(ticker: str) -> dict:
    path = ROOT / 'database' / ticker / 'html-research/output/overview.html'
    row = {'ticker': ticker, 'html_path': str(path.relative_to(ROOT)).replace('\\', '/'),
           'exists': path.exists(), 'revenue_points': 0, 'profit_points': 0, 'axis_quarters': 0,
           'issues': ['missing_html'] if not path.exists() else []}
    if not path.exists():
        return row
    text = path.read_text(encoding='utf-8')
    marker = 'window.REPORT_DATA='
    if marker in text:
        model, _ = json.JSONDecoder().raw_decode(text[text.index(marker) + len(marker):])
        charts = {chart['id']: chart for chart in model['charts']}
        def count(ids):
            return sum(any(series['values'][i] is not None for cid in ids for series in charts[cid]['series'])
                       for i in range(len(model['quarters'])))
        row['axis_quarters'] = len(model['quarters'])
        row['revenue_points'] = count(['g1'])
        row['profit_points'] = count(['g3', 'g6'])
    else:
        parsed = []
        for marker in ('const D=', 'const R='):
            if marker not in text:
                continue
            try:
                value, _ = json.JSONDecoder().raw_decode(text[text.index(marker) + len(marker):])
                records = value if isinstance(value, list) else value.get('rows', value.get('dataset', []))
                parsed.extend(item for item in records if isinstance(item, dict) and re.fullmatch(r'20\d{2}Q[1-4]', str(item.get('q'))))
                if parsed:
                    break
            except (json.JSONDecodeError, AttributeError):
                pass
        if not parsed:
            for match in re.finditer(r'\{[^{}]*"q":"20\d{2}Q[1-4]"[^{}]*\}', text):
                try:
                    parsed.append(json.loads(match.group()))
                except json.JSONDecodeError:
                    continue
        quarters = {item['q'] for item in parsed}
        row['axis_quarters'] = len(quarters)
        row['revenue_points'] = len({item['q'] for item in parsed if any(isinstance(item.get(k), (int, float)) for k in REVENUE_FIELDS)})
        row['profit_points'] = len({item['q'] for item in parsed if any(isinstance(item.get(k), (int, float)) for k in PROFIT_FIELDS)})
    row['issues'] = (["missing_html"] if not row['exists'] else
                     (["one_or_no_revenue_quarter"] if row['revenue_points'] <= 1 else []) +
                     (["no_profit_data"] if row['profit_points'] == 0 else []))
    return row


def main() -> None:
    index = json.loads((ROOT / 'data/library_index.json').read_text(encoding='utf-8'))
    companies = [company['ticker'] for company in index['companies']]
    rows = [report(ticker) for ticker in companies]
    result = {'generated_at': datetime.now(timezone.utc).isoformat(),
              'scope': '23 public companies; SpaceX shown separately as a private-company exception',
              'public_companies': len(companies) - 1,
              'public_company_issues': {row['ticker']: row['issues'] for row in rows if row['ticker'] != 'SPACEX' and row['issues']},
              'exception': 'SpaceX has no public quarterly earnings or profit series; no values were invented.',
              'companies': rows}
    out = ROOT / 'data/html_quality_audit.json'
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'companies': len(rows), 'public_issues': result['public_company_issues']}, ensure_ascii=False))


if __name__ == '__main__':
    main()
