"""Add Tesla's official segment gross profit and detailed revenue history."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

from extract_tsla_segments import parse, parse_products

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database" / "TSLA" / "html-research" / "data"
SEGMENTS = {"Automotive segment": "automotive_segment", "Energy generation and storage segment": "energy_segment"}
PRODUCTS = {"Automotive sales": ("automotive_sales", "automotive_segment"),
            "Automotive regulatory credits": ("automotive_regulatory_credits", "automotive_segment"),
            "Automotive leasing": ("automotive_leasing", "automotive_segment"),
            "Services and other": ("services_other", "automotive_segment"),
            "Energy generation and storage": ("energy_revenue", "energy_segment")}


def load(name):
    return json.loads((DATA / f"{name}.json").read_text(encoding="utf-8"))


def save(name, payload):
    payload["schema_version"] = "full-history-draft-v1"
    payload["updated_at"] = date.today().isoformat()
    (DATA / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    facts_payload, classes_payload, sources_payload = load("facts"), load("classification"), load("sources")
    facts = [f for f in facts_payload["records"] if not f.get("tier2_segment_research") and not f.get("tesla_deliveries_research")]
    sources_payload["records"] = [s for s in sources_payload["records"] if not s.get("tesla_deliveries_research")]
    base = next(f for f in facts if f["metric_id"] == "consolidated_revenue")

    def add(period, name, metric, value, source, locator, period_type="quarter", derivation=None):
        if name == "Total":
            entity, parent, level = "group", "group", "group"
            metric_id = "consolidated_revenue"
        elif name in SEGMENTS:
            entity, parent, level = SEGMENTS[name], "group", "reportable_segment"
            metric_id = "segment_revenue" if metric == "revenue" else "segment_profit"
        else:
            entity, parent = PRODUCTS[name]
            level, metric_id = "product_category", "product_revenue"
        fid = f"tier2:{period}:{period_type}:{metric_id}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=period, period_type=period_type, metric_id=metric_id,
                 original_metric_name="Gross profit" if metric == "gross_profit" else "Revenue",
                 entity_id=entity, parent_entity_id=parent, entity_level=level, value=value,
                 value_status="derived" if derivation else "reported", source_id=source, locator=locator,
                 definition_version="TSLA-official-segments-GAAP", accounting_scope="reportable_segment" if metric == "gross_profit" else "consolidated",
                 tier2_segment_research=True)
        f.pop("side", None)
        if derivation:
            f["derivation"] = derivation
        if name in PRODUCTS and period_type == "quarter":
            f["is_exhaustive_child_set"] = True
        if metric == "gross_profit":
            f["profit_basis"] = "GAAP gross profit"
        facts.append(f)
        return fid

    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if year == 2026 and quarter == 4:
                continue
            period = f"{year}Q{quarter}"
            source = f"official_{period}"
            if quarter < 4:
                segments, products = parse(period), parse_products(period)
                for name, metrics in segments["data"].items():
                    for metric, value in metrics.items():
                        add(period, name, metric, value, source, f"SEC Note: segment information; table {segments['table']}; Three Months Ended")
                for name, value in products["data"].items():
                    if name != "Total":
                        add(period, name, "revenue", value, source, f"SEC Revenue note; table {products['table']}; Three Months Ended")
            else:
                annual_s, ytd_s = parse(period, "annual"), parse(f"{year}Q3", "ytd")
                annual_p, ytd_p = parse_products(period, "annual"), parse_products(f"{year}Q3", "ytd")
                for annual, ytd, is_product in ((annual_s, ytd_s, False), (annual_p, ytd_p, True)):
                    for name, metrics in annual["data"].items():
                        if is_product:
                            metrics = {"revenue": metrics}
                            earlier = {"revenue": ytd["data"][name]}
                        else:
                            earlier = ytd["data"][name]
                        for metric, value in metrics.items():
                            fid_a = add(period, name, metric, value, source, f"SEC fiscal year table {annual['table']}", "full_year")
                            fid_y = add(f"{year}Q3", name, metric, earlier[metric], f"official_{year}Q3", f"SEC nine months table {ytd['table']}", "year_to_date")
                            if name == "Total" and any(f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == "consolidated_revenue" and not f.get("tier2_segment_research") for f in facts):
                                continue
                            add(period, name, metric, value - earlier[metric], source,
                                f"Full fiscal year (table {annual['table']}) minus nine months (table {ytd['table']})",
                                derivation={"formula": "annual - nine_months", "input_fact_ids": [fid_a, fid_y]})

    for period in [f"{year}Q{quarter}" for year in range(2021, 2027) for quarter in range(1, 5) if year != 2026 or quarter != 4]:
        group = next((f["value"] for f in facts if f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == "consolidated_revenue"), None)
        segments = [f["value"] for f in facts if f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == "segment_revenue"]
        products = [f["value"] for f in facts if f.get("period_id") == period and f.get("period_type") == "quarter" and f.get("metric_id") == "product_revenue"]
        if group is None or sum(segments) != group or sum(products) != group:
            raise ValueError(f"{period}: group {group}, segments {sum(segments)}, products {sum(products)}")

    deliveries_path = ROOT / "database" / "TSLA" / "html-research" / "checks" / "vehicle-deliveries-extraction.json"
    delivery_rows = json.loads(deliveries_path.read_text(encoding="utf-8"))["records"]
    for row in delivery_rows:
        period = row["period"]
        source_id = f"tesla_deliveries_{period}"
        sources_payload["records"].append({"source_id": source_id, "publisher": "Tesla Investor Relations",
            "document_type": "quarterly deliveries release or operational summary", "title": f"Tesla {period} vehicle deliveries",
            "url": row["url"], "published_at": row["published_at"], "is_company_official": True,
            "tesla_deliveries_research": True})
        f = deepcopy(base)
        f.update(fact_id=f"tesla:{period}:shipment_quantity:automotive_segment", period_id=period,
            period_type="quarter", metric_id="shipment_quantity", original_metric_name="Total vehicle deliveries",
            entity_id="automotive_segment", parent_entity_id="group", entity_level="reportable_segment",
            value=row["value"], value_status="reported", unit_original="vehicles", currency=None,
            scale_original="unit", display_scale="vehicles", accounting_scope="operational",
            definition_version="Tesla-official-vehicle-deliveries", source_id=source_id,
            locator=row.get("locator", "Quarterly production and deliveries release; Total deliveries row"),
            product_entity_id="automotive_segment", measurement_unit="vehicles", comparison_basis="quarter",
            chart_slot="traditional_progress", original_wording="Total deliveries",
            tesla_deliveries_research=True)
        facts.append(f)

    classes_payload["records"] = [c for c in classes_payload["records"] if not c.get("tier2_segment_research")]
    for name, entity in SEGMENTS.items():
        classes_payload["records"].append({"classification_id": f"tier2:{entity}", "entity_id": entity,
            "official_name": name, "parent_entity_id": "group", "entity_level": "reportable_segment",
            "valid_from_period_id": "2021Q1", "valid_to_period_id": "2026Q3", "source_id": "official_2021Q1",
            "locator": "SEC Note: segment information", "side": "traditional", "classification_status": "financial_history_draft",
            "external_revenue_scope": "external_only", "tier2_segment_research": True})
    for name, (entity, parent) in PRODUCTS.items():
        classes_payload["records"].append({"classification_id": f"tier2:{entity}", "entity_id": entity,
            "official_name": name, "parent_entity_id": parent, "entity_level": "product_category",
            "valid_from_period_id": "2021Q1", "valid_to_period_id": "2026Q3", "source_id": "official_2021Q1",
            "locator": "SEC Revenue note", "side": "traditional", "classification_status": "financial_history_draft",
            "external_revenue_scope": "external_only", "tier2_segment_research": True})
    view = load("report-view")
    view.update(research_status="financial_history_draft", group_only_profit=False, profit_chart_label="毛利润",
                traditional_intro="汽车收入按销售、监管积分、租赁、服务拆分；能源生产与储能单列。",
                ai_intro="公司尚未披露可与收入勾稽的 AI 软件季度绝对收入，相关图卡留空。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256"):
        view.pop(key, None)
    facts_payload["records"] = facts
    save("facts", facts_payload)
    save("classification", classes_payload)
    save("sources", sources_payload)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("TSLA", len([f for f in facts if f.get("tier2_segment_research")]), "segment/product facts")


if __name__ == "__main__":
    main()
