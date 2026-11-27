"""Extract Broadcom segment revenue/profit and group adjustment from SEC filings."""
import io
import json
from pathlib import Path

import pandas as pd

from extract_amat_segments import cells, numbers

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache" / "tier2" / "AVGO"
SEGMENTS = ("Semiconductor solutions", "Infrastructure software", "Total")


def file_for(period):
    kind = "sec" if period.startswith("2026") else "official"
    return CACHE / f"{kind}_{period}.html"


def table_values(table, basis):
    data = {name: {} for name in SEGMENTS}
    mode = None
    block = None
    for row in table.astype(str).values.tolist():
        values = cells(row)
        if not values:
            continue
        label = values[0]
        lower = label.lower()
        if lower == "net revenue:":
            mode = "revenue"
        elif lower == "operating income:":
            mode = "profit"
        elif lower in ("semiconductor solutions:", "infrastructure software:", "total:"):
            block = label[:-1].capitalize() if lower != "total:" else "Total"
            if block == "Infrastructure software":
                block = "Infrastructure software"
            if block == "Semiconductor solutions":
                block = "Semiconductor solutions"
        ns = numbers(row)
        idx = 2 if basis == "ytd" else 0
        if len(ns) <= idx:
            continue
        if block and lower in ("net revenue", "operating income"):
            data[block]["revenue" if lower == "net revenue" else "profit"] = ns[idx]
        elif mode and lower in ("semiconductor solutions", "infrastructure software", "total net revenue", "total operating income", "unallocated expenses"):
            name = "Total" if lower.startswith("total") else label.capitalize()
            if name == "Infrastructure software":
                name = "Infrastructure software"
            if name == "Semiconductor solutions":
                name = "Semiconductor solutions"
            if name in data:
                data[name][mode] = ns[idx]
    if all(set(data[n]) == {"revenue", "profit"} for n in SEGMENTS):
        data["Unallocated expenses"] = {"profit": data["Total"]["profit"] - data["Semiconductor solutions"]["profit"] - data["Infrastructure software"]["profit"]}
        if data["Semiconductor solutions"]["revenue"] + data["Infrastructure software"]["revenue"] != data["Total"]["revenue"]:
            raise ValueError("segment revenue not additive")
        return data
    return None


def parse(period, basis="quarter"):
    tables = pd.read_html(io.BytesIO(file_for(period).read_bytes()))
    for i, table in enumerate(tables):
        joined = " ".join(" ".join(cells(r)) for r in table.astype(str).values.tolist()).lower()
        if "semiconductor solutions" not in joined or "infrastructure software" not in joined or "operating income" not in joined:
            continue
        if basis == "annual" and "fiscal year" not in joined:
            continue
        if basis in ("quarter", "ytd") and "fiscal quarter" not in joined:
            continue
        if basis == "ytd" and "three fiscal quarters ended" not in joined:
            continue
        data = table_values(table, basis)
        if data:
            return {"table": i, "data": data}
    raise ValueError(f"{period} {basis}: segment table missing")


def build():
    result = {}
    for year in range(2021, 2027):
        for quarter in range(1, 5):
            if year == 2026 and quarter == 4:
                continue
            period = f"{year}Q{quarter}"
            if quarter != 4:
                result[period] = parse(period)
            else:
                annual, ytd = parse(period, "annual"), parse(f"{year}Q3", "ytd")
                data = {name: {kind: annual["data"][name][kind] - ytd["data"][name][kind] for kind in annual["data"][name]} for name in annual["data"]}
                result[period] = {"table": annual["table"], "method": "annual_minus_three_fiscal_quarters", "data": data,
                                  "input_tables": [f"{period}:table {annual['table']}", f"{year}Q3:table {ytd['table']}"]}
            print(period, result[period]["data"]["Total"], result[period]["data"]["Unallocated expenses"])
    path = ROOT / "database" / "AVGO" / "html-research" / "checks" / "segment-extraction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    build()
