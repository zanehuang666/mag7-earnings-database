"""Reconstruct Lam Research quarterly cash flows from its official cash-flow statements."""
import io
import json
import re
from copy import deepcopy
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/LRCX/html-research"
CACHE = ROOT / ".research-cache/tier2/LRCX"
AUDIT = json.loads((BASE / "checks/revenue-extraction.json").read_text(encoding="utf-8"))


def number(row):
    vals = []
    for raw in row[1:]:
        x = str(raw).strip().replace(",", "").replace("$", "")
        if x and x != "nan" and (not vals or vals[-1] != x):
            vals.append(x)
    for x in vals:
        if re.fullmatch(r"\(?-?\d+\)?", x):
            return -int(x[1:-1]) if x.startswith("(") else int(x)
    return None


def read(item):
    name = f"official_{item['old_id']}" if item["old_id"] else item["period_id"]
    tables = pd.read_html(io.BytesIO((CACHE / f"{name}.html").read_bytes()))
    for index, table in enumerate(tables):
        text = table.to_string().lower()
        if "cash flows from operating activities" not in text or "cash flows from investing activities" not in text:
            continue
        values = {}
        for row in table.astype(str).values.tolist():
            name = str(row[0]).strip().lower()
            if name == "net cash provided by operating activities":
                values["ocf"] = number(row)
            elif name.startswith("capital expenditures") and not name.startswith("capital expenditures incurred"):
                values["cash_capex"] = abs(number(row)) if number(row) is not None else None
                values["cash_capex_label"] = name
        if isinstance(values.get("ocf"), int) and isinstance(values.get("cash_capex"), int):
            return {"table": index, **values}
    raise ValueError(f"cash flow table missing for {item['period_id']}")


def main():
    path = BASE / "data/facts.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = [x for x in payload["records"] if not x.get("lrcx_cash_research")]
    base = next(x for x in facts if x["metric_id"] == "consolidated_revenue")
    sources = {x["source_id"] for x in json.loads((BASE / "data/sources.json").read_text(encoding="utf-8"))["records"]}
    results = []
    new = []

    def add(pid, metric, value, sid, locator, period_type="quarter", inputs=None, formula=None):
        if sid not in sources:
            raise ValueError(f"unknown source {sid}")
        x = deepcopy(base)
        fid = f"lrcxcash:{pid}:{period_type}:{metric}"
        x.update(fact_id=fid, period_id=pid, period_type=period_type, metric_id=metric,
                 original_metric_name="Net cash provided by operating activities" if metric == "ocf" else "Capital expenditures and intangible assets" if metric in ("cash_capex", "purchase_ppe_cash") else "Research free cash flow",
                 entity_id="group", parent_entity_id="group", entity_level="group", value=value,
                 value_status="derived" if inputs else "reported", source_id=sid, locator=locator,
                 definition_version="LRCX-cashflow-including-intangibles", accounting_scope="consolidated",
                 unit_original="USD thousands", currency="USD", scale_original="thousand", lrcx_cash_research=True)
        if inputs:
            x["derivation"] = {"formula": formula, "input_fact_ids": inputs}
        new.append(x)
        return fid

    prior = {}
    for item in AUDIT:
        pid = item["period_id"]
        q = int(pid[-1])
        raw = read(item)
        results.append({"period_id": pid, **raw})
        sid = f"sec_{pid}"
        current = {}
        for metric in ("ocf", "cash_capex"):
            cumulative = raw[metric] / 1000
            locator = f"SEC cash flow statement, table {raw['table']}; {raw.get('cash_capex_label') if metric=='cash_capex' else 'operating cash flow'}"
            raw_type = "full_year" if q == 4 else "year_to_date"
            original = add(pid, metric if metric == "ocf" else "purchase_ppe_cash", cumulative, sid, locator, raw_type)
            if q == 1:
                value = cumulative
                inputs = [original]
                formula = "first fiscal quarter cumulative"
            else:
                value = cumulative - prior[metric]["value"]
                inputs = [original, prior[metric]["id"]]
                formula = "current cumulative - previous cumulative"
            current[metric] = {"value": cumulative, "id": original, "quarter": value,
                               "quarter_id": add(pid, metric, value, sid, locator, inputs=inputs, formula=formula)}
        add(pid, "derived_fcf", current["ocf"]["quarter"] - current["cash_capex"]["quarter"], sid,
            "Operating cash flow less company cash capital expenditures and intangible assets",
            inputs=[current["ocf"]["quarter_id"], current["cash_capex"]["quarter_id"]], formula="ocf - cash_capex")
        prior = {} if q == 4 else current
    payload["records"] = facts + new
    payload["updated_at"] = date.today().isoformat()
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    check = BASE / "checks/cash-extraction.json"
    check.write_text(json.dumps(results, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("LRCX", len(new), "cash flow facts", {x["cash_capex_label"] for x in results})


if __name__ == "__main__":
    main()
