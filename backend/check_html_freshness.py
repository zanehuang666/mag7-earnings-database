"""Track official quarter packets not yet reflected in each HTML data series."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load(path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def quarter(value):
    match = re.search(r"(20\d{2})Q([1-4])", str(value or ""), re.I)
    return int(match.group(1)) * 4 + int(match.group(2)) if match else None


def period_quarter(row):
    explicit = quarter(row.get("calendar_quarter"))
    if explicit:
        return explicit
    end = row.get("quarter_end")
    if end and re.match(r"20\d\d-\d\d-\d\d", end):
        return int(end[:4]) * 4 + ((int(end[5:7]) - 1) // 3 + 1)
    return quarter(row.get("period_id"))


def main():
    companies = load(ROOT / "data" / "library_index.json", {}).get("companies", [])
    rows = []
    for company in companies:
        ticker = company["ticker"]
        root = ROOT / "database" / ticker
        view = load(root / "html-research" / "data" / "report-view.json", {})
        records = load(root / "html-research" / "data" / "periods.json", {}).get("records", [])
        displayed = [q for q in (period_quarter(r) for r in records) if q]
        available = []
        for packet_path in (root / "earnings").glob("20*Q*/materials/analysis.json"):
            packet = load(packet_path, {})
            if packet.get("official_release_confirmed"):
                q = quarter(packet_path.parents[1].name)
                if q:
                    if ticker == "AAPL":
                        q -= 1  # Apple packet folders use fiscal quarters; HTML uses period-end calendar quarters.
                    available.append((q, packet_path.relative_to(ROOT).as_posix()))
        latest = max(available, default=(None, None))
        current = max(displayed, default=None)
        pending = sorted({path for q, path in available if current is None or q > current})
        status = ("no_public_earnings" if ticker == "SPACEX" else
                  "needs_source_mapping" if pending and not view.get("auto_generated_from_official_packets") else
                  "auto_refresh_pending" if pending else "current_or_source_limited")
        rows.append({"ticker": ticker, "status": status, "latest_official_packet": latest[1],
                     "pending_packets": pending, "auto_generated_html": bool(view.get("auto_generated_from_official_packets")),
                     "note": "A period match does not certify chart completeness or source verification."})
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "companies": rows}
    (ROOT / "data" / "html_update_queue.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({s: sum(r["status"] == s for r in rows) for s in sorted({r["status"] for r in rows})})


if __name__ == "__main__":
    main()
