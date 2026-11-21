"""Collect compact, auditable quarterly source packets from SEC filings.

The SEC companyfacts API supplies only facts whose accession matches the cited
filing. A 10-K is labelled annual; its facts are never presented as Q4 alone.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import time
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST = {"MSFT", "AMZN", "META", "GOOGL", "ORCL", "NVDA", "AVGO", "AMD", "MU", "INTC"}
SECOND = {"CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML"}
HEADERS = {"User-Agent": "EarningsDatabaseResearch zane.h.2500@gmail.com", "Accept": "application/json"}
TAGS = {
    "Revenue": ("RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"),
    "Operating income": ("OperatingIncomeLoss",),
    "Net income": ("NetIncomeLoss", "ProfitLoss"),
    "Operating cash flow": ("NetCashProvidedByUsedInOperatingActivities",),
}


def fetch(url: str) -> dict:
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(request, timeout=35) as response:
                return json.load(response)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(3 * (attempt + 1))
    raise AssertionError


def metric(facts: dict, accession: str, end: str, form: str, label: str):
    gaap = facts.get("facts", {}).get("us-gaap", {})
    for tag in TAGS[label]:
        for unit, entries in gaap.get(tag, {}).get("units", {}).items():
            if unit != "USD":
                continue
            choices = [x for x in entries if x.get("accn") == accession and x.get("end") == end
                       and x.get("form") == form and x.get("start")]
            if not choices:
                continue
            candidates = []
            for item in choices:
                days = (date.fromisoformat(end) - date.fromisoformat(item["start"])).days
                if form == "10-Q" and not 60 <= days <= 110:
                    continue
                if form == "10-K" and not 330 <= days <= 380:
                    continue
                candidates.append(item)
            if candidates:
                x = sorted(candidates, key=lambda y: y.get("filed", ""))[-1]
                period = "quarter" if form == "10-Q" else "full fiscal year, not Q4 alone"
                return f"{label}: USD {x['val']:,} ({period}; {x['start']} to {end}; US GAAP tag {tag})."
    return None


def files_for_ticker(ticker: str, cik: int) -> tuple[str, int, list[dict]]:
    number = str(cik).zfill(10)
    filings = fetch(f"https://data.sec.gov/submissions/CIK{number}.json")["filings"]
    recent = filings["recent"]
    rows = [{k: v[i] for k, v in recent.items()} for i in range(len(recent["form"]))]
    for older in filings.get("files", []):
        if older.get("filingFrom", "9999") <= f"{date.today().year}-12-31" and older.get("filingTo", "0000") >= "2024-01-01":
            extra = fetch("https://data.sec.gov/submissions/" + older["name"])
            rows.extend({k: v[i] for k, v in extra.items()} for i in range(len(extra["form"])))
    return ticker, cik, rows


def collect(ticker: str, cik: int) -> tuple[str, int]:
    ticker, cik, rows = files_for_ticker(ticker, cik)
    start_year = max(2025, int(os.getenv("RESEARCH_FROM_YEAR", "2025")))
    through_year = date.today().year
    forms = [r for r in rows if r.get("form") in ("10-Q", "10-K")
             and r.get("reportDate", "") >= f"{start_year - 1}-01-01"]
    forms.sort(key=lambda r: (r["reportDate"], r["filingDate"]))
    unique = {}
    for row in forms:
        unique.setdefault(row["reportDate"], row)
    ordered = list(unique.values())
    selected = [r for r in ordered if start_year <= int(r["reportDate"][:4]) <= through_year]
    if not selected:
        return ticker, 0
    facts = fetch(f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json")
    saved = 0
    for row in selected:
        end = row["reportDate"]
        quarter = f"{end[:4]}Q{(int(end[5:7]) - 1) // 3 + 1}"
        accession = row["accessionNumber"]
        url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}/{row['primaryDocument']}"
        observed = [metric(facts, accession, end, row["form"], label) for label in TAGS]
        found = [x for x in observed if x]
        if not found:
            continue
        folder = ROOT / "database" / ticker / "earnings" / quarter
        materials = folder / "materials"
        materials.mkdir(parents=True, exist_ok=True)
        event = {"ticker": ticker, "quarter": quarter, "period_end": end,
                 "release_date": row["filingDate"], "filing_form": row["form"], "official_filing_url": url,
                 "note": "SEC filing date may follow the earnings press release date."}
        if not (folder / "event.json").exists():
            (folder / "event.json").write_text(json.dumps(event, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        packet = {"ticker": ticker, "calendar_quarter": quarter, "cutoff": row["filingDate"] + "T23:59:59Z",
                  "sources": [url], "facts": found, "official_release_confirmed": True,
                  "verification_status": "official_filing_text_collected",
                  "note": "Numbers extracted from SEC XBRL for this accession. 10-K figures are annual, not Q4 standalone; source review pending."}
        if not (materials / "analysis.json").exists():
            (materials / "analysis.json").write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        previous = [r for r in ordered if r["reportDate"] < end and r["filingDate"] < row["filingDate"]]
        if previous and not (materials / "preview.json").exists():
            prior = previous[-1]
            prior_end = prior["reportDate"]
            prior_url = f"https://www.sec.gov/Archives/edgar/data/{cik}/{prior['accessionNumber'].replace('-', '')}/{prior['primaryDocument']}"
            prior_facts = [metric(facts, prior["accessionNumber"], prior_end, prior["form"], label) for label in TAGS]
            preview = {"ticker": ticker, "calendar_quarter": quarter,
                       "target_event_date": row["filingDate"], "cutoff": prior["filingDate"] + "T23:59:59Z",
                       "sources": [prior_url], "facts": [x for x in prior_facts if x],
                       "verification_status": "official_filing_text_collected", "historical_reconstruction": True,
                       "note": "Retrospective preview based only on the previous SEC filing; not a contemporaneous prediction."}
            if preview["facts"]:
                (materials / "preview.json").write_text(json.dumps(preview, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        readable = f"# {ticker} {quarter} SEC 原始资料\n\n- 报告期末：{end}\n- 申报日期：{row['filingDate']}\n- 表格：{row['form']}\n- [SEC 原件]({url})\n\n" + "\n".join(f"- {x}" for x in found) + "\n\n10-K 数值为全年值，不代表单独第四季度。\n"
        if not (materials / "README.md").exists():
            (materials / "README.md").write_text(readable, encoding="utf-8")
        saved += 1
    # Keep one forward Preview packet ready. It contains only the most recent
    # filed quarter; the earnings date remains unconfirmed until IR publishes it.
    latest = selected[-1]
    end = latest["reportDate"]
    month = int(end[5:7]) + 3
    next_year = int(end[:4]) + (month > 12)
    next_month = (month - 1) % 12 + 1
    next_quarter = f"{next_year}Q{(next_month - 1) // 3 + 1}"
    target = ROOT / "database" / ticker / "earnings" / next_quarter / "materials" / "preview.json"
    if not target.exists():
        prior_url = (f"https://www.sec.gov/Archives/edgar/data/{cik}/"
                     f"{latest['accessionNumber'].replace('-', '')}/{latest['primaryDocument']}")
        latest_facts = [metric(facts, latest["accessionNumber"], end, latest["form"], label) for label in TAGS]
        if any(latest_facts):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"ticker": ticker, "calendar_quarter": next_quarter,
                "cutoff": latest["filingDate"] + "T23:59:59Z", "sources": [prior_url],
                "facts": [x for x in latest_facts if x], "official_release_confirmed": False,
                "verification_status": "official_filing_text_collected",
                "note": "Forward preview using latest filed quarter; target release date awaits IR confirmation."
            }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ticker, saved


def main() -> None:
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
