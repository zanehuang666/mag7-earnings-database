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
        view_file = folder / "data" / "report-view.json"
        view = json.loads(view_file.read_text(encoding="utf-8")) if view_file.exists() else {}
        facts_file = folder / "data" / "facts.json"
        facts = json.loads(facts_file.read_text(encoding="utf-8")).get("records", []) if facts_file.exists() else []
        sourced_revenue_periods = {str(f.get("period_id")) for f in facts if f.get("metric_id") == "consolidated_revenue" and isinstance(f.get("value"), (int, float))}
        has_2021 = any("2021" in item or "21Q" in item for item in ids)
        output = folder / "output" / "overview.html"
        status = ("diagnostic_draft" if output.exists() and view.get("research_status") == "diagnostic"
                  else "periods_2021_onward_present" if output.exists() and has_2021 and len(sourced_revenue_periods) >= 20
                  else "html_exists_but_history_incomplete" if output.exists() else "html_missing")
        rows.append({"ticker": ticker, "tier": company["tier"], "status": status,
                     "period_count": len(ids), "sourced_revenue_quarters": len(sourced_revenue_periods),
                     "research_status": view.get("research_status"), "first_period": ids[0] if ids else None,
                     "last_period": ids[-1] if ids else None,
                     "html_path": company["html_path"],
                     "note": "Period coverage alone does not validate chart values or source quality."})
    result = {"scope": "HTML research from FY2021Q1 to latest officially published quarter",
              "generated_at": datetime.now(timezone.utc).isoformat(), "companies": rows}
    (ROOT / "data" / "html_coverage.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print({status: sum(r["status"] == status for r in rows) for status in
           ("periods_2021_onward_present", "diagnostic_draft", "html_exists_but_history_incomplete", "html_missing")})


if __name__ == "__main__":
    main()
