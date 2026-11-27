"""Reconstruct fiscal-quarter OCF, cash PP&E purchases and FCF from SEC XBRL.

Uses the filing's year-to-date cash flows; Q2/Q3/Q4 are exact differences of
two official filings.  Raw cumulative inputs remain in facts.json.
"""
import argparse
import json
from copy import deepcopy
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TAGS = {"ocf": "NetCashProvidedByUsedInOperatingActivities",
        "cash_capex": "PaymentsToAcquirePropertyPlantAndEquipment"}


def choose(rows, year, quarter, end):
    fp = "FY" if quarter == 4 else f"Q{quarter}"
    form = "10-K" if quarter == 4 else "10-Q"
    found = [x for x in rows if x.get("fy") == year and x.get("fp") == fp and x.get("form") == form and x.get("end") == end and x.get("start")]
    if not found:
        # Some issuer companyfacts records carry an incorrect fiscal-year label.
        # The exact report end, form, and cumulative start still identify the filing.
        from datetime import date
        candidates = [x for x in rows if x.get("form") == form and x.get("end") == end and x.get("start")]
        span = lambda x: (date.fromisoformat(end)-date.fromisoformat(x["start"])).days
        found = [x for x in candidates if span(x) >= (340 if quarter == 4 else 250 if quarter == 3 else 155 if quarter == 2 else 70)]
    if not found:
        raise ValueError(f"SEC XBRL not found: FY{year}Q{quarter} end={end}")
    found.sort(key=lambda x: (x["filed"], x.get("accn", "")))
    return found[0]


def main(ticker):
    data_dir = ROOT / "database" / ticker / "html-research" / "data"
    companyfacts = json.loads((ROOT / ".research-cache" / "tier2" / "companyfacts" / f"{ticker}.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]
    facts_payload = json.loads((data_dir / "facts.json").read_text(encoding="utf-8"))
    periods = json.loads((data_dir / "periods.json").read_text(encoding="utf-8"))["records"]
    sources = {s["source_id"] for s in json.loads((data_dir / "sources.json").read_text(encoding="utf-8"))["records"]}
    original = [f for f in facts_payload["records"] if f.get("metric_id") not in ("ocf", "cash_capex", "derived_fcf", "purchase_ppe_cash")]
    base = next(f for f in original if f.get("metric_id") == "consolidated_revenue")
    rows = []

    def add(period, metric, value, source, locator, period_type="quarter", inputs=None, formula=None):
        f = deepcopy(base)
        fid = f"tier2cash:{period}:{period_type}:{metric}"
        f.update(fact_id=fid, period_id=period, period_type=period_type, metric_id=metric,
                 original_metric_name=TAGS["ocf"] if metric == "ocf" else TAGS["cash_capex"] if metric in ("cash_capex", "purchase_ppe_cash") else "Research free cash flow",
                 entity_id="group", parent_entity_id="group", entity_level="group", value=value,
                 value_status="derived" if inputs else "reported", source_id=source,
                 locator=locator, accounting_scope="consolidated", definition_version=f"SEC-XBRL-{metric}",
                 unit_original="USD millions", currency="USD", scale_original="million", tier2_cashflow_research=True)
        f.pop("side", None)
        if inputs:
            f["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        rows.append(f)
        return fid

    for year in sorted({p["fiscal_year"] for p in periods}):
        prior = {}
        for quarter in range(1, 5):
            period = next((p for p in periods if p["fiscal_year"] == year and p["fiscal_quarter"] == quarter), None)
            if not period or not period.get("quarter_end"):
                continue
            pid = period["period_id"]
            sid = f"sec_{pid}" if f"sec_{pid}" in sources else f"official_{pid}"
            if sid not in sources:
                raise ValueError(f"{pid}: source {sid} missing")
            source_values = {}
            for metric, tag in TAGS.items():
                data = companyfacts[tag]["units"]["USD"]
                item = choose(data, year, quarter, period["quarter_end"])
                value = item["val"] / 1_000_000
                raw_metric = "ocf" if metric == "ocf" else "purchase_ppe_cash"
                raw_type = "full_year" if quarter == 4 else "year_to_date"
                locator = f"SEC XBRL {tag}; accession {item['accn']}; {item['start']} to {item['end']}"
                raw_id = add(pid, raw_metric, value, sid, locator, raw_type)
                if quarter == 1:
                    inputs = [raw_id]
                    qvalue = value
                    formula = "quarter = fiscal Q1 cumulative"
                else:
                    inputs = [raw_id, prior[metric]["raw_id"]]
                    qvalue = value - prior[metric]["cumulative"]
                    formula = "current cumulative - previous cumulative"
                qid = add(pid, metric, qvalue, sid, locator, inputs=inputs, formula=formula)
                source_values[metric] = {"raw_id": raw_id, "cumulative": value, "quarter_id": qid, "quarter_value": qvalue}
            add(pid, "derived_fcf", source_values["ocf"]["quarter_value"] - source_values["cash_capex"]["quarter_value"], sid,
                "Research FCF = quarterly operating cash flow - quarterly cash PP&E purchases",
                inputs=[source_values["ocf"]["quarter_id"], source_values["cash_capex"]["quarter_id"]], formula="ocf - cash_capex")
            prior = source_values
    facts_payload["records"] = original + rows
    facts_payload["schema_version"] = "full-history-draft-v1"
    facts_payload["updated_at"] = date.today().isoformat()
    (data_dir / "facts.json").write_text(json.dumps(facts_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(ticker, len(rows), "cash-flow facts")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("tickers", nargs="+")
    args = ap.parse_args()
    for ticker in args.tickers:
        main(ticker)
