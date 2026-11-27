"""Build a hardware earnings report from the five sourced JSON files."""
import argparse
import json
import sys
from pathlib import Path

from render_html import render
from report_model import build_model
from validate_data import load_bundle, validate


def build(directory, output):
    bundle = load_bundle(directory)
    config_file = directory / "report-view.json"
    metadata = json.loads(config_file.read_text(encoding="utf-8")) if config_file.exists() else {}
    report = validate(bundle, allow_review_sources=metadata.get("research_status") == "sample_reproduction")
    if not report["ok"]:
        raise ValueError("data validation failed: " + "; ".join(report["errors"]))
    if metadata.get("research_status") == "verified":
        topics = ("source", "business_classification", "revenue", "profit", "cash_flow", "guidance", "quantity_price")
        covered = {"complete", "confirmed_not_disclosed", "not_applicable"}
        source_ids = {s.get("source_id") for s in bundle["sources"] if s.get("is_company_official") is True}
        gaps = []
        for period in bundle["periods"]:
            if period.get("status") == "pre_release":
                continue
            pid = period.get("period_id")
            if period.get("status") != "reported" or not period.get("quarter_end"):
                gaps.append(f"{pid}: period not fully researched")
            for topic in topics:
                item = (period.get("research_coverage") or {}).get(topic) or {}
                if item.get("status") not in covered or not set(item.get("source_ids") or []).intersection(source_ids):
                    gaps.append(f"{pid}: {topic} lacks official-source review")
                elif item.get("status") != "complete" and not item.get("note"):
                    gaps.append(f"{pid}: {topic} missing explanation")
        if gaps:
            raise ValueError("verified report research coverage incomplete: " + "; ".join(gaps))
        missing = [p["period_id"] for p in bundle["periods"] if p.get("status") != "pre_release" and
                   not any(f.get("period_id") == p["period_id"] and f.get("metric_id") == "consolidated_revenue" and
                           f.get("period_type") == "quarter" and isinstance(f.get("value"), (int, float)) for f in bundle["facts"])]
        if missing:
            raise ValueError("verified report requires consolidated quarterly revenue for every period: " + ", ".join(missing))
        if any(s.get("is_review_fixture") for s in bundle["sources"]):
            raise ValueError("verified report cannot include review fixtures")
    if metadata.get("research_status") == "verified" and not metadata.get("return_href"):
        raise ValueError("verified report requires report-view.json return_href to the hardware research index")
    model = build_model(bundle, metadata)
    render(model, output)
    return {"output": str(output), "quarters": len(model["quarters"]), "charts": len(model["charts"]), "data_report": report}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("data_dir")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    try:
        print(json.dumps(build(Path(args.data_dir), Path(args.output)), ensure_ascii=False, indent=2))
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)
