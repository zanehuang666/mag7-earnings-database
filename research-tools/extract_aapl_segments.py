"""Extract Apple's fiscal-quarter product and geographic-segment results."""
import io
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd

from extract_amat_segments import cells
from extract_tsla_segments import numeric

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache" / "tier2" / "AAPL"
DATA = ROOT / "database" / "AAPL" / "html-research" / "data"
PRODUCTS = ("iPhone", "Mac", "iPad", "Wearables, Home and Accessories", "Services")
REGIONS = ("Americas", "Europe", "Greater China", "Japan", "Rest of Asia Pacific", "Corporate", "Total")


def source_map():
    sources = {x["source_id"]: x for x in json.loads((DATA / "sources.json").read_text(encoding="utf-8"))["records"]}
    periods = json.loads((DATA / "periods.json").read_text(encoding="utf-8"))["records"]
    out = {
        "FY2021Q1": {"path": CACHE / "FY2021Q1.html", "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019321000010/aapl-20201226.htm", "end": "2020-12-26", "published": "2021-01-28"},
        "FY2023Q4": {"path": CACHE / "FY2023Q4.html", "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019323000106/aapl-20230930.htm", "end": "2023-09-30", "published": "2023-11-02"},
        "FY2026Q4": {"path": CACHE / "FY2026Q4.html", "url": "https://www.sec.gov/Archives/edgar/data/320193/000032019326000026/aapl-20260926.htm", "end": "2026-09-26", "published": "2026-11-03"},
    }
    for p in periods:
        end = p.get("quarter_end")
        source = sources.get(f"official_{p['period_id']}")
        if not end or not source or "sec.gov" not in source["url"]:
            continue
        y, month, _ = map(int, end.split("-"))
        fy, fq = (y + 1, 1) if month == 12 else (y, 2) if month in (3, 4) else (y, 3) if month in (6, 7) else (y, 4)
        key = f"FY{fy}Q{fq}"
        if key in out:
            continue
        out[key] = {"path": CACHE / f"official_{p['period_id']}.html", "url": source["url"], "end": end, "published": source.get("published_at")}
    expected = {f"FY{year}Q{quarter}" for year in range(2021, 2027) for quarter in range(1, 5)}
    if set(out) != expected:
        raise ValueError(f"Apple fiscal source gap: {sorted(expected - set(out))}; extras {sorted(set(out) - expected)}")
    return out


def label(value):
    return re.sub(r"\s*\(\d+\)", "", value).replace("®", "").replace("™", "").replace("GreaterChina", "Greater China").strip().rstrip(":")


def row_number(row, basis):
    values = numeric(row)
    idx = 2 if basis == "ytd" else 0
    return values[idx] if len(values) > idx else None


def products(table, basis):
    lines = table.astype(str).values.tolist()
    head = " ".join(" ".join(cells(r)) for r in lines).lower()
    if not all(name.lower() in head for name in PRODUCTS) or "total net sales" not in head:
        return None
    if basis == "annual" and ("three months ended" in head or "change" in head):
        return None
    if basis in ("quarter", "ytd") and "three months ended" not in head:
        return None
    if basis == "ytd" and "nine months ended" not in head:
        return None
    out = {}
    for row in lines:
        values = cells(row)
        if not values:
            continue
        name = label(values[0])
        if name in PRODUCTS or name == "Total net sales":
            val = row_number(row, basis)
            if val is not None:
                out["Total" if name == "Total net sales" else name] = val
    if set(PRODUCTS) | {"Total"} <= out.keys() and sum(out[x] for x in PRODUCTS) == out["Total"]:
        return out
    return None


def regions(table, basis):
    lines = table.astype(str).values.tolist()
    head = " ".join(" ".join(cells(r)) for r in lines).lower()
    if "americas" not in head or not ("greater china" in head or "greaterchina" in head) or "operating income" not in head:
        return None
    if basis == "annual" and "three months ended" in head:
        return None
    if basis == "quarter" and "three months ended" not in head:
        return None
    if basis == "ytd" and "nine months ended" not in head:
        return None
    # FY2025 onward: geographic segments are columns.
    header_rows = [i for i, row in enumerate(lines) if {"Americas", "Europe", "Japan", "Total"} <= set(label(v) for v in cells(row))]
    if header_rows:
        start = header_rows[0]
        for row in lines[start + 1:]:
            values = cells(row)
            if values and values[0].lower() == "net sales":
                revenues = numeric(row)
            elif values and values[0].lower().startswith("operating income"):
                profits = numeric(row)
                break
        else:
            return None
        if len(revenues) == 6:
            revenues.insert(5, 0)
        if len(revenues) >= 7 and len(profits) >= 7:
            out = {name: {"revenue": revenues[i], "profit": profits[i]} for i, name in enumerate(REGIONS)}
            return out
    # Earlier filings: each geographic segment is a block of rows.
    out, current = {}, None
    for row in lines:
        values = cells(row)
        if not values:
            continue
        name = label(values[0])
        if name in REGIONS:
            current = name
            out.setdefault(name, {})
        elif current and name.lower() in ("net sales", "operating income", "operating income/(loss)"):
            val = row_number(row, basis)
            if val is not None:
                out[current]["revenue" if name.lower() == "net sales" else "profit"] = val
        if name == "Total" and set(out.get("Total", {})) == {"revenue", "profit"}:
            break
    if len(out) >= 5 and all(set(x) == {"revenue", "profit"} for x in out.values()):
        return out
    return None


def group_operating_income(pid, basis, end):
    fy, fq = int(pid[2:6]), int(pid[-1])
    values = json.loads((ROOT / ".research-cache" / "tier2" / "companyfacts" / "AAPL.json").read_text(encoding="utf-8"))["facts"]["us-gaap"]["OperatingIncomeLoss"]["units"]["USD"]
    fp = "FY" if fq == 4 else f"Q{fq}"
    form = "10-K" if fq == 4 else "10-Q"
    wanted = 365 if basis == "annual" else 275 if basis == "ytd" else 90
    found = [v for v in values if v.get("fy") == fy and v.get("fp") == fp and v.get("form") == form and v.get("end") == end and v.get("start") and abs((date.fromisoformat(end) - date.fromisoformat(v["start"])).days - wanted) < 25]
    if len(found) != 1:
        raise ValueError(f"{pid} {basis}: operating income XBRL count {len(found)}")
    return found[0]["val"] / 1_000_000


def parse(path, basis, pid, end):
    result = {}
    for i, table in enumerate(pd.read_html(io.BytesIO(path.read_bytes()))):
        if "products" not in result:
            found = products(table, basis)
            if found:
                result["products"] = {"table": i, "data": found}
        if "regions" not in result:
            found = regions(table, basis)
            if found:
                result["regions"] = {"table": i, "data": found}
        if len(result) == 2:
            break
    if len(result) != 2:
        raise ValueError(f"{path.name} {basis}: missing {set(('products','regions')) - set(result)}")
    region_rows = result["regions"]["data"]
    operating_total = group_operating_income(pid, basis, end)
    if "Total" not in region_rows:
        region_rows["Total"] = {"revenue": sum(v["revenue"] for v in region_rows.values()), "profit": operating_total}
        region_rows["Corporate"] = {"revenue": 0, "profit": operating_total - sum(v["profit"] for k, v in region_rows.items() if k not in ("Total", "Corporate"))}
    elif region_rows["Total"]["profit"] != operating_total:
        raise ValueError(f"{path.name} {basis}: region operating income != SEC group XBRL")
    product_total = result["products"]["data"]["Total"]
    region_total = result["regions"]["data"]["Total"]["revenue"]
    if product_total != region_total:
        raise ValueError(f"{path.name} {basis}: product {product_total} != region {region_total}")
    return result


def build():
    sources = source_map()
    audit = {}
    for year in range(2021, 2027):
        for quarter in range(1, 5):
            pid = f"FY{year}Q{quarter}"
            item = sources[pid]
            if quarter < 4:
                result = parse(item["path"], "quarter", pid, item["end"])
            else:
                annual = parse(item["path"], "annual", pid, item["end"])
                prior_item = sources[f"FY{year}Q3"]
                ytd = parse(prior_item["path"], "ytd", f"FY{year}Q3", prior_item["end"])
                result = {kind: {"table": annual[kind]["table"], "method": "annual_minus_nine_months",
                                 "input_tables": [f"{pid}:table {annual[kind]['table']}", f"FY{year}Q3:table {ytd[kind]['table']}"]} for kind in ("products", "regions")}
                result["products"]["data"] = {name: value - ytd["products"]["data"][name] for name, value in annual["products"]["data"].items()}
                result["regions"]["data"] = {name: {metric: value - ytd["regions"]["data"][name][metric] for metric, value in values.items()} for name, values in annual["regions"]["data"].items()}
            result["source"] = {k: str(v) for k, v in item.items() if k != "path"}
            group = result["products"]["data"]["Total"]
            region = result["regions"]["data"]
            if group != region["Total"]["revenue"] or sum(v["revenue"] for k, v in region.items() if k != "Total") != group:
                raise ValueError(f"{pid}: revenue reconciliation failed")
            if sum(v["profit"] for k, v in region.items() if k != "Total") != region["Total"]["profit"]:
                raise ValueError(f"{pid}: operating-income reconciliation failed")
            audit[pid] = result
            print(pid,group,region["Total"]["profit"],result["products"]["table"],result["regions"]["table"])
    path = ROOT / "database" / "AAPL" / "html-research" / "checks" / "segment-extraction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
