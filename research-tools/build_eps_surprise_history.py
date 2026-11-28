"""Build dated, sourced EPS surprise JSON from public website tables.

Source extracts are captured snapshots of visible MarketBeat/Investing.com
tables. No private API or model-generated estimates are used.
"""
from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
START = date(2024, 11, 26)
END = date(2026, 11, 26)
EXTRACTED = '2026-11-26'
INVESTING = {'ASML', 'SNDK', 'STX', 'WDC', 'SKHX', 'SMSN'}
FISCAL_RE = re.compile(r'Q([1-4])\s+(20\d{2})')


def number(value: str) -> Decimal | None:
    value = value.strip().replace(',', '').replace('$', '').replace('/', '')
    if value in {'', '-', '--'}:
        return None
    return Decimal(value)


def next_quarter(quarter: str, offset: int) -> str:
    y, q = int(quarter[:4]), int(quarter[-1])
    n = y * 4 + q - 1 + offset
    return f'{n // 4}Q{n % 4 + 1}'


def parse_marketbeat(row: str) -> dict:
    cells = [x.strip() for x in row.split('|')]
    fiscal = FISCAL_RE.search(cells[1])
    return {'report_date': datetime.strptime(cells[0], '%m/%d/%Y').date(),
            'source_fiscal_quarter': f'{fiscal.group(2)}Q{fiscal.group(1)}' if fiscal else None,
            'consensus': number(cells[2]), 'actual': number(cells[3]),
            'currency': 'USD'}


def parse_investing(row: str, ticker: str) -> dict:
    cells = [x.strip() for x in row.split('|')]
    period = datetime.strptime(cells[1], '%m/%Y').date()
    return {'report_date': datetime.strptime(cells[0], '%b %d, %Y').date(),
            'source_fiscal_quarter': f'{period.year}Q{(period.month - 1) // 3 + 1}',
            'consensus': number(cells[3]), 'actual': number(cells[2]),
            'currency': 'KRW' if ticker in {'SKHX', 'SMSN'} else 'USD'}


def event_quarter(ticker: str, row: dict, events: list[dict]) -> str:
    dated = []
    for event in events:
        if event['ticker'] == ticker and event.get('date'):
            d = date.fromisoformat(event['date'])
            dated.append((abs((row['report_date'] - d).days), d, event['quarter']))
    if dated:
        distance, _, quarter = min(dated)
        if distance <= 35:
            return quarter
        first = min(dated, key=lambda x: x[1])
        last = max(dated, key=lambda x: x[1])
        if row['report_date'] < first[1]:
            return next_quarter(first[2], -1)
        if row['report_date'] > last[1]:
            return next_quarter(last[2], 1)
    if row['source_fiscal_quarter']:
        return row['source_fiscal_quarter']
    raise ValueError(f'Cannot map {ticker} {row["report_date"]}')


def printable(value: Decimal | None):
    return float(value) if value is not None else None


def build() -> dict:
    marketbeat = json.loads((ROOT / 'data/eps_source_extract_20241126_20261126.json').read_text(encoding='utf-8'))['marketbeat']
    investing = json.loads((ROOT / 'data/eps_investing_extract_20241126_20261126.json').read_text(encoding='utf-8'))
    index = json.loads(subprocess.check_output(['git', 'show', 'HEAD:data/library_index.json'], cwd=ROOT))
    events = index['events']
    counts = {}
    review = []
    for ticker in sorted(marketbeat):
        packet = investing[ticker] if ticker in INVESTING else marketbeat[ticker]
        parser = (lambda x: parse_investing(x, ticker)) if ticker in INVESTING else parse_marketbeat
        rows = [parser(x) for x in packet['rows']]
        rows = [x for x in rows if START <= x['report_date'] <= END and x['actual'] is not None]
        # One public report per release date/quarter. Prefer a row with consensus.
        selected = {}
        for row in rows:
            q = event_quarter(ticker, row, events)
            if q not in selected or (selected[q]['consensus'] is None and row['consensus'] is not None):
                selected[q] = row
        counts[ticker] = len(selected)
        for quarter, row in selected.items():
            actual, consensus = row['actual'], row['consensus']
            issue = None
            if consensus is None:
                issue = 'No comparable pre-release EPS consensus in cited table.'
            diff = actual - consensus if actual is not None and consensus is not None else None
            result = ('beat' if diff > 0 else 'miss' if diff < 0 else 'in_line') if diff is not None else 'unavailable'
            pct = (diff / abs(consensus) * 100) if diff is not None and consensus != 0 else None
            payload = {
                'ticker': ticker, 'quarter': quarter,
                'report_date': row['report_date'].isoformat(),
                'source_reported_period': row['source_fiscal_quarter'],
                'source_period_type': 'period_end_calendar_quarter' if ticker in INVESTING else 'fiscal_quarter',
                'currency': row['currency'], 'eps_basis': 'website reported EPS and consensus; same table',
                'actual_eps': printable(actual), 'consensus_eps': printable(consensus),
                'difference': printable(diff),
                'surprise_pct': float(pct.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)) if pct is not None else None,
                'result': result, 'source_url': packet['url'],
                'source_name': 'Investing.com' if ticker in INVESTING else 'MarketBeat',
                'verified_at': EXTRACTED, 'review_note': issue,
            }
            if (ticker, quarter) == ('NBIS', '2025Q1'):
                # Both displayed values come from the same dated TipRanks report.
                payload.update(report_date='2025-05-20', source_reported_period='2025Q1',
                               actual_eps=-0.42, consensus_eps=-0.48, difference=0.06,
                               surprise_pct=12.50, result='beat',
                               source_url='https://www.tipranks.com/stocks/nbis/earnings/q1-2025-report',
                               source_name='TipRanks', eps_basis='TipRanks displayed rounded EPS and consensus; same report',
                               review_note='Displayed EPS is rounded to cents; calculated surprise uses displayed values.',
                               review_status='resolved', verified_at='2026-11-28')
                issue = None
            elif (ticker, quarter) == ('SMSN', '2025Q1'):
                # Investing.com has a 1.19-vs-737.27 KRW unit error and a late date.
                payload.update(report_date='2025-04-30', source_reported_period='2025Q1',
                               actual_eps=1192.0, consensus_eps=863.5, difference=328.5,
                               surprise_pct=38.04, result='beat',
                               source_url='https://www.tipranks.com/stocks/kr:005930/earnings/q1-2025-report',
                               source_name='TipRanks', eps_basis='KRW per ordinary share; same dated report',
                               supporting_source_urls=['https://images.samsung.com/is/content/samsung/assets/global/ir/docs/2025_1Q_conference_eng.pdf'],
                               review_note='Issuer presentation independently confirms actual EPS KRW 1,192; erroneous Investing.com row excluded.',
                               review_status='resolved', verified_at='2026-11-28')
                issue = None
            elif (ticker, quarter) == ('SNDK', '2024Q4'):
                payload.update(eps_basis='No comparable standalone pre-release EPS consensus',
                               supporting_source_urls=['https://investor.sandisk.com/news-releases/news-release-details/sandisk-celebrates-nasdaq-listing-after-completing-separation'],
                               review_note='Investing.com shows no forecast. Sandisk began standalone trading on February 24, 2025, two days before this reported row; no comparable pre-release standalone consensus established.',
                               review_status='resolved_unavailable', verified_at='2026-11-28')
                issue = None
            out = ROOT / 'database' / ticker / 'earnings' / quarter / 'eps-surprise.json'
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            if issue:
                review.append(f'{ticker}_{quarter}: {issue}')
    return {'scope_start': START.isoformat(), 'scope_end': END.isoformat(),
            'companies': len(counts), 'records': sum(counts.values()),
            'by_company': counts, 'review_items': review}


if __name__ == '__main__':
    summary = build()
    (ROOT / 'data/eps_surprise_coverage.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(summary, ensure_ascii=False, indent=2))
