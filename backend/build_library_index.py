"""Derive the public calendar/library view from company files, never stale prose JSON."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST = {"MSFT", "AAPL", "AMZN", "META", "GOOGL", "TSLA", "ORCL", "SPACEX", "NVDA", "AVGO", "AMD", "MU", "INTC", "SKHX", "SMSN"}
SECOND = {"CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML"}
NAMES = {"MSFT": "Microsoft", "AAPL": "Apple", "AMZN": "Amazon", "META": "Meta", "GOOGL": "Alphabet", "TSLA": "Tesla", "ORCL": "Oracle",
         "SPACEX": "SpaceX", "NVDA": "NVIDIA", "AVGO": "Broadcom", "AMD": "AMD", "MU": "Micron",
         "INTC": "Intel", "SKHX": "SK hynix", "SMSN": "Samsung Electronics", "CRWV": "CoreWeave",
         "NBIS": "Nebius", "SNDK": "SanDisk", "WDC": "Western Digital", "STX": "Seagate",
         "AMAT": "Applied Materials", "CSCO": "Cisco", "LRCX": "Lam Research", "ASML": "ASML"}


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def relative(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def summary(markdown: str) -> str:
    paragraphs = []
    for block in re.split(r"\n\s*\n", markdown):
        block = block.strip()
        if not block or block.startswith(("#", "|", "-", "1.", "2.", "3.")):
            continue
        plain = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", block)
        plain = re.sub(r"[*`>]", "", plain).replace("\n", " ")
        if len(plain) > 25:
            paragraphs.append(plain)
    return (paragraphs[0][:155] + ("…" if len(paragraphs[0]) > 155 else "")) if paragraphs else "暂无正文摘要"


def match_event(ticker: str, quarter: str, release_date: str | None, calendar: list[dict], old_index: dict):
    for event_id, item in old_index.items():
        if item.get("ticker") == ticker and item.get("quarter") == quarter:
            return event_id, item.get("date")
    if release_date:
        candidates = [e for e in calendar if e.get("ticker") == ticker and e.get("date")]
        target = datetime.fromisoformat(release_date[:10]).date()
        ranked = sorted(candidates, key=lambda e: abs((datetime.fromisoformat(e["date"][:10]).date() - target).days))
        if ranked and abs((datetime.fromisoformat(ranked[0]["date"][:10]).date() - target).days) <= 45:
            return ranked[0]["id"], ranked[0]["date"]
    return f"library-{ticker.lower()}-{quarter.lower()}", release_date


def build():
    calendar = load(ROOT / "data" / "mag7.json", {}).get("calendar", {}).get("formal", {}).get("events", [])
    old_index = load(ROOT / "data" / "research_index.json", {}).get("events", {})
    records = []
    for company_folder in sorted((ROOT / "database").iterdir()):
        ticker = company_folder.name
        if ticker not in FIRST | SECOND:
            continue
        html = company_folder / "html-research" / "output" / "overview.html"
        for folder in sorted((company_folder / "earnings").glob("20*Q*")):
            if folder.name[:4] < "2025":
                continue
            event = load(folder / "event.json", {})
            release_date = event.get("earnings_date") or event.get("release_date")
            stages = {}
            for stage in ("preview", "analysis"):
                md = folder / "analysis" / f"{stage}.md"
                meta = load(folder / "analysis" / f"{stage}.meta.json", {})
                packet_path = folder / "materials" / f"{stage}.json"
                packet = load(packet_path, {})
                adopted = meta.get("status") not in ("rejected", "superseded") and md.exists()
                stages[stage] = {
                    "status": (meta.get("status") or "manual") if adopted else ("source_ready" if packet.get("sources") else "unavailable"),
                    "path": relative(md) if adopted else None,
                    "source_packet": relative(packet_path) if packet_path.exists() else None,
                    "summary": summary(md.read_text(encoding="utf-8")) if adopted else "",
                    "cutoff": meta.get("cutoff") or packet.get("cutoff"),
                    "generated_at": meta.get("generated_at"),
                    "historical_reconstruction": bool(meta.get("historical_reconstruction") or packet.get("historical_reconstruction")),
                    "versions": [relative(x) for x in sorted((folder / "analysis" / "history").glob(f"{stage}-*.md"))],
                }
            event_id, matched_date = match_event(ticker, folder.name, release_date, calendar, old_index)
            date = matched_date
            date = date[:10] if date else None
            records.append({"id": event_id, "ticker": ticker, "company": NAMES[ticker],
                            "tier": 1 if ticker in FIRST else 2, "quarter": folder.name, "date": date,
                            "date_basis": "calendar" if event_id in {e["id"] for e in calendar} else "filing_or_source_cutoff",
                            "released": bool(load(folder / "materials" / "analysis.json", {}).get("official_release_confirmed")),
                            "folder": relative(folder), "html_path": relative(html) if html.exists() else None,
                            "stages": stages})
    result = {"schema_version": 1, "generated_at": datetime.now(timezone.utc).isoformat(),
              "companies": [{"ticker": t, "company": NAMES[t], "tier": 1 if t in FIRST else 2,
                             "html_path": relative(ROOT / "database" / t / "html-research" / "output" / "overview.html")
                             if (ROOT / "database" / t / "html-research" / "output" / "overview.html").exists() else None,
                             "candidate_path": relative(ROOT / "database" / t / "html-research" / "output" / "auto-update-candidate.html")
                             if (ROOT / "database" / t / "html-research" / "output" / "auto-update-candidate.html").exists() else None}
                            for t in sorted(FIRST | SECOND)],
              "events": records}
    output = ROOT / "data" / "library_index.json"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


if __name__ == "__main__":
    built = build()
    print(f"indexed {len(built['companies'])} companies and {len(built['events'])} quarters")
