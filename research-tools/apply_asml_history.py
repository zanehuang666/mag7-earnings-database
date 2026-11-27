"""Build ASML's 23-quarter product and system-volume history from issuer releases."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database/ASML/html-research/data"
AUDIT = json.loads((ROOT / "database/ASML/html-research/checks/official-quarterly-extraction.json").read_text(encoding="utf-8"))


def save(name, rows):
    (DATA / f"{name}.json").write_text(json.dumps({"schema_version": "full-history-draft-v1", "company_id": "asml",
                                              "updated_at": date.today().isoformat(), "records": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    base = next(f for f in json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"] if f["metric_id"] == "consolidated_revenue")
    facts, sources, periods = [], [], []
    for item in AUDIT:
        pid = item["period_id"]
        y, q = int(pid[:4]), int(pid[-1])
        sid = f"official_{pid}"
        sources.append({"source_id": sid, "publisher": "ASML", "document_type": "Quarterly earnings release",
                        "title": f"ASML {pid} official quarterly results", "url": item["url"],
                        "published_at": item["published_at"], "is_company_official": True})
        periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                        "quarter_end": None, "calendar_quarter": pid, "earnings_published_at": item["published_at"],
                        "status": "reported", "comparability_events": []})
    sources.append({"source_id": "asml_2025_annual", "publisher": "ASML", "document_type": "2025 Annual Report US GAAP",
                    "title": "ASML 2025 Annual Report Based on US GAAP",
                    "url": "https://ourbrand.asml.com/m/71076aaad607de4d/original/asml-2025-annual-report-based-on-us-gaap.pdf",
                    "published_at": "2026-02-25", "is_company_official": True})

    def add(pid, metric, entity, value, sid, locator, inputs=None, formula=None, unit="EUR millions", slot=None):
        fid = f"asml:{pid}:quarter:{metric}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=pid, period_type="quarter", metric_id=metric,
                 original_metric_name="Total net sales" if metric == "consolidated_revenue" else "Installed Base Management sales" if entity == "ibm" else "Net system sales" if entity == "systems" else "Sales of lithography systems" if "shipment" in metric else metric,
                 entity_id=entity, parent_entity_id="lithography_segment" if entity in ("systems","ibm") else "group",
                 entity_level="product_category" if entity in ("systems","ibm") else "reportable_segment" if entity == "lithography_segment" else "group" if entity == "group" else "product",
                 value=value, value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                 definition_version="ASML-US-GAAP-quarterly-release", accounting_scope="consolidated",
                 unit_original=unit, currency="EUR" if unit == "EUR millions" else None,
                 scale_original="million" if unit == "EUR millions" else "unit", display_scale="亿欧元" if unit == "EUR millions" else unit,
                 gaap_basis="US GAAP")
        f.pop("side", None)
        if entity in ("systems", "ibm"):
            f["is_exhaustive_child_set"] = True
        if metric == "shipment_quantity":
            f.update(product_entity_id=entity, comparison_basis="quarter", measurement_unit="systems",
                     value_precision="exact", original_wording="New and used lithography systems sold (units)")
        if slot:
            f["chart_slot"] = slot
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(f)
        return fid

    for item in AUDIT:
        pid, sid = item["period_id"], f"official_{item['period_id']}"
        total = item["revenue"]
        ibm = item["ibm"]
        if not all(isinstance(item[k], (int,float)) for k in ("revenue","ibm","gross_profit","net_income","new_systems","used_systems")):
            raise ValueError(f"{pid}: incomplete official release extraction")
        t = add(pid, "consolidated_revenue", "group", total, sid, "Issuer quarterly release, summary table: net sales")
        add(pid, "segment_revenue", "lithography_segment", total, sid,
            "One formal reportable segment (2025 annual report); same consolidated net sales", inputs=[t], formula="sole reportable segment = group")
        b = add(pid, "product_revenue", "ibm", ibm, sid, "Issuer quarterly release, summary table: Installed Base Management sales")
        add(pid, "product_revenue", "systems", total-ibm, sid, "Total net sales less Installed Base Management sales",
            inputs=[t,b], formula="total net sales - Installed Base Management sales")
        add(pid, "consolidated_gross_profit", "group", item["gross_profit"], sid, "Issuer quarterly release, summary table: gross profit")
        add(pid, "consolidated_net_profit", "group", item["net_income"], sid, "Issuer quarterly release, summary table: net income")
        n = add(pid, "shipment_quantity", "new_systems", item["new_systems"], sid,
                "Issuer quarterly release, summary table: new lithography systems sold", unit="systems")
        u = add(pid, "shipment_quantity", "used_systems", item["used_systems"], sid,
                "Issuer quarterly release, summary table: used lithography systems sold", unit="systems")
        add(pid, "shipment_quantity", "lithography_systems", item["new_systems"]+item["used_systems"], sid,
            "New plus used lithography systems sold; excludes metrology and inspection", inputs=[n,u],
            formula="new systems + used systems", unit="systems", slot="traditional_progress")

    classes = [{"classification_id": "asml:lithography_segment", "entity_id": "lithography_segment",
                "official_name": "光刻解决方案（唯一报告分部）", "parent_entity_id": "group", "entity_level": "reportable_segment",
                "valid_from_period_id": "2021Q1", "valid_to_period_id": "2026Q3", "source_id": "asml_2025_annual",
                "locator": "Segment disclosure: one reportable segment", "side": "traditional",
                "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"}]
    for entity, name in (("systems", "光刻系统销售"), ("ibm", "装机基座管理及服务")):
        classes.append({"classification_id": f"asml:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "lithography_segment", "entity_level": "product_category", "valid_from_period_id": "2021Q1",
                        "valid_to_period_id": "2026Q3", "source_id": "official_2021Q1", "locator": "Issuer earnings release summary table",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False,
                traditional_intro="唯一正式分部下，收入拆为光刻系统与装机基座管理服务；逐季销量为新旧光刻系统合计，不含检测设备。",
                ai_intro="EUV/DUV 和 AI 终端相关收入尚未完成逐季核实，AI 图卡保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    view["chart_context_notes"] = {"g2": "系统收入为总收入减官方披露的装机基座管理收入；系统与服务利润未单独披露。",
                                   "g3": "只有集团毛利和净利润，未将其分摊到系统或服务业务。",
                                   "g8": "历史季度经营现金流仍在逐季核对，空值不代表零。"}
    for name, rows in (("sources", sources), ("periods", periods), ("facts", facts), ("classification", classes)):
        save(name, rows)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ASML", len(periods), "quarters", len(facts), "facts")


if __name__ == "__main__":
    main()
