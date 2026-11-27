"""Audit Cisco's fiscal-quarter product and geographic disclosures from SEC filings."""
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/CSCO/html-research"
CACHE = ROOT / ".research-cache/tier2/CSCO"
PRODUCTS = {"Infrastructure Platforms", "Applications", "Security", "Other Products",
            "Networking", "Collaboration", "Observability", "Services",
            "Secure, Agile Networks", "Hybrid Work", "End-to-End Security",
            "Internet for the Future", "Optimized Application Experiences"}
REGIONS = {"Americas", "EMEA", "APJC"}


def distinct(row):
    out = []
    for cell in row:
        value = str(cell).strip().replace("\xa0", " ")
        if value != "nan" and value and (not out or out[-1] != value):
            out.append(value)
    return out


def numeric(row, start=0):
    for value in distinct(row[start:])[1 if start == 0 else 0:]:
        value = value.replace(",", "").replace("$", "").strip()
        if re.fullmatch(r"\(?-?\d+\)?", value):
            return -int(value[1:-1]) if value.startswith("(") else int(value)
    return None


def parse_table(table, kind, ytd=False):
    rows = [distinct(row) for row in table.astype(str).values.tolist()]
    labels = [row[0] for row in rows if row]
    start = 0
    if ytd:
        headers = table.astype(str).values.tolist()[:4]
        starts = [i for row in headers for i, v in enumerate(row) if "Nine Months Ended" in v]
        if not starts:
            return None
        start = min(starts)
    if kind == "product":
        if "Services" not in labels or not (set(labels) & (PRODUCTS - {"Services"})):
            return None
        wanted = PRODUCTS
    else:
        if not REGIONS.issubset(labels) or not any(x.lower().startswith("gross margin") for x in labels):
            return None
        wanted = REGIONS
    parts = {"revenue": {}, "gross_profit": {}, "totals": {}}
    section = "revenue"
    for row in table.astype(str).values.tolist():
        vals = distinct(row)
        if not vals:
            continue
        label = vals[0]
        if label.lower().startswith("gross margin"):
            section = "gross_profit"
        elif label in wanted:
            value = numeric(row, start)
            if value is not None:
                parts[section][label] = value
        elif label in ("Total", "Total (1)", "Total revenue"):
            value = numeric(row, start)
            if value is not None:
                parts["totals"][section] = value
    if kind == "product":
        return parts if len(parts["revenue"]) >= 4 else None
    return parts if len(parts["revenue"]) == 3 and len(parts["gross_profit"]) == 3 else None


def extract(path):
    tables = pd.read_html(io.BytesIO(path.read_bytes()))
    candidates = {kind: [] for kind in ("product", "geography", "product_ytd", "geography_ytd")}
    for index, table in enumerate(tables):
        for kind in candidates:
            result = parse_table(table, kind.removesuffix("_ytd"), kind.endswith("_ytd"))
            if result:
                candidates[kind].append((index, result))
    # Prefer the detailed segment note toward the end over duplicate MD&A tables.
    return {kind: rows[-1] if rows else None for kind, rows in candidates.items()}


def main():
    periods = json.loads((BASE / "data/periods.json").read_text(encoding="utf-8"))["records"]
    sources = {s["source_id"]: s for s in json.loads((BASE / "data/sources.json").read_text(encoding="utf-8"))["records"]}
    out = []
    for period in periods:
        sid = f"official_{period['period_id']}"
        path = CACHE / f"{sid}.html"
        end = period["quarter_end"]
        if not path.exists() or not end:
            out.append({"old_id": period["period_id"], "error": "missing source or end"})
            continue
        year, month = int(end[:4]), int(end[5:7])
        fiscal_year, q = (year + 1, 1) if month in (10, 11) else (year, 2 if month in (1, 2) else 3 if month in (4, 5) else 4)
        result = extract(path)
        out.append({"old_id": period["period_id"], "period_id": f"FY{fiscal_year}Q{q}", "end": end,
                    "url": sources[sid]["url"], "product": result["product"], "geography": result["geography"],
                    "product_ytd": result["product_ytd"] if q == 3 else None,
                    "geography_ytd": result["geography_ytd"] if q == 3 else None})
        print(out[-1]["period_id"], "product", result["product"][0] if result["product"] else None,
              "geography", result["geography"][0] if result["geography"] else None)
    first_url = "https://www.sec.gov/Archives/edgar/data/858877/000085887720000015/csco-20201024.htm"
    first = extract(CACHE / "FY2021Q1.html")
    out.insert(0, {"old_id": None, "period_id": "FY2021Q1", "end": "2020-10-24", "url": first_url,
                   "product": first["product"], "geography": first["geography"]})
    check = BASE / "checks/segment-extraction.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("total", len(out), "products", sum(bool(x.get("product")) for x in out), "geography", sum(bool(x.get("geography")) for x in out))


if __name__ == "__main__":
    main()
