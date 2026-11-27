"""Build Seagate's full fiscal history at its actual sales-channel disclosure depth."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database/STX/html-research/data"
AUDIT = json.loads((ROOT / "database/STX/html-research/checks/channel-extraction.json").read_text(encoding="utf-8"))
XBRL = json.loads((ROOT / ".research-cache/tier2/companyfacts/STX.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]


def save(name, rows):
    (DATA / f"{name}.json").write_text(json.dumps({"schema_version": "full-history-draft-v1", "company_id": "stx",
                                              "updated_at": date.today().isoformat(), "records": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def xbrl(tag, year, q, end, cumulative=False):
    form, fp = ("10-K", "FY") if q == 4 else ("10-Q", f"Q{q}")
    # Seagate's SEC companyfacts has some incorrect `fy` metadata (notably FY2025).
    # Match the filing period and duration, then take the first official filing.
    rows = [x for x in XBRL[tag]["units"]["USD"] if x.get("form") == form
            and x.get("end") == end and x.get("start")]
    days = lambda x: (date.fromisoformat(end)-date.fromisoformat(x["start"])).days
    rows = [x for x in rows if days(x) > (250 if q == 3 else 340)] if cumulative or q == 4 else [x for x in rows if 70 <= days(x) <= 112]
    if not rows:
        raise ValueError(f"STX {tag} FY{year}Q{q}: no XBRL value")
    return sorted(rows, key=lambda x: (x["filed"], x.get("accn", "")))[0]


def main():
    old_facts = json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"]
    base = next(f for f in old_facts if f["metric_id"] == "consolidated_revenue")
    sources, periods, facts, classes = [], [], [], []
    by_pid = {x["period_id"]: x for x in AUDIT}
    for item in AUDIT:
        pid, end = item["period_id"], item["end"]
        y, q = int(pid[2:6]), int(pid[-1])
        op = xbrl("OperatingIncomeLoss", y, q, end, cumulative=q == 4)
        sid = f"sec_{pid}"
        sources.append({"source_id": sid, "publisher": "Seagate / SEC", "document_type": "Form 10-K" if q == 4 else "Form 10-Q",
                        "title": f"Seagate {pid} official filing", "url": item["url"], "published_at": op["filed"],
                        "period_end": end, "is_company_official": True})
        d = date.fromisoformat(end)
        periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                        "quarter_end": end, "calendar_quarter": f"{d.year}Q{(d.month-1)//3+1}",
                        "earnings_published_at": op["filed"], "status": "reported", "comparability_events": []})

    def add(pid, metric, entity, value, sid, locator, period_type="quarter", inputs=None, formula=None,
            unit="USD millions", level=None):
        fid = f"stx:{pid}:{period_type}:{metric}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                 original_metric_name="Revenue by channel" if metric == "channel_revenue" else "HDD exabytes shipped" if metric == "shipment_quantity" else metric,
                 entity_id=entity, parent_entity_id="storage_segment" if metric == "channel_revenue" else "group",
                 entity_level=level or ("group" if entity == "group" else "reportable_segment" if entity == "storage_segment" else "sales_channel"),
                 value=value, value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                 definition_version="STX-official-fiscal-history", accounting_scope="consolidated",
                 unit_original=unit, currency="USD" if unit == "USD millions" else None,
                 scale_original="million" if unit == "USD millions" else "unit", display_scale="亿美元" if unit == "USD millions" else unit)
        f.pop("side", None)
        if metric == "channel_revenue":
            f["is_exhaustive_child_set"] = period_type == "quarter"
            f["disclosure_view"] = "sales_channel"
        if metric == "shipment_quantity":
            f.update(product_entity_id="storage_segment", measurement_unit="exabytes", value_precision="approximate",
                     comparison_basis="quarter", chart_slot="traditional_progress", original_wording="HDD Exabytes Shipped")
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(f)
        return fid

    for item in AUDIT:
        pid = item["period_id"]
        q = int(pid[-1])
        sid = f"sec_{pid}"
        if q < 4:
            channels = item["channel"][1]
            for name, value in channels.items():
                add(pid, "channel_revenue", name.lower(), value, sid, f"SEC Revenue by Channel, table {item['channel'][0]}")
            total = sum(channels.values())
            add(pid, "consolidated_revenue", "group", total, sid, f"SEC Revenue by Channel, table {item['channel'][0]}")
            add(pid, "segment_revenue", "storage_segment", total, sid, "SEC one reportable segment; same consolidated revenue")
            op = xbrl("OperatingIncomeLoss", int(pid[2:6]), q, item["end"])
            add(pid, "consolidated_operating_profit", "group", op["val"]/1_000_000, sid,
                f"SEC XBRL OperatingIncomeLoss {op['accn']}")
            operating = item["operating"]
            if operating:
                for name, value in operating[1].get("hdd_exabytes", {}).items():
                    if name == "Total":
                        add(pid, "shipment_quantity", "hdd_total", value, sid,
                            f"SEC HDD exabytes shipped, table {operating[0]}", unit="exabytes", level="product")
                for name, value in operating[1].get("market_share_percent", {}).items():
                    add(pid, "market_revenue_mix_percent", name.lower().replace(" ", "_"), value, sid,
                        f"SEC Revenues by Market (%), table {operating[0]}; percentage only, not business revenue",
                        unit="%", level="end_market")
        else:
            prev = by_pid[f"FY{pid[2:6]}Q3"]
            annual, ytd = item["channel"][1], prev["channel_ytd"][1] if prev["channel_ytd"] else None
            if not ytd or set(annual) != set(ytd):
                raise ValueError(f"{pid}: annual and nine-month channel labels differ")
            for name, value in annual.items():
                entity = name.lower()
                a = add(pid, "channel_revenue", entity, value, sid, f"SEC annual revenue by channel, table {item['channel'][0]}", "full_year")
                b = add(prev["period_id"], "channel_revenue", entity, ytd[name], f"sec_{prev['period_id']}",
                        f"SEC nine-month revenue by channel, table {prev['channel_ytd'][0]}", "year_to_date")
                add(pid, "channel_revenue", entity, value-ytd[name], sid, "Full fiscal year minus first nine months",
                    inputs=[a,b], formula="full fiscal year - first nine months")
            total = sum(annual.values())-sum(ytd.values())
            a = add(pid, "consolidated_revenue", "group", sum(annual.values()), sid, "SEC annual channel revenue", "full_year")
            b = add(prev["period_id"], "consolidated_revenue", "group", sum(ytd.values()), f"sec_{prev['period_id']}",
                    "SEC nine-month channel revenue", "year_to_date")
            group = add(pid, "consolidated_revenue", "group", total, sid, "Full fiscal year minus first nine months",
                        inputs=[a,b], formula="full fiscal year - first nine months")
            add(pid, "segment_revenue", "storage_segment", total, sid, "SEC one reportable segment; same consolidated revenue",
                inputs=[group], formula="one reportable segment equals consolidated revenue")
            op = xbrl("OperatingIncomeLoss", int(pid[2:6]), q, item["end"], cumulative=True)
            p_op = xbrl("OperatingIncomeLoss", int(pid[2:6]), 3, prev["end"], cumulative=True)
            x = add(pid, "consolidated_operating_profit", "group", op["val"]/1_000_000, sid,
                    f"SEC XBRL OperatingIncomeLoss {op['accn']}", "full_year")
            y = add(prev["period_id"], "consolidated_operating_profit", "group", p_op["val"]/1_000_000,
                    f"sec_{prev['period_id']}", f"SEC XBRL OperatingIncomeLoss {p_op['accn']}", "year_to_date")
            add(pid, "consolidated_operating_profit", "group", (op["val"]-p_op["val"])/1_000_000, sid,
                "Full fiscal year minus first nine months", inputs=[x,y], formula="full fiscal year - first nine months")

    classes.append({"classification_id": "stx:storage_segment", "entity_id": "storage_segment", "official_name": "数据存储（唯一报告分部）",
                    "parent_entity_id": "group", "entity_level": "reportable_segment", "valid_from_period_id": "FY2021Q1",
                    "valid_to_period_id": "FY2027Q1", "source_id": "sec_FY2026Q4", "locator": "SEC segment reporting: single reportable segment",
                    "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    for name in ("OEMs", "Distributors", "Retailers"):
        classes.append({"classification_id": f"stx:{name.lower()}", "entity_id": name.lower(), "official_name": f"销售渠道：{name}",
                        "parent_entity_id": "storage_segment", "entity_level": "sales_channel", "valid_from_period_id": "FY2021Q1",
                        "valid_to_period_id": "FY2027Q1", "source_id": "sec_FY2021Q1", "locator": "SEC Revenues by Channel",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False,
                traditional_intro="公司仅披露一个正式业务分部；可加总收入明细为 OEM、分销商、零售商销售渠道。终端市场仅披露百分比，未换算成金额。",
                ai_intro="没有可单独勾稽的 AI 存储收入，AI 收入与利润图保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    view["chart_context_notes"] = {"g2": "这是销售渠道收入，不是产品或终端市场收入；产品利润未披露。",
                                   "g3": "仅有集团营业利润，未按销售渠道或产品披露利润，故明细利润留空。"}
    for name, rows in (("sources", sources), ("periods", periods), ("facts", facts), ("classification", classes)):
        save(name, rows)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("STX", len(periods), "quarters", len(facts), "facts")


if __name__ == "__main__":
    main()
