"""Build Broadcom's sourced segment history and GAAP operating reconciliation."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from extract_avgo_segments import parse

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database" / "AVGO" / "html-research" / "data"
SEC_2026 = {
    "2026Q1": "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000016/avgo-20260201.htm",
    "2026Q2": "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000054/avgo-20260503.htm",
    "2026Q3": "https://www.sec.gov/Archives/edgar/data/1730168/000173016826000080/avgo-20260802.htm",
}
ENTITIES = {"Semiconductor solutions": "semiconductor_solutions", "Infrastructure software": "infrastructure_software", "Unallocated expenses": "unallocated_expenses"}


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def save(name, data):
    data["schema_version"] = "full-history-draft-v1"
    data["updated_at"] = date.today().isoformat()
    (DATA / f"{name}.json").write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    facts_payload, sources_payload, classification, periods_payload = load("facts"), load("sources"), load("classification"), load("periods")
    facts = [f for f in facts_payload["records"] if not f.get("tier2_segment_research")]
    sources = [s for s in sources_payload["records"] if not s.get("tier2_segment_research")]
    for period, url in SEC_2026.items():
        sources.append({"source_id": f"sec_{period}", "publisher": "SEC / Broadcom", "document_type": "Form 10-Q",
                        "title": f"Broadcom {period} 10-Q", "url": url, "published_at": "2026-09-10" if period == "2026Q3" else "2026-06-10" if period == "2026Q2" else "2026-03-11",
                        "is_company_official": True, "tier2_segment_research": True})
    for p in periods_payload["records"]:
        if p["period_id"] in SEC_2026:
            p["quarter_end"] = {"2026Q1": "2026-02-01", "2026Q2": "2026-05-03", "2026Q3": "2026-08-02"}[p["period_id"]]
            p["status"] = "reported"
    base = next(f for f in facts if f["metric_id"] == "consolidated_revenue")

    def add(period, name, metric, value, source, locator, period_type="quarter", derivation=None):
        entity = "group" if name == "Total" else ENTITIES[name]
        metric_id = ("consolidated_revenue" if metric == "revenue" else "consolidated_operating_profit") if entity == "group" else ("segment_revenue" if metric == "revenue" else "corporate_adjustment" if name == "Unallocated expenses" else "segment_operating_profit")
        fid = f"tier2:{period}:{period_type}:{metric_id}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=period, period_type=period_type, metric_id=metric_id,
                 original_metric_name=("Net revenue" if metric == "revenue" else "Operating income"), entity_id=entity,
                 parent_entity_id="group", entity_level="group" if entity == "group" else "adjustment" if name == "Unallocated expenses" else "reportable_segment",
                 value=value, value_status="derived" if derivation else "reported", source_id=source,
                 locator=locator, definition_version="AVGO-official-segments-GAAP", tier2_segment_research=True,
                 accounting_scope="consolidated" if entity == "group" else "reportable_segment")
        f.pop("side", None)
        if derivation:
            f["derivation"] = derivation
        if metric == "profit" and period_type == "quarter" and entity != "group":
            f["profit_reconciliation_complete"] = True
        facts.append(f)
        return fid

    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if year == 2026 and quarter == 4:
                continue
            period = f"{year}Q{quarter}"
            source = f"sec_{period}" if year == 2026 else f"official_{period}"
            if quarter != 4:
                item = parse(period)
                for name, metrics in item["data"].items():
                    for metric, value in metrics.items():
                        if name == "Total":
                            previous = next((f for f in facts if f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == ("consolidated_revenue" if metric == "revenue" else "consolidated_operating_profit") and not f.get("tier2_segment_research")), None)
                            if previous:
                                if abs(previous["value"] - value) > 0.01:
                                    if period == "2026Q3" and previous["value"] in (29600, 16000):
                                        previous["value"] = value
                                        previous["source_id"] = source
                                        previous["locator"] = f"Form 10-Q segment information; table {item['table']}; fiscal quarter ended"
                                        previous["value_precision"] = "exact"
                                    else:
                                        raise ValueError(f"{period} {metric}: existing group value {previous['value']} vs filing {value}")
                                continue
                        add(period, name, metric, value, source, f"Form 10-Q segment information; table {item['table']}; fiscal quarter ended")
            else:
                annual, ytd = parse(period, "annual"), parse(f"{year}Q3", "ytd")
                annual_ids, ytd_ids = {}, {}
                for name, metrics in annual["data"].items():
                    for metric, value in metrics.items():
                        annual_ids[(name, metric)] = add(period, name, metric, value, source, f"Form 10-K segment information; table {annual['table']}; fiscal year", "full_year")
                ytd_period = f"{year}Q3"
                for name, metrics in ytd["data"].items():
                    for metric, value in metrics.items():
                        ytd_ids[(name, metric)] = add(ytd_period, name, metric, value, f"official_{ytd_period}", f"Form 10-Q segment information; table {ytd['table']}; three fiscal quarters ended", "year_to_date")
                for name, metrics in annual["data"].items():
                    for metric, value in metrics.items():
                        inputs = [annual_ids[(name, metric)], ytd_ids[(name, metric)]]
                        add(period, name, metric, value - ytd["data"][name][metric], source,
                            f"Full fiscal year (table {annual['table']}) minus three fiscal quarters (table {ytd['table']})",
                            derivation={"formula": "annual - three_fiscal_quarters", "input_fact_ids": inputs})

    ai_path = ROOT / "database" / "AVGO" / "html-research" / "checks" / "ai-revenue-official-extraction.json"
    for row in json.loads(ai_path.read_text(encoding="utf-8"))["records"]:
        period, source_id = row["period"], f"avgo_ai_release_{row['period']}"
        sources.append({"source_id": source_id, "publisher": "Broadcom", "document_type": "earnings release",
                        "title": f"Broadcom {period} financial results", "url": row["url"],
                        "published_at": None, "is_company_official": True, "tier2_segment_research": True})
        f = deepcopy(base)
        f.update(fact_id=f"tier2:{period}:quarter:ai_revenue:group", period_id=period,
                 period_type="quarter", metric_id="ai_revenue", original_metric_name="AI semiconductor revenue",
                 entity_id="group", parent_entity_id="group", entity_level="group", side="ai",
                 value=row["value"], value_status="reported", source_id=source_id, locator=row["locator"],
                 definition_version="AVGO-official-AI-revenue", accounting_scope="reportable_segment",
                 value_precision=row["precision"], chart_slot="ai_revenue", tier2_segment_research=True)
        facts.append(f)

    classification["records"] = [c for c in classification["records"] if not c.get("tier2_segment_research")]
    for name, entity in ENTITIES.items():
        classification["records"].append({"classification_id": f"tier2:{entity}", "entity_id": entity, "official_name": name,
            "parent_entity_id": "group", "entity_level": "adjustment" if name == "Unallocated expenses" else "reportable_segment",
            "valid_from_period_id": "2021Q1", "valid_to_period_id": "2026Q3", "source_id": "official_2021Q1",
            "locator": "Form 10-Q Note: segment information", "side": "adjustment" if name == "Unallocated expenses" else "traditional",
            "classification_status": "financial_history_draft", "external_revenue_scope": "external_only", "tier2_segment_research": True})
    classification["records"].append({"classification_id": "tier2:ai_semiconductor", "entity_id": "ai_semiconductor",
        "official_name": "AI semiconductor revenue", "parent_entity_id": "semiconductor_solutions",
        "entity_level": "product_category", "valid_from_period_id": "2024Q2", "valid_to_period_id": "2026Q3",
        "source_id": "avgo_ai_release_2024Q2", "locator": "Earnings release CEO commentary",
        "side": "ai", "classification_status": "financial_history_draft",
        "external_revenue_scope": "subset_of_parent", "tier2_segment_research": True})
    view = load("report-view")
    view["research_status"] = "financial_history_draft"
    view["group_only_profit"] = False
    view["traditional_intro"] = "按正式报告分部列示半导体解决方案与基础设施软件；营业利润另含集团未分配费用。"
    view["ai_intro"] = "AI 半导体收入是半导体分部的子集，仅列示官方公告明确给出实际金额的季度。"
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256"):
        view.pop(key, None)
    facts_payload["records"] = facts
    sources_payload["records"] = sources
    save("facts", facts_payload)
    save("sources", sources_payload)
    save("classification", classification)
    save("periods", periods_payload)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AVGO", len([f for f in facts if f.get("tier2_segment_research")]), "segment facts")


if __name__ == "__main__":
    main()
