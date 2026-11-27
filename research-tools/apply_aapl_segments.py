"""Rebuild Apple's report on actual FY2021Q1–FY2026Q4 with official disclosures."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from extract_aapl_segments import PRODUCTS, REGIONS, parse, source_map

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database" / "AAPL" / "html-research" / "data"


def save(name, records):
    payload = {"schema_version": "full-history-draft-v1", "company_id": "aapl", "updated_at": date.today().isoformat(), "records": records}
    (DATA / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    source_map_ = source_map()
    old_facts = json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"]
    base = next(f for f in old_facts if f.get("metric_id") == "consolidated_revenue")
    facts, sources, periods, classes = [], [], [], []

    for year in range(2021, 2027):
        for q in range(1, 5):
            pid = f"FY{year}Q{q}"
            item = source_map_[pid]
            sid = f"sec_{pid}"
            sources.append({"source_id": sid, "publisher": "Apple / SEC", "document_type": "Form 10-K" if q == 4 else "Form 10-Q",
                            "title": f"Apple {pid} official filing", "url": item["url"], "published_at": item["published"],
                            "period_end": item["end"], "is_company_official": True})
            end = date.fromisoformat(item["end"])
            cq = (end.month - 1) // 3 + 1
            periods.append({"period_id": pid, "fiscal_year": year, "fiscal_quarter": q, "fiscal_label": pid,
                            "quarter_end": item["end"], "calendar_quarter": f"{end.year}Q{cq}",
                            "earnings_published_at": item["published"], "status": "reported",
                            "comparability_events": []})

    def add(pid, entity, metric, value, source, locator, period_type="quarter", inputs=None, formula=None):
        if entity == "group":
            metric_id, level = ("consolidated_revenue" if metric == "revenue" else "consolidated_operating_profit"), "group"
        elif entity == "corporate":
            metric_id, level = "corporate_adjustment", "adjustment"
        elif entity in ("americas", "europe", "greater_china", "japan", "rest_apac"):
            metric_id, level = ("segment_revenue" if metric == "revenue" else "segment_operating_profit"), "reportable_segment"
        else:
            metric_id, level = "product_revenue", "product_category"
        fid = f"aapl:{pid}:{period_type}:{metric_id}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric_id,
                 original_metric_name="Net sales" if metric == "revenue" else "Operating income/(loss)",
                 entity_id=entity, parent_entity_id="group", entity_level=level, value=value,
                 value_status="derived" if inputs else "reported", source_id=source, locator=locator,
                 definition_version="Apple-FY-segment-GAAP", accounting_scope="consolidated" if entity == "group" else "reportable_segment",
                 unit_original="USD millions", currency="USD", scale_original="million", display_scale="亿美元")
        f.pop("side", None)
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        if metric == "profit" and period_type == "quarter" and entity != "group":
            f["profit_reconciliation_complete"] = True
        facts.append(f)
        return fid

    entity_for_region = {"Americas": "americas", "Europe": "europe", "Greater China": "greater_china", "Japan": "japan", "Rest of Asia Pacific": "rest_apac", "Corporate": "corporate", "Total": "group"}
    entity_for_product = {"iPhone": "iphone", "Mac": "mac", "iPad": "ipad", "Wearables, Home and Accessories": "wearables_home_accessories", "Services": "services", "Total": "group"}

    def write_result(pid, result, source, period_type="quarter", inputs=None, formula=None):
        ids = {}
        for name, values in result["regions"]["data"].items():
            if name == "Corporate":
                ids[("regions", name, "profit")] = add(pid, "corporate", "profit", values["profit"], source,
                    f"SEC Note: Segment Information; table {result['regions']['table']}", period_type, inputs.get(("regions", name, "profit")) if inputs else None, formula)
            else:
                for metric, value in values.items():
                    ids[("regions", name, metric)] = add(pid, entity_for_region[name], metric, value, source,
                        f"SEC Note: Segment Information; table {result['regions']['table']}", period_type, inputs.get(("regions", name, metric)) if inputs else None, formula)
        for name, value in result["products"]["data"].items():
            if name == "Total":
                continue
            ids[("products", name, "revenue")] = add(pid, entity_for_product[name], "revenue", value, source,
                f"SEC Note: Revenue; table {result['products']['table']}", period_type, inputs.get(("products", name, "revenue")) if inputs else None, formula)
        return ids

    for year in range(2021, 2027):
        for q in range(1, 5):
            pid = f"FY{year}Q{q}"
            item = source_map_[pid]
            if q < 4:
                result = parse(item["path"], "quarter", pid, item["end"])
                write_result(pid, result, f"sec_{pid}")
            else:
                annual = parse(item["path"], "annual", pid, item["end"])
                prior_pid = f"FY{year}Q3"
                prior_item = source_map_[prior_pid]
                ytd = parse(prior_item["path"], "ytd", prior_pid, prior_item["end"])
                annual_ids = write_result(pid, annual, f"sec_{pid}", "full_year")
                ytd_ids = write_result(prior_pid, ytd, f"sec_{prior_pid}", "year_to_date")
                result = {"regions": {"table": annual["regions"]["table"], "data": {}},
                          "products": {"table": annual["products"]["table"], "data": {}}}
                input_map = {}
                for name, values in annual["regions"]["data"].items():
                    result["regions"]["data"][name] = {metric: value - ytd["regions"]["data"][name][metric] for metric, value in values.items()}
                    for metric in values:
                        if name == "Corporate" and metric == "revenue":
                            continue
                        input_map[("regions", name, metric)] = [annual_ids[("regions", name, metric)], ytd_ids[("regions", name, metric)]]
                for name, value in annual["products"]["data"].items():
                    result["products"]["data"][name] = value - ytd["products"]["data"][name]
                    if name != "Total":
                        input_map[("products", name, "revenue")] = [annual_ids[("products", name, "revenue")], ytd_ids[("products", name, "revenue")]]
                write_result(pid, result, f"sec_{pid}", inputs=input_map, formula="full fiscal year - first nine months")

    for name, entity in entity_for_region.items():
        if name in ("Total", "Corporate"):
            continue
        classes.append({"classification_id": f"aapl:{entity}", "entity_id": entity, "official_name": name,
            "parent_entity_id": "group", "entity_level": "reportable_segment", "valid_from_period_id": "FY2021Q1",
            "valid_to_period_id": "FY2026Q4", "source_id": "sec_FY2021Q1", "locator": "SEC Note: Segment Information",
            "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    classes.append({"classification_id": "aapl:corporate", "entity_id": "corporate", "official_name": "Corporate",
        "parent_entity_id": "group", "entity_level": "adjustment", "valid_from_period_id": "FY2021Q1", "valid_to_period_id": "FY2026Q4",
        "source_id": "sec_FY2021Q1", "locator": "Group operating income less reported geographic segment income",
        "side": "adjustment", "classification_status": "financial_history_draft"})
    for name, entity in entity_for_product.items():
        if name == "Total":
            continue
        classes.append({"classification_id": f"aapl:{entity}", "entity_id": entity, "official_name": name,
            "parent_entity_id": "group", "entity_level": "product_category", "valid_from_period_id": "FY2021Q1",
            "valid_to_period_id": "FY2026Q4", "source_id": "sec_FY2021Q1", "locator": "SEC Note: Revenue by category",
            "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})

    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False,
                traditional_intro="正式分部按美洲、欧洲、大中华、日本、亚太其他地区列示；产品收入为独立的平行披露视图。",
                ai_intro="公司未按季度披露可单独勾稽的 AI 产品收入，相关图卡保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256"):
        view.pop(key, None)
    save("sources", sources)
    save("periods", periods)
    save("facts", facts)
    save("classification", classes)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("AAPL", len(periods), "fiscal periods", len(facts), "facts")


if __name__ == "__main__":
    main()
