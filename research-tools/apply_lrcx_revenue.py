"""Create Lam Research fiscal-history product revenue without inventing product profit."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database/LRCX/html-research/data"
AUDIT = json.loads((ROOT / "database/LRCX/html-research/checks/revenue-extraction.json").read_text(encoding="utf-8"))
XBRL = json.loads((ROOT / ".research-cache/tier2/companyfacts/LRCX.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]


def save(name, rows):
    (DATA / f"{name}.json").write_text(json.dumps({"schema_version": "full-history-draft-v1", "company_id": "lrcx",
                                              "updated_at": date.today().isoformat(), "records": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def op_row(year, q, end, cumulative=False):
    form, fp = ("10-K", "FY") if q == 4 else ("10-Q", f"Q{q}")
    rows = [x for x in XBRL["OperatingIncomeLoss"]["units"]["USD"] if x.get("fy") == year and x.get("fp") == fp
            and x.get("form") == form and x.get("end") == end and x.get("start")]
    days = lambda x: (date.fromisoformat(end) - date.fromisoformat(x["start"])).days
    rows = [x for x in rows if days(x) > (250 if q == 3 else 340) ] if cumulative or q == 4 else [x for x in rows if 70 <= days(x) <= 112]
    if not rows:
        raise ValueError(f"missing operating income FY{year}Q{q}: {end}")
    return sorted(rows, key=lambda x: (x["filed"], x.get("accn", "")))[0]


def main():
    base = next(f for f in json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"] if f["metric_id"] == "consolidated_revenue")
    sources, periods, facts, classes = [], [], [], []
    by_pid = {x["period_id"]: x for x in AUDIT}
    for item in AUDIT:
        pid = item["period_id"]
        y, q = int(pid[2:6]), int(pid[-1])
        row = op_row(y, q, item["end"], cumulative=q == 4)
        sid = f"sec_{pid}"
        sources.append({"source_id": sid, "publisher": "Lam Research / SEC", "document_type": "Form 10-K" if q == 4 else "Form 10-Q",
                        "title": f"Lam Research {pid} official filing", "url": item["url"], "published_at": row["filed"],
                        "period_end": item["end"], "is_company_official": True})
        end = date.fromisoformat(item["end"])
        periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                        "quarter_end": item["end"], "calendar_quarter": f"{end.year}Q{(end.month-1)//3+1}",
                        "earnings_published_at": row["filed"], "status": "reported", "comparability_events": []})

    def add(pid, metric, entity, value, sid, locator, period_type="quarter", inputs=None, formula=None):
        fact = deepcopy(base)
        fid = f"lrcx:{pid}:{period_type}:{metric}:{entity}"
        fact.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                    original_metric_name="Revenue" if "revenue" in metric else "Operating income",
                    entity_id=entity, parent_entity_id="group", entity_level="group" if entity == "group" else "product_category",
                    value=value, value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                    definition_version="LRCX-fiscal-revenue-categories", accounting_scope="consolidated" if entity == "group" else "product_category",
                    unit_original="USD thousands", currency="USD", scale_original="thousand", display_scale="亿美元")
        fact.pop("side", None)
        if inputs:
            fact["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(fact)
        return fid

    for item in AUDIT:
        pid = item["period_id"]
        q = int(pid[-1])
        sid = f"sec_{pid}"
        if q < 4:
            for entity, raw in item["revenue"][1].items():
                add(pid, "product_revenue", entity, raw / 1000, sid, f"SEC disaggregated revenue, table {item['revenue'][0]}")
            total = sum(item["revenue"][1].values()) / 1000
            add(pid, "consolidated_revenue", "group", total, sid, f"SEC disaggregated revenue, table {item['revenue'][0]}")
            row = op_row(int(pid[2:6]), q, item["end"])
            add(pid, "consolidated_operating_profit", "group", row["val"] / 1_000_000, sid, f"SEC XBRL OperatingIncomeLoss {row['accn']}")
        else:
            prior = by_pid[f"FY{pid[2:6]}Q3"]
            if not prior["ytd"]:
                raise ValueError(f"{pid}: missing nine-month revenue")
            if set(item["revenue"][1]) != set(prior["ytd"][1]):
                raise ValueError(f"{pid}: revenue category mismatch")
            quarterly = []
            for entity, annual_raw in item["revenue"][1].items():
                ytd_raw = prior["ytd"][1][entity]
                annual = add(pid, "product_revenue", entity, annual_raw / 1000, sid,
                             f"SEC annual disaggregated revenue, table {item['revenue'][0]}", "full_year")
                ytd = add(prior["period_id"], "product_revenue", entity, ytd_raw / 1000, f"sec_{prior['period_id']}",
                          f"SEC nine-month disaggregated revenue, table {prior['ytd'][0]}", "year_to_date")
                quarterly.append(add(pid, "product_revenue", entity, (annual_raw-ytd_raw)/1000, sid,
                                     "Full fiscal year minus first nine months", inputs=[annual,ytd], formula="full fiscal year - first nine months"))
            a_total = sum(item["revenue"][1].values()) / 1000
            b_total = sum(prior["ytd"][1].values()) / 1000
            a = add(pid, "consolidated_revenue", "group", a_total, sid, "SEC annual revenue categories", "full_year")
            b = add(prior["period_id"], "consolidated_revenue", "group", b_total, f"sec_{prior['period_id']}",
                    "SEC nine-month revenue categories", "year_to_date")
            add(pid, "consolidated_revenue", "group", a_total-b_total, sid, "Full fiscal year minus first nine months",
                inputs=[a,b], formula="full fiscal year - first nine months")
            op = op_row(int(pid[2:6]), q, item["end"], cumulative=True)
            p_op = op_row(int(pid[2:6]), 3, prior["end"], cumulative=True)
            x = add(pid, "consolidated_operating_profit", "group", op["val"]/1_000_000, sid,
                    f"SEC XBRL OperatingIncomeLoss {op['accn']}", "full_year")
            y = add(prior["period_id"], "consolidated_operating_profit", "group", p_op["val"]/1_000_000,
                    f"sec_{prior['period_id']}", f"SEC XBRL OperatingIncomeLoss {p_op['accn']}", "year_to_date")
            add(pid, "consolidated_operating_profit", "group", (op["val"]-p_op["val"])/1_000_000, sid,
                "Full fiscal year minus first nine months", inputs=[x,y], formula="full fiscal year - first nine months")

    for entity, name in (("systems", "Systems"), ("support", "Customer support and other")):
        classes.append({"classification_id": f"lrcx:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "group", "entity_level": "product_category", "valid_from_period_id": "FY2021Q1",
                        "valid_to_period_id": AUDIT[-1]["period_id"], "source_id": "sec_FY2021Q1",
                        "locator": "SEC disaggregated revenue note", "side": "traditional",
                        "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False,
                traditional_intro="收入按系统设备与客户支持及其他两类披露；公司未披露这两类收入对应的单独利润。",
                ai_intro="未披露可逐季勾稽的独立 AI 产品收入，AI 图卡保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    for name, records in (("sources", sources), ("periods", periods), ("facts", facts), ("classification", classes)):
        save(name, records)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("LRCX", len(periods), "fiscal periods", len(facts), "facts")


if __name__ == "__main__":
    main()
