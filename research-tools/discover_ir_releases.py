"""Probe predictable issuer-owned release URLs; save only confirmed source packets.

This deliberately extracts no unverified numeric facts. A new official release
unlocks a source-limited Analysis; an editor can enrich the packet later.
"""
from __future__ import annotations

import html
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORDS = {1: "first", 2: "second", 3: "third", 4: "fourth"}


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "nav", "footer"):
            self.hidden += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style", "nav", "footer"):
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden and data.strip():
            self.parts.append(html.unescape(data.strip()))


def urls(ticker, year, quarter):
    if ticker == "ASML":
        return [f"https://investor.asml.com/news-releases/news-release-details/q{quarter}-{year}-financial-results"]
    if ticker == "SMSN":
        base = f"https://news.samsung.com/global/samsung-electronics-announces-{WORDS[quarter]}-quarter"
        return [f"{base}-{year}-results", f"{base}-and-fy-{year}-results"]
    if ticker == "SKHX":
        return [f"https://news.skhynix.com/en/sk-hynix-announces-{quarter}q{str(year)[2:]}-financial-results/",
                f"https://news.skhynix.com/en/sk-hynix-announces-fy{str(year)[2:]}-financial-results/"]
    if ticker == "NBIS":
        base = "https://nebius.com/newsroom/"
        return [base + f"nebius-reports-{WORDS[quarter]}-quarter-{year}-financial-results",
                base + f"nebius-reports-{WORDS[quarter]}-quarter-and-full-year-{year}-financial-results",
                base + f"nebius-group-n-v-announces-{WORDS[quarter]}-quarter-{year}-financial-results"]
    return []


def probe(url, year, quarter):
    request = urllib.request.Request(url, headers={"User-Agent": "EarningsDatabaseResearch/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=12) as response:
            if "html" not in response.headers.get("Content-Type", ""):
                return None
            body = response.read(1_000_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return None
    parser = VisibleText()
    parser.feed(body)
    text = re.sub(r"\s+", " ", " ".join(parser.parts))
    qword = WORDS[quarter]
    if str(year) not in text[:10000] or not re.search(r"financial results|quarterly results|quarter.*results", text[:10000], re.I):
        return None
    if not (f"Q{quarter}" in text[:10000] or qword in text[:10000].lower() or f"{quarter}Q" in text[:10000]):
        return None
    published = re.search(r'"datePublished"\s*:\s*"(\d{4}-\d{2}-\d{2})', body)
    return {"url": url, "published": published.group(1) if published else None,
            "excerpt": text[:900]}


def save(ticker, year, quarter, result):
    q = f"{year}Q{quarter}"
    folder = ROOT / "database" / ticker / "earnings" / q
    target = folder / "materials" / "analysis.json"
    if target.exists():
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    packet = {"ticker": ticker, "calendar_quarter": q, "cutoff": now,
              "sources": [result["url"]],
              "facts": [f"Official {ticker} {q} results announcement is available. Numeric results and guidance remain to be checked against the source."],
              "official_release_confirmed": True, "verification_status": "official_release_discovered",
              "source_excerpt_for_review": result["excerpt"],
              "note": "Official issuer announcement found automatically; financial values are not extracted or verified."}
    target.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (target.parent / "README.md").write_text(
        f"# {ticker} {q} 官方公告\n\n[财报原件]({result['url']})\n\n"
        "财务数字待核。自动发现仅确认公司官网存在当季公告。\n", encoding="utf-8")
    if result["published"] and not (folder / "event.json").exists():
        (folder / "event.json").write_text(json.dumps({"ticker": ticker, "quarter": q,
            "earnings_date": result["published"], "date_basis": "official_published_metadata"},
            ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return True


def main():
    today = date.today()
    for ticker in ("ASML", "SMSN", "SKHX", "NBIS"):
        for year in range(2025, today.year + 1):
            for quarter in range(1, 5):
                target = ROOT / "database" / ticker / "earnings" / f"{year}Q{quarter}" / "materials" / "analysis.json"
                if target.exists():
                    continue
                for url in urls(ticker, year, quarter):
                    result = probe(url, year, quarter)
                    if result:
                        print(ticker, year, quarter, save(ticker, year, quarter, result), flush=True)
                        break


if __name__ == "__main__":
    main()
