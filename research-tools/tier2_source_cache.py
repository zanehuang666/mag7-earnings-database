"""Cache official HTML filings for repeatable second-tier report research."""
import argparse
import json
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache" / "tier2"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Earnings research contact research-team@example.org"})


def download(ticker):
    path = ROOT / "database" / ticker / "html-research" / "data" / "sources.json"
    sources = json.loads(path.read_text(encoding="utf-8"))["records"]
    folder = CACHE / ticker
    folder.mkdir(parents=True, exist_ok=True)
    results = []
    for source in sources:
        sid = source["source_id"]
        url = source.get("url") or ""
        if urlparse(url).scheme != "https":
            continue
        target = folder / f"{sid}.html"
        if target.exists() and target.stat().st_size > 1000:
            results.append((sid, "cached", target.stat().st_size))
            continue
        try:
            response = SESSION.get(url, timeout=35)
            response.raise_for_status()
            target.write_bytes(response.content)
            results.append((sid, "downloaded", len(response.content)))
        except Exception as exc:
            results.append((sid, "failed", str(exc)[:100]))
        time.sleep(0.3)
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("tickers", nargs="+")
    args = parser.parse_args()
    for ticker in args.tickers:
        rows = download(ticker)
        print(ticker, len(rows), sum(r[1] != "failed" for r in rows), [r for r in rows if r[1] == "failed"])
