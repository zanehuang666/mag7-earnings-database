"""Reconstruct CoreWeave's disclosed 2024–2026 quarterly history from SEC XBRL.

2024 comparatives are in 2025 10-Qs and the 2025 10-K. CoreWeave has one
reportable segment; consolidated net loss is the CODM's segment-profit measure.
"""
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "database/CRWV/html-research/data"
XBRL = json.loads((ROOT / ".research-cache/tier2/companyfacts/CRWV.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]
TAGS = {"consolidated_revenue": "RevenueFromContractWithCustomerExcludingAssessedTax",
        "consolidated_operating_profit": "OperatingIncomeLoss", "segment_profit": "NetIncomeLoss",
        "ocf": "NetCashProvidedByUsedInOperatingActivities", "cash_capex": "PaymentsToAcquirePropertyPlantAndEquipment"}


def save(name, rows):
    obj = {"schema_version": "full-history-draft-v1", "company_id": "crwv", "updated_at": date.today().isoformat(), "records": rows}
    (DATA / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def select(tag, start, end):
    rows = [x for x in XBRL[tag]["units"]["USD"] if x.get("start") == start and x.get("end") == end
            and x.get("form") in ("10-Q", "10-K")]
    if not rows:
        raise ValueError(f"missing {tag} {start}–{end}")
    rows.sort(key=lambda x: (x["filed"], x.get("accn", "")))
    return rows[0]


def main():
    old_sources = json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["records"]
    old = {s["source_id"]: s for s in old_sources}
    old_facts = json.loads((DATA / "facts.json").read_text(encoding="utf-8"))["records"]
    base = next(f for f in old_facts if f["metric_id"] == "consolidated_revenue")
    periods, sources, facts = [], [], []
    end_by_q = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}
    accn_to_old = {s["url"].split("/")[-2]: s for s in old_sources}
    # SEC URL accession folder removes dashes, unlike XBRL's accn field.
    accn_to_old = {key: s for key, s in accn_to_old.items()}
    coverage = {}
    for y in (2024, 2025, 2026):
        for q in range(1, 5):
            if y == 2026 and q == 4:
                continue
            pid, end = f"{y}Q{q}", f"{y}-{end_by_q[q]}"
            start = f"{y}-01-01"
            ref = select(TAGS["consolidated_revenue"], start, end)
            accession = ref["accn"].replace("-", "")
            src = accn_to_old.get(accession)
            if src is None:
                raise ValueError(f"{pid}: source accession {accession} missing")
            sid = f"sec_{pid}"
            sources.append({"source_id": sid, "publisher": "CoreWeave / SEC", "document_type": ref["form"],
                            "title": f"CoreWeave {pid} {'comparative' if y == 2024 else 'current'} SEC filing",
                            "url": src["url"], "published_at": ref["filed"], "period_end": end,
                            "is_company_official": True})
            periods.append({"period_id": pid, "fiscal_year": y, "fiscal_quarter": q, "fiscal_label": pid,
                            "quarter_end": end, "calendar_quarter": pid, "earnings_published_at": ref["filed"],
                            "status": "reported", "comparability_events": ["上市前比较期，依据后续 SEC 文件披露"] if y == 2024 else []})
            coverage[pid] = {"source_id": sid, "source_url": src["url"]}

    def add(pid, metric, value, source, locator, period_type="quarter", inputs=None, formula=None):
        f = deepcopy(base)
        entity = "ai_cloud" if metric == "segment_profit" else "group"
        fid = f"crwv:{pid}:{period_type}:{metric}:{entity}"
        f.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                 original_metric_name="Net loss" if metric == "segment_profit" else TAGS.get(metric, metric),
                 entity_id=entity, parent_entity_id="group", entity_level="reportable_segment" if entity == "ai_cloud" else "group",
                 value=value, value_status="derived" if inputs else "reported", source_id=source, locator=locator,
                 definition_version="CRWV-SEC-XBRL-2024-2026", accounting_scope="consolidated",
                 unit_original="USD", currency="USD", scale_original="unit", display_scale="亿美元")
        f.pop("side", None)
        if metric == "segment_profit":
            f["profit_basis"] = "CODM consolidated net loss"
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        facts.append(f)
        return fid

    by_pid = {p["period_id"]: p for p in periods}
    for y in (2024, 2025, 2026):
        prior_cash = {}
        for q in range(1, 5):
            if y == 2026 and q == 4:
                continue
            pid, end = f"{y}Q{q}", by_pid[f"{y}Q{q}"]["quarter_end"]
            sid = coverage[pid]["source_id"]
            start_q = f"{y}-01-01" if q == 1 else (date(y, [1,4,7,10][q-1], 1)).isoformat()
            start_y = f"{y}-01-01"
            for metric in ("consolidated_revenue", "consolidated_operating_profit", "segment_profit"):
                tag = TAGS[metric]
                if q < 4:
                    row = select(tag, start_q, end)
                    add(pid, metric, row["val"] / 1_000_000, sid,
                        f"SEC XBRL {tag}; accession {row['accn']}; {row['start']} to {row['end']}")
                else:
                    annual = select(tag, start_y, end)
                    prev_pid = f"{y}Q3"
                    prev = select(tag, start_y, by_pid[prev_pid]["quarter_end"])
                    a = add(pid, metric, annual["val"] / 1_000_000, sid,
                            f"SEC XBRL {tag}; accession {annual['accn']}", "full_year")
                    b = add(prev_pid, metric, prev["val"] / 1_000_000, coverage[prev_pid]["source_id"],
                            f"SEC XBRL {tag}; accession {prev['accn']}", "year_to_date")
                    add(pid, metric, (annual["val"]-prev["val"]) / 1_000_000, sid,
                        "Full fiscal year minus first nine months", inputs=[a,b], formula="full fiscal year - first nine months")
            # The sole formal segment has the same revenue as the consolidated company.
            group = next(f for f in reversed(facts) if f["period_id"] == pid and f["period_type"] == "quarter" and f["metric_id"] == "consolidated_revenue")
            add(pid, "segment_revenue", group["value"], sid,
                "SEC segment reporting: one reportable segment; consolidated revenue")
            for metric in ("ocf", "cash_capex"):
                tag = TAGS[metric]
                raw = select(tag, start_y, end)
                cumulative = raw["val"] / 1_000_000
                raw_metric = "ocf" if metric == "ocf" else "purchase_ppe_cash"
                raw_id = add(pid, raw_metric, cumulative, sid,
                             f"SEC XBRL {tag}; accession {raw['accn']}; {raw['start']} to {raw['end']}",
                             "full_year" if q == 4 else "year_to_date")
                value = cumulative if q == 1 else cumulative - prior_cash[metric]["cumulative"]
                inputs = [raw_id] if q == 1 else [raw_id, prior_cash[metric]["id"]]
                qid = add(pid, metric, value, sid, f"Quarterly {tag} from SEC cumulative cash flow",
                          inputs=inputs, formula="first fiscal quarter cumulative" if q == 1 else "current cumulative - previous cumulative")
                prior_cash[metric] = {"cumulative": cumulative, "id": raw_id, "quarter": value, "quarter_id": qid}
            add(pid, "derived_fcf", prior_cash["ocf"]["quarter"]-prior_cash["cash_capex"]["quarter"], sid,
                "Quarterly operating cash flow less cash PP&E purchases",
                inputs=[prior_cash["ocf"]["quarter_id"], prior_cash["cash_capex"]["quarter_id"]], formula="ocf - cash_capex")

    classes = [{"classification_id": "crwv:ai_cloud", "entity_id": "ai_cloud", "official_name": "AI 云基础设施",
                "parent_entity_id": "group", "entity_level": "reportable_segment", "valid_from_period_id": "2024Q1",
                "valid_to_period_id": "2026Q3", "source_id": "sec_2025Q4",
                "locator": "2025 10-K segment reporting: one operating and reportable segment; CODM uses consolidated net loss",
                "side": "ai", "classification_status": "financial_history_draft", "external_revenue_scope": "external_only"}]
    view = json.loads((DATA / "report-view.json").read_text(encoding="utf-8"))
    view.update(research_status="financial_history_draft", group_only_profit=False, profit_chart_label="净利润",
                traditional_intro="公司仅披露一个正式报告分部，没有可勾稽的传统业务收入。",
                ai_intro="AI 云基础设施为唯一报告分部；产品和服务收入未单独披露，利润按管理层使用的集团净亏损口径列示。")
    for key in ("auto_generated_from_official_packets", "source_digest", "output_sha256", "chart_context_notes"):
        view.pop(key, None)
    for name, rows in (("sources", sources), ("periods", periods), ("facts", facts), ("classification", classes)):
        save(name, rows)
    (DATA / "report-view.json").write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    check = ROOT / "database/CRWV/html-research/checks/xbrl-coverage.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps(coverage, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("CRWV", len(periods), "quarters", len(facts), "facts")


if __name__ == "__main__":
    main()
