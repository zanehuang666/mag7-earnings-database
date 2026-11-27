"""Add sourced AMAT segment history extracted from SEC quarterly/annual tables."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from extract_amat_segments import parse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database" / "AMAT" / "html-research" / "data"
NAMES = {
    "Semiconductor Systems": "semiconductor_systems",
    "Applied Global Services": "applied_global_services",
    "Display and Adjacent Markets": "display_adjacent",
    "Display": "display",
    "Corporate and Other": "corporate_other",
    "Other": "other",
}


def read(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def save(name, value):
    value["updated_at"] = date.today().isoformat()
    value["schema_version"] = "full-history-draft-v1"
    (DATA / f"{name}.json").write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    payload = read("facts")
    facts = [f for f in payload["records"] if not f.get("tier2_segment_research")]
    sources = {s["source_id"] for s in read("sources")["records"]}
    periods = read("periods")
    base = next(f for f in facts if f["metric_id"] == "consolidated_revenue")

    def add(period, name, kind, value, source, locator, period_type="quarter", derivation=None):
        entity = "group" if name == "Total" else NAMES[name]
        metric = ("consolidated_revenue" if kind == "revenue" else "consolidated_operating_profit") if entity == "group" else ("segment_revenue" if kind == "revenue" else "segment_operating_profit")
        fid = f"tier2:{period}:{period_type}:{metric}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=period, period_type=period_type, metric_id=metric,
                 original_metric_name=("Net sales" if kind == "revenue" else "Operating income (loss)"),
                 entity_id=entity, parent_entity_id="group", entity_level=("group" if entity == "group" else "reportable_segment"),
                 value=value, value_status=("derived" if derivation else "reported"), source_id=source,
                 locator=locator, definition_version=f"AMAT-{period[:4]}-official-segment",
                 accounting_scope=("consolidated" if entity == "group" else "reportable_segment"),
                 tier2_segment_research=True)
        f.pop("side", None)
        if derivation:
            f["derivation"] = derivation
        if kind == "profit" and period_type == "quarter" and entity != "group":
            f["profit_reconciliation_complete"] = True
        facts.append(f)
        return fid

    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if year == 2026 and quarter == 4:
                continue
            period = f"{year}Q{quarter}"
            source = f"official_{period}"
            if source not in sources:
                raise ValueError(f"missing official source {source}")
            if quarter < 4:
                item = parse(period)
                for name, values in item["data"].items():
                    for kind, value in zip(("revenue", "profit"), values):
                        if name == "Total" and any(f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == ("consolidated_revenue" if kind == "revenue" else "consolidated_operating_profit") for f in facts):
                            continue
                        add(period, name, kind, value, source, f"SEC Note: segment information; table {item['table']}; Three Months Ended")
            else:
                annual = parse(period, "annual")
                ytd_period = f"{year}Q3"
                ytd = parse(ytd_period, "ytd")
                annual_ids, ytd_ids = {}, {}
                for name, values in annual["data"].items():
                    for kind, value in zip(("revenue", "profit"), values):
                        annual_ids[(name, kind)] = add(period, name, kind, value, source, f"SEC Note: segment information; table {annual['table']}; Full Fiscal Year", "full_year")
                for name, values in ytd["data"].items():
                    for kind, value in zip(("revenue", "profit"), values):
                        ytd_ids[(name, kind)] = add(ytd_period, name, kind, value, f"official_{ytd_period}", f"SEC Note: segment information; table {ytd['table']}; Nine Months Ended", "year_to_date")
                for name in annual["data"]:
                    if name not in ytd["data"] and name not in ("Display", "Corporate and Other"):
                        continue
                    output_name = name
                    if year == 2025 and name == "Corporate and Other":
                        output_name = "Other"
                    if year == 2025 and name == "Display":
                        continue
                    if year == 2024 and name == "Display":
                        prior_names = ["Display and Adjacent Markets"]
                    elif year == 2025 and name == "Corporate and Other":
                        prior_names = ["Corporate and Other", "Display"]
                    else:
                        prior_names = [name]
                    for idx, kind in enumerate(("revenue", "profit")):
                        base_value = annual["data"][name][idx]
                        prior = sum(ytd["data"][n][idx] for n in prior_names)
                        inputs = [annual_ids[(name, kind)]] + [ytd_ids[(n, kind)] for n in prior_names]
                        add(period, output_name, kind, base_value - prior, source,
                            f"Full Fiscal Year (table {annual['table']}) minus Nine Months Ended (table {ytd['table']})",
                            derivation={"formula": "annual - nine_months", "input_fact_ids": inputs})

    classification = read("classification")
    classification["records"] = [c for c in classification["records"] if not c.get("tier2_segment_research")]
    for name, entity in NAMES.items():
        relevant = [f for f in facts if f.get("tier2_segment_research") and f.get("period_type") == "quarter" and f.get("entity_id") == entity]
        if not relevant:
            continue
        periods_for_entity = sorted({f["period_id"] for f in relevant})
        first = periods_for_entity[0]
        classification["records"].append({"classification_id": f"tier2:{entity}", "entity_id": entity, "official_name": name,
            "parent_entity_id": "group", "entity_level": "adjustment" if name in ("Corporate and Other", "Other") else "reportable_segment",
            "valid_from_period_id": first, "valid_to_period_id": periods_for_entity[-1], "source_id": f"official_{first}",
            "locator": "SEC Note: segment information", "side": "traditional", "classification_status": "financial_history_draft",
            "external_revenue_scope": "external_only", "tier2_segment_research": True})

    original = [f for f in facts if f.get("period_type") == "quarter" and f.get("metric_id") in ("consolidated_revenue", "consolidated_operating_profit") and not f.get("tier2_segment_research")]
    for item in original:
        extracted = next((f for f in facts if f.get("period_id") == item["period_id"] and f.get("period_type") == "quarter" and f.get("metric_id") == item["metric_id"] and f.get("entity_id") == "group" and f.get("tier2_segment_research")), None)
        if extracted and abs(extracted["value"] - item["value"]) > 0.01:
            raise ValueError(f"{item['period_id']} {item['metric_id']}: group mismatch {item['value']} vs {extracted['value']}")
    view = read("report-view")
    view["research_status"] = "financial_history_draft"
    view["group_only_profit"] = False
    view["traditional_intro"] = "按公司当季正式披露的半导体系统、全球服务、显示及其他收入列示；历史分部名称变更保留断点。"
    view["ai_intro"] = "公司未逐季披露可独立勾稽的 AI 产品收入，AI 收入与利润图保留空值。"
    view.pop("auto_generated_from_official_packets", None)
    view.pop("source_digest", None)
    view.pop("output_sha256", None)
    payload["records"] = facts
    save("facts", payload)
    save("classification", classification)
    save("periods", periods)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AMAT", len([f for f in facts if f.get("tier2_segment_research")]), "segment facts")


if __name__ == "__main__":
    main()
