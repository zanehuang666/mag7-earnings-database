"""Rebuild Cisco's FY2021Q1–FY2027Q1 report from audited SEC segment tables."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/CSCO/html-research"
DATA = BASE / "data"
AUDIT = json.loads((BASE / "checks/segment-extraction.json").read_text(encoding="utf-8"))
XBRL = json.loads((ROOT / ".research-cache/tier2/companyfacts/CSCO.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]


def save(name, rows):
    obj = {"schema_version": "full-history-draft-v1", "company_id": "csco", "updated_at": date.today().isoformat(), "records": rows}
    (DATA / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def xbrl_op(year, quarter, end, cumulative=False):
    form = "10-K" if quarter == 4 else "10-Q"
    fp = "FY" if quarter == 4 else f"Q{quarter}"
    rows = [x for x in XBRL["OperatingIncomeLoss"]["units"]["USD"]
            if x.get("fy") == year and x.get("fp") == fp and x.get("form") == form and x.get("end") == end and x.get("start")]
    if not cumulative and quarter < 4:
        start = date.fromisoformat(end)
        rows = [x for x in rows if 70 <= (start - date.fromisoformat(x["start"])).days <= 112]
    else:
        start = date.fromisoformat(end)
        rows = [x for x in rows if (start - date.fromisoformat(x["start"])).days >= (250 if quarter == 3 else 340)]
    if not rows:
        raise ValueError(f"missing group operating income FY{year}Q{quarter} {end}")
    rows.sort(key=lambda x: (x["filed"], x.get("accn", "")))
    return rows[0]


def main():
    old_sources = {s["source_id"]: s for s in json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["records"]}
    base = next(f for f in json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"] if f["metric_id"] == "consolidated_revenue")
    periods, sources, facts, classes = [], [], [], []
    by_pid = {x["period_id"]: x for x in AUDIT}
    final = AUDIT[-1]["period_id"]
    for item in AUDIT:
        pid = item["period_id"]
        y, q = int(pid[2:6]), int(pid[-1])
        sid = f"sec_{pid}"
        op = xbrl_op(y, q, item["end"], cumulative=q == 4)
        old = old_sources.get(f"official_{item['old_id']}") if item["old_id"] else None
        sources.append({"source_id": sid, "publisher": "Cisco / SEC", "document_type": "Form 10-K" if q == 4 else "Form 10-Q",
                        "title": f"Cisco {pid} official filing", "url": item["url"], "published_at": op["filed"],
                        "period_end": item["end"], "is_company_official": True})
        end = date.fromisoformat(item["end"])
        periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                        "quarter_end": item["end"], "calendar_quarter": f"{end.year}Q{(end.month-1)//3+1}",
                        "earnings_published_at": op["filed"], "status": "reported", "comparability_events": []})

    def add(pid, metric, entity, value, sid, locator, period_type="quarter", inputs=None, formula=None, basis=None):
        fid = f"csco:{pid}:{period_type}:{metric}:{entity}"
        fact = deepcopy(base)
        fact.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                    original_metric_name="Gross margin" if basis else "Revenue" if "revenue" in metric else "Operating income",
                    entity_id=entity, parent_entity_id="group", entity_level="group" if entity == "group" else "adjustment" if entity.endswith("_rounding") else "reportable_segment" if entity in ("americas", "emea", "apjc") else "product_category",
                    value=value, value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                    definition_version="CSCO-fiscal-official", accounting_scope="consolidated" if entity == "group" else "reportable_segment",
                    unit_original="USD millions", currency="USD", scale_original="million", display_scale="亿美元")
        fact.pop("side", None)
        if basis:
            fact["profit_basis"] = basis
        if inputs:
            fact["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(fact)
        return fid

    labels = {"Americas": "americas", "EMEA": "emea", "APJC": "apjc"}
    prod_names = set()

    def write(pid, item, type_="quarter", prior=None):
        sid = f"sec_{pid}"
        ids = {}
        for view in ("product", "geography"):
            source = item[view]
            previous = prior[view] if prior else None
            data = source[1]
            for name, value in data["revenue"].items():
                metric = "product_revenue" if view == "product" else "segment_revenue"
                entity = name.lower().replace(" ", "_").replace(",", "").replace("-", "_") if view == "product" else labels[name]
                prod_names.add(name) if view == "product" else None
                key = (view, "revenue", name)
                inputs = [source[2][key], previous[2][key]] if previous else None
                ids[key] = add(pid, metric, entity, value, sid, f"SEC segment note, table {source[0]}", type_, inputs,
                               "full fiscal year - first nine months" if inputs else None)
            if view == "geography":
                for name, value in data["gross_profit"].items():
                    key = (view, "gross_profit", name)
                    inputs = [source[2][key], previous[2][key]] if previous else None
                    ids[key] = add(pid, "segment_profit", labels[name], value, sid, f"SEC geographic gross margin, table {source[0]}",
                                   type_, inputs, "full fiscal year - first nine months" if inputs else None, "GAAP gross margin")
            group = data["totals"].get("revenue")
            if group is not None and view == "geography":
                key = (view, "revenue", "Total")
                inputs = [source[2][key], previous[2][key]] if previous else None
                ids[key] = add(pid, "consolidated_revenue", "group", group, sid,
                               f"SEC geographic segment revenue total, table {source[0]}", type_, inputs,
                               "full fiscal year - first nine months" if inputs else None)
                residual = group - sum(data["revenue"].values())
                if residual:
                    add(pid, "revenue_adjustment", "geographic_rounding", residual, sid,
                        f"Reported total less sum of rounded geographic segments, table {source[0]}", type_)
        return ids

    for item in AUDIT:
        pid = item["period_id"]
        q = int(pid[-1])
        if q != 4:
            result = {v: item[v] for v in ("product", "geography")}
            for view in result:
                result[view].append({})
            write(pid, result)
            op = xbrl_op(int(pid[2:6]), q, item["end"])
            add(pid, "consolidated_operating_profit", "group", op["val"] / 1_000_000,
                f"sec_{pid}", f"SEC XBRL OperatingIncomeLoss; {op['accn']}")
        else:
            prev = by_pid[f"FY{pid[2:6]}Q3"]
            assert item["product"] and item["geography"] and prev["product_ytd"] and prev["geography_ytd"]
            annual = {v: [*item[v], {}] for v in ("product", "geography")}
            ytd = {v: [*prev[v + "_ytd"], {}] for v in ("product", "geography")}
            annual_ids = write(pid, annual, "full_year")
            ytd_ids = write(prev["period_id"], ytd, "year_to_date")
            for view in ("product", "geography"):
                a, b = annual[view][1], ytd[view][1]
                if set(a["revenue"]) != set(b["revenue"]):
                    raise ValueError(f"{pid} {view}: category mismatch between annual and nine-month reports")
                quarter = {"revenue": {name: v-b["revenue"][name] for name, v in a["revenue"].items()},
                           "gross_profit": {name: v-b["gross_profit"][name] for name, v in a["gross_profit"].items()},
                           "totals": {name: v-b["totals"][name] for name, v in a["totals"].items() if name in b["totals"]}}
                annual[view][1] = quarter
                annual[view][2] = annual_ids
                ytd[view][2] = ytd_ids
            write(pid, annual, prior=ytd)
            op = xbrl_op(int(pid[2:6]), q, item["end"], cumulative=True)
            prior_op = xbrl_op(int(pid[2:6]), 3, prev["end"], cumulative=True)
            a = add(pid, "consolidated_operating_profit", "group", op["val"] / 1_000_000,
                    f"sec_{pid}", f"SEC XBRL OperatingIncomeLoss; {op['accn']}", "full_year")
            b = add(prev["period_id"], "consolidated_operating_profit", "group", prior_op["val"] / 1_000_000,
                    f"sec_{prev['period_id']}", f"SEC XBRL OperatingIncomeLoss; {prior_op['accn']}", "year_to_date")
            add(pid, "consolidated_operating_profit", "group", (op["val"]-prior_op["val"])/1_000_000,
                f"sec_{pid}", "Full fiscal year minus first nine months", inputs=[a,b], formula="full fiscal year - first nine months")

    for name, entity in labels.items():
        classes.append({"classification_id": f"csco:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "group", "entity_level": "reportable_segment", "valid_from_period_id": "FY2021Q1",
                        "valid_to_period_id": final, "source_id": "sec_FY2021Q1", "locator": "SEC geographic segment note",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    classes.append({"classification_id": "csco:geographic_rounding", "entity_id": "geographic_rounding", "official_name": "取整调节",
                    "parent_entity_id": "group", "entity_level": "adjustment", "valid_from_period_id": "FY2021Q1",
                    "valid_to_period_id": final, "source_id": "sec_FY2021Q1", "locator": "Rounded segment totals",
                    "side": "adjustment", "classification_status": "financial_history_draft"})
    for name in sorted(prod_names):
        entity = name.lower().replace(" ", "_").replace(",", "").replace("-", "_")
        active = [x["period_id"] for x in AUDIT if name in x["product"][1]["revenue"]]
        classes.append({"classification_id": f"csco:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "group", "entity_level": "product_category", "valid_from_period_id": active[0],
                        "valid_to_period_id": active[-1], "source_id": f"sec_{active[0]}", "locator": "SEC revenue by product",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False, profit_chart_label="毛利",
                traditional_intro="正式分部按美洲、EMEA、亚太日本及大中华列示；产品收入为独立披露视图。",
                ai_intro="AI 网络设备收入未作为独立季度收入披露，AI 收入与利润图保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    save("sources", sources)
    save("periods", periods)
    save("facts", facts)
    save("classification", classes)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CSCO", len(periods), "periods", len(facts), "facts")


if __name__ == "__main__":
    main()
