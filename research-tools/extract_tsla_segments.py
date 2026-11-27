"""Read Tesla's official automotive and energy segment gross profit history."""
import io
import json
import re
from pathlib import Path

import pandas as pd

from extract_amat_segments import cells

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache" / "tier2" / "TSLA"


def numeric(row):
    raw = " ".join(cells(row)[1:]).replace("$", "").replace(",", "")
    return [(-int(x[1:-1].replace(" ", "")) if x.startswith("(") else int(x)) for x in re.findall(r"\(\s*\d+\s*\)|\b\d+\b", raw)]


def segment_table(table, basis):
    lines = table.astype(str).values.tolist()
    title = " ".join(" ".join(cells(row)) for row in lines).lower()
    if "automotive segment" not in title or "energy generation and storage segment" not in title or "gross profit" not in title:
        return None
    if basis == "annual" and "year ended december" not in title:
        return None
    if basis in ("quarter", "ytd") and "three months ended" not in title.replace("\xa0", " "):
        return None
    if basis == "ytd" and "nine months ended" not in title:
        return None
    result, segment = {}, None
    for row in lines:
        values = cells(row)
        if not values:
            continue
        label = values[0].lower()
        if label == "automotive segment":
            segment = "Automotive segment"
            result[segment] = {}
        elif label == "energy generation and storage segment":
            segment = "Energy generation and storage segment"
            result[segment] = {}
        elif segment and label in ("revenues", "gross profit"):
            ns = numeric(row)
            idx = 2 if basis == "ytd" else 0
            if len(ns) > idx:
                result[segment]["revenue" if label == "revenues" else "gross_profit"] = ns[idx]
    if len(result) == 2 and all(set(v) == {"revenue", "gross_profit"} for v in result.values()):
        return result
    return None


def parse(period, basis="quarter"):
    path = CACHE / f"official_{period}.html"
    for i, table in enumerate(pd.read_html(io.BytesIO(path.read_bytes()))):
        result = segment_table(table, basis)
        if result:
            return {"table": i, "data": result}
    raise ValueError(f"{period} {basis}: segment table missing")


def product_table(table, basis):
    title = " ".join(" ".join(cells(row)) for row in table.astype(str).values.tolist()).lower()
    if "automotive" not in title or "services and other" not in title or "total revenues" not in title:
        return None
    if basis == "annual" and "year ended december" not in title:
        return None
    if basis in ("quarter", "ytd") and "three months ended" not in title.replace("\xa0", " "):
        return None
    if basis == "ytd" and "nine months ended" not in title:
        return None
    result = {}
    for row in table.astype(str).values.tolist():
        values = cells(row)
        if not values:
            continue
        label = values[0].lower().replace("  ", " ")
        ns = numeric(row)
        idx = 2 if basis == "ytd" else 0
        if not ns or len(ns) <= idx:
            continue
        value = ns[idx]
        if label in ("automotive sales", "automotive sales without resale value guarantee", "automotive sales with resale value guarantee"):
            result["Automotive sales"] = result.get("Automotive sales", 0) + value
        elif label == "automotive regulatory credits":
            result["Automotive regulatory credits"] = value
        elif label == "automotive leasing":
            result["Automotive leasing"] = value
        elif label == "services and other":
            result["Services and other"] = value
        elif label in ("energy generation and storage", "energy generation and storage segment revenue"):
            result["Energy generation and storage"] = value
        elif label in ("energy generation and storage sales", "energy generation and storage leasing"):
            result["Energy generation and storage"] = result.get("Energy generation and storage", 0) + value
        elif label == "total revenues":
            result["Total"] = value
            break
    required = {"Automotive sales", "Automotive regulatory credits", "Automotive leasing", "Services and other", "Energy generation and storage", "Total"}
    if required <= result.keys() and sum(v for k, v in result.items() if k != "Total") == result["Total"]:
        return result
    return None


def parse_products(period, basis="quarter"):
    path = CACHE / f"official_{period}.html"
    for i, table in enumerate(pd.read_html(io.BytesIO(path.read_bytes()))):
        result = product_table(table, basis)
        if result:
            return {"table": i, "data": result}
    raise ValueError(f"{period} {basis}: product revenue table missing")


def build():
    result = {}
    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if year == 2026 and quarter == 4:
                continue
            period = f"{year}Q{quarter}"
            if quarter < 4:
                result[period] = parse(period)
            else:
                annual, ytd = parse(period, "annual"), parse(f"{year}Q3", "ytd")
                data = {name: {metric: value - ytd["data"][name][metric] for metric, value in metrics.items()} for name, metrics in annual["data"].items()}
                result[period] = {"table": annual["table"], "data": data, "method": "annual_minus_nine_months",
                                  "input_tables": [f"{period}:table {annual['table']}", f"{year}Q3:table {ytd['table']}"]}
            if quarter < 4:
                product = parse_products(period)
            else:
                annual_product, ytd_product = parse_products(period, "annual"), parse_products(f"{year}Q3", "ytd")
                product = {"table": annual_product["table"], "method": "annual_minus_nine_months",
                           "data": {name: value - ytd_product["data"][name] for name, value in annual_product["data"].items()},
                           "input_tables": [f"{period}:table {annual_product['table']}", f"{year}Q3:table {ytd_product['table']}"]}
            result[period]["products"] = product
            if product["data"]["Total"] != sum(x["revenue"] for x in result[period]["data"].values()):
                raise ValueError(f"{period}: product/segment revenue discrepancy")
            print(period, result[period]["data"])
    path = ROOT / "database" / "TSLA" / "html-research" / "checks" / "segment-extraction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
