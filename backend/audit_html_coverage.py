"""Publish an honest FY2021-to-current coverage inventory for HTML research."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    library = json.loads((ROOT / "data" / "library_index.json").read_text(encoding="utf-8"))
    rows = []
    for company in library["companies"]:
        ticker = company["ticker"]
        folder = ROOT / "database" / ticker / "html-research"
        periods = folder / "data" / "periods.json"
        records = json.loads(periods.read_text(encoding="utf-8")).get("records", []) if periods.exists() else []
        ids = [str(row.get("period_id", "")) for row in records]
        has_2021 = any("2021" in item or "21Q" in item for item in ids)
        output = folder / "output" / "overview.html"
        status = ("periods_2021_onward_present" if output.exists() and has_2021 and len(ids) >= 20
                  else "html_exists_but_history_incomplete" if output.exists() else "html_missing")
        rows.append({"ticker": ticker, "tier": company["tier"], "status": status,
                     "period_count": len(ids), "first_period": ids[0] if ids else None,
                     "last_period": ids[-1] if ids else None,
                     "html_path": company["html_path"],
                     "note": "Period coverage alone does not validate chart values or source quality."})
    result = {"scope": "HTML research from FY2021Q1 to latest officially published quarter",
              "generated_at": datetime.now(timezone.utc).isoformat(), "companies": rows}
    (ROOT / "data" / "html_coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({status: sum(r["status"] == status for r in rows) for status in
           ("periods_2021_onward_present", "html_exists_but_history_incomplete", "html_missing")})


if __name__ == "__main__":
    main()
