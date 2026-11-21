"""Keep original SEC evidence for FY2021-2024 HTML research history.

This creates source packets, not completed chart data or validated HTML.
Later quarters are already under each company's earnings/materials folder.
"""
from __future__ import annotations

import concurrent.futures
import json
from pathlib import Path

from collect_sec_quarters import FIRST, SECOND, TAGS, fetch, files_for_ticker, metric

ROOT = Path(__file__).resolve().parents[1]


def collect(ticker, cik):
    _, _, rows = files_for_ticker(ticker, cik)
    selected = {}
    for row in rows:
        end = row.get("reportDate", "")
        if row.get("form") in ("10-Q", "10-K") and "2021-01-01" <= end < "2025-01-01":
            selected.setdefault(end, row)
    if not selected:
        return ticker, 0
    facts = fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    out = ROOT / "database" / ticker / "html-research" / "materials" / "official-filings"
    count = 0
    for end, row in sorted(selected.items()):
        q = f"{end[:4]}Q{(int(end[5:7]) - 1) // 3 + 1}"
        md = out / f"{q}.md"
        if md.exists():
            continue
        accn = row["accessionNumber"]
        values = [metric(facts, accn, end, row["form"], label) for label in TAGS]
        values = [v for v in values if v]
        if not values:
            continue
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accn.replace('-', '')}/{row['primaryDocument']}"
        out.mkdir(parents=True, exist_ok=True)
        md.write_text(f"# {ticker} {q} HTML 历史原始资料\n\n"
                      f"- 报告期末：{end}\n- 申报日期：{row['filingDate']}\n"
                      f"- 表格：{row['form']}\n- [SEC 原件]({url})\n\n"
                      + "\n".join("- " + v for v in values)
                      + "\n\n10-K 数值为全年，不能当作第四季度单季。\n",
                      encoding="utf-8")
        count += 1
    return ticker, count


def main():
    tickers = fetch("https://www.sec.gov/files/company_tickers.json")
    mapping = {x["ticker"]: x["cik_str"] for x in tickers.values()}
    work = [(ticker, mapping[ticker]) for ticker in sorted(FIRST | SECOND) if ticker in mapping]
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
        for future in concurrent.futures.as_completed([executor.submit(collect, *item) for item in work]):
            try:
                print(future.result(), flush=True)
            except Exception as exc:
                print("ERROR", repr(exc), flush=True)


if __name__ == "__main__":
    main()
