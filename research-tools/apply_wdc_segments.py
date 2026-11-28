"""Rebuild WDC with an explicit FY2025Q3 Flash-separation scope break."""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database/WDC/html-research/data"
AUDIT = json.loads((ROOT / "database/WDC/html-research/checks/segment-extraction.json").read_text(encoding="utf-8"))
XBRL = json.loads((ROOT / ".research-cache/tier2/companyfacts/WDC.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]
BREAK = "FY2025Q3"


def save(name, rows):
    (DATA / f"{name}.json").write_text(json.dumps({"schema_version": "full-history-draft-v1", "company_id": "wdc",
                                              "updated_at": date.today().isoformat(), "records": rows}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def xbrl(tag, year, q, end, cumulative=False):
    form, fp = ("10-K", "FY") if q == 4 else ("10-Q", f"Q{q}")
    rows = [x for x in XBRL[tag]["units"]["USD"] if x.get("fy") == year and x.get("fp") == fp
            and x.get("form") == form and x.get("end") == end and x.get("start")]
    days = lambda x: (date.fromisoformat(end)-date.fromisoformat(x["start"])).days
    rows = [x for x in rows if days(x) > (250 if q == 3 else 340)] if cumulative or q == 4 else [x for x in rows if 70 <= days(x) <= 112]
    if not rows:
        raise ValueError(f"WDC {tag} FY{year}Q{q}: no XBRL value")
    return sorted(rows, key=lambda x: (x["filed"], x.get("accn", "")))[0]


def norm_segment(name, pid):
    return ("flash_pre" if name.lower().startswith("flash") else "hdd_pre") if pid < BREAK else "hdd_post"


def main():
    base = next(f for f in json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"] if f["metric_id"] == "consolidated_revenue")
    sources, periods, facts, classes = [], [], [], []
    by_pid = {x["period_id"]: x for x in AUDIT}
    for item in AUDIT:
        pid, end = item["period_id"], item["end"]
        y, q = int(pid[2:6]), int(pid[-1])
        op = xbrl("OperatingIncomeLoss", y, q, end, cumulative=q == 4)
        sid = f"sec_{pid}"
        sources.append({"source_id": sid, "publisher": "Western Digital / SEC", "document_type": "Form 10-K" if q == 4 else "Form 10-Q",
                        "title": f"Western Digital {pid} official filing", "url": item["url"], "published_at": op["filed"],
                        "period_end": end, "is_company_official": True})
        d = date.fromisoformat(end)
        periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                        "quarter_end": end, "calendar_quarter": f"{d.year}Q{(d.month-1)//3+1}",
                        "earnings_published_at": op["filed"], "status": "reported",
                        "comparability_events": ["Flash 分拆完成，集团改为仅 HDD 持续经营；不得与旧集团直接连成同口径"] if pid == BREAK else []})

    def add(pid, metric, entity, value, sid, locator, period_type="quarter", inputs=None, formula=None, basis=None):
        fid = f"wdc:{pid}:{period_type}:{metric}:{entity}"
        f = deepcopy(base)
        f.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                 original_metric_name="Gross profit" if basis == "gross" else "Net income" if basis == "net" else "Revenue" if "revenue" in metric else "Operating income",
                 entity_id=entity, parent_entity_id="group", entity_level="group" if entity == "group" else "reportable_segment" if entity in ("hdd_pre","flash_pre","hdd_post") else "product_category",
                 value=value, value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                 definition_version="WDC-pre-separation" if pid < BREAK else "WDC-HDD-continuing",
                 accounting_scope="pre_separation_group" if pid < BREAK else "continuing_operations",
                 unit_original="USD millions", currency="USD", scale_original="million", display_scale="亿美元")
        f.pop("side", None)
        if basis:
            f["profit_basis"] = "GAAP gross profit" if basis == "gross" else "CODM consolidated net income"
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(f)
        return fid

    def adjusted_data(item, view):
        # Standardize Flash-based and Flash across the old reporting regime.
        data = deepcopy(item[view][1]) if item[view] else None
        if data and view == "segment":
            for part in ("revenue", "gross_profit"):
                if "Flash-based" in data[part]:
                    data[part]["Flash"] = data[part].pop("Flash-based")
        return data

    def write(pid, item, type_="quarter", prior=None):
        sid = f"sec_{pid}"
        ids = {}
        for view in ("market", "segment"):
            if not item[view]:
                continue
            data = adjusted_data(item, view)
            old = adjusted_data(prior, view) if prior else None
            for metric_name in ("revenue", "gross_profit"):
                for name, value in data[metric_name].items():
                    entity = norm_segment(name, pid) if view == "segment" else name.lower().replace(" ", "_").replace("&", "and")
                    metric = "segment_revenue" if view == "segment" and metric_name == "revenue" else "segment_profit" if view == "segment" else "product_revenue"
                    if view == "market" and metric_name != "revenue":
                        continue
                    key = (view, metric_name, name)
                    inputs = [item["ids"][key], prior["ids"][key]] if prior else None
                    ids[key] = add(pid, metric, entity, value, sid, f"SEC business disclosure table {item[view][0]}", type_, inputs,
                                   "full fiscal year - first nine months" if inputs else None,
                                   "gross" if metric_name == "gross_profit" else None)
        group = sum(adjusted_data(item, "market")["revenue"].values())
        key = ("group", "revenue", "Total")
        inputs = [item["ids"][key], prior["ids"][key]] if prior else None
        ids[key] = add(pid, "consolidated_revenue", "group", group, sid,
                       f"SEC end-market revenue total, table {item['market'][0]}", type_, inputs,
                       "full fiscal year - first nine months" if inputs else None)
        return ids

    for item in AUDIT:
        pid = item["period_id"]
        q = int(pid[-1])
        if q < 4:
            write(pid, {**item, "ids": {}})
            op = xbrl("OperatingIncomeLoss", int(pid[2:6]), q, item["end"])
            add(pid, "consolidated_operating_profit", "group", op["val"]/1_000_000, f"sec_{pid}",
                f"SEC XBRL OperatingIncomeLoss {op['accn']}")
        else:
            prev = by_pid[f"FY{pid[2:6]}Q3"]
            a = {**item, "ids": {}}
            b = {"market": prev["market_ytd"], "segment": prev["segment_ytd"], "ids": {}}
            if not b["market"]:
                raise ValueError(f"{pid}: no nine-month end-market values")
            a["ids"] = write(pid, a, "full_year")
            b["ids"] = write(prev["period_id"], b, "year_to_date")
            quarter = {"ids": a["ids"]}
            for view in ("market", "segment"):
                if not a[view]:
                    quarter[view] = None
                    continue
                av, bv = adjusted_data(a, view), adjusted_data(b, view)
                if not bv or set(av["revenue"]) != set(bv["revenue"]):
                    raise ValueError(f"{pid} {view}: annual and nine-month labels differ")
                quarter[view] = [a[view][0], {metric: {name: v-bv[metric][name] for name, v in av[metric].items()}
                                              for metric in ("revenue", "gross_profit")}]
            write(pid, quarter, prior=b)
            op = xbrl("OperatingIncomeLoss", int(pid[2:6]), q, item["end"], cumulative=True)
            p_op = xbrl("OperatingIncomeLoss", int(pid[2:6]), 3, prev["end"], cumulative=True)
            x = add(pid, "consolidated_operating_profit", "group", op["val"]/1_000_000, f"sec_{pid}",
                    f"SEC XBRL OperatingIncomeLoss {op['accn']}", "full_year")
            y = add(prev["period_id"], "consolidated_operating_profit", "group", p_op["val"]/1_000_000,
                    f"sec_{prev['period_id']}", f"SEC XBRL OperatingIncomeLoss {p_op['accn']}", "year_to_date")
            add(pid, "consolidated_operating_profit", "group", (op["val"]-p_op["val"])/1_000_000,
                f"sec_{pid}", "Full fiscal year minus first nine months", inputs=[x,y], formula="full fiscal year - first nine months")

    # After the Flash separation, HDD is the only formal reportable segment.
    # Revenue equals continuing-operations group revenue; CODM profit is
    # income from continuing operations, not group operating income.
    for period in periods:
        pid = period["period_id"]
        if pid < BREAK:
            continue
        sid, year, quarter = f"sec_{pid}", period["fiscal_year"], period["fiscal_quarter"]
        group = next(f for f in facts if f["period_id"] == pid and f["period_type"] == "quarter" and f["metric_id"] == "consolidated_revenue" and f["entity_id"] == "group")
        add(pid, "segment_revenue", "hdd_post", group["value"], sid,
            "Only reportable segment HDD; continuing-operations revenue (FY2026 10-K segment note)",
            inputs=[group["fact_id"]], formula="sole HDD segment = continuing-operations group revenue")
        tag = "IncomeLossFromContinuingOperations"
        if quarter < 4:
            try:
                item = xbrl(tag, year, quarter, period["quarter_end"])
            except ValueError:
                # After discontinued operations cease to be separately reported,
                # consolidated net income is the sole HDD segment CODM measure.
                if pid != "FY2027Q1":
                    raise
                tag = "NetIncomeLoss"
                item = xbrl(tag, year, quarter, period["quarter_end"])
            add(pid, "segment_profit", "hdd_post", item["val"] / 1_000_000, sid,
                f"SEC XBRL {tag} {item['accn']}; CODM profit measure", basis="codm")
        else:
            prev = next(p for p in periods if p["fiscal_year"] == year and p["fiscal_quarter"] == 3)
            full = xbrl(tag, year, 4, period["quarter_end"], cumulative=True)
            nine = xbrl(tag, year, 3, prev["quarter_end"], cumulative=True)
            fid_full = add(pid, "segment_profit", "hdd_post", full["val"] / 1_000_000, sid,
                           f"SEC XBRL {tag} full fiscal year {full['accn']}", "full_year", basis="codm")
            fid_nine = add(prev["period_id"], "segment_profit", "hdd_post", nine["val"] / 1_000_000,
                           f"sec_{prev['period_id']}", f"SEC XBRL {tag} nine months {nine['accn']}", "year_to_date", basis="codm")
            add(pid, "segment_profit", "hdd_post", (full["val"] - nine["val"]) / 1_000_000, sid,
                "Full fiscal year less first nine months; CODM continuing-operations income", inputs=[fid_full, fid_nine],
                formula="full fiscal year - first nine months", basis="codm")

    for entity, name, first, last in (("hdd_pre", "HDD（分拆前）", "FY2021Q1", "FY2025Q2"),
                                      ("flash_pre", "Flash（分拆前）", "FY2021Q1", "FY2025Q2"),
                                      ("hdd_post", "HDD（持续经营）", "FY2025Q3", "FY2027Q1")):
        classes.append({"classification_id": f"wdc:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "group", "entity_level": "reportable_segment", "valid_from_period_id": first,
                        "valid_to_period_id": last, "source_id": f"sec_{first}", "locator": "SEC segment disclosure and separation note",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only",
                        "break_from_previous": entity == "hdd_post"})
    markets = {}
    for item in AUDIT:
        for name in item["market"][1]["revenue"]:
            markets.setdefault(name, []).append(item["period_id"])
    for name, active in markets.items():
        entity = name.lower().replace(" ", "_").replace("&", "and")
        classes.append({"classification_id": f"wdc:{entity}", "entity_id": entity, "official_name": name,
                        "parent_entity_id": "group", "entity_level": "product_category", "valid_from_period_id": active[0],
                        "valid_to_period_id": active[-1], "source_id": f"sec_{active[0]}", "locator": "SEC revenue by end market",
                        "side": "traditional", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"})
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False, profit_chart_label="毛利",
                traditional_intro="分拆前按 HDD 与 Flash 正式分部列示；FY2025Q3 起仅保留 HDD 持续经营，历史集团口径在此断开。",
                ai_intro="公司未披露可独立勾稽的 AI 存储收入，AI 图卡保留空值。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    view["chart_context_notes"] = {"g1": "FY2025Q3 完成 Flash 分拆；此前为 HDD+Flash 集团，此后为 HDD 持续经营。",
                                   "g3": "分拆前若有披露，展示 HDD 与 Flash 分部毛利；分拆后产品级毛利未披露。"}
    for name, rows in (("sources", sources), ("periods", periods), ("facts", facts), ("classification", classes)):
        save(name, rows)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("WDC", len(periods), "quarters", len(facts), "facts")


if __name__ == "__main__":
    main()
