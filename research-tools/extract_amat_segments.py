"""Extract AMAT's reported quarterly segment revenue and operating income.

Reads cached SEC 10-Q/10-K tables.  Q4 equals the annual segment table less the
Q3 filing's nine-month segment table; both inputs remain in the audit output.
"""
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".research-cache" / "tier2" / "AMAT"
NAMES = ("Semiconductor Systems", "Applied Global Services", "Display and Adjacent Markets", "Display", "Corporate and Other", "Other", "Total")


def cells(row):
    values = []
    for raw in row:
        value = str(raw).strip().replace("\xa0", " ")
        if value not in ("", "nan") and (not values or values[-1] != value):
            values.append(value)
    return values


def numbers(row):
    out = []
    for value in cells(row)[1:]:
        value = value.replace(",", "").replace(" ", "")
        if value in ("$", "%"):
            continue
        if value in ("—", "–", "-"):
            out.append(0)
        elif re.fullmatch(r"\(\d+\)", value):
            out.append(-int(value[1:-1]))
        elif re.fullmatch(r"\d+", value):
            out.append(int(value))
    return out


def heading(table):
    return " ".join(" ".join(cells(row)) for row in table.astype(str).values.tolist())


def extract_rows(table, which):
    data = {}
    for row in table.astype(str).values.tolist():
        values = cells(row)
        if values and values[0] in NAMES:
            ns = numbers(row)
            if len(ns) >= 2:
                if which == "ytd":
                    if len(ns) >= 4:
                        data[values[0]] = ns[2:4]
                else:
                    data[values[0]] = ns[:2]
            if values[0] == "Total" and data:
                break
    return data


def extract_group_table(table, which):
    title = next((values for row in table.astype(str).values.tolist() if (values := cells(row))), [])
    if not title or "Semiconductor Systems" not in title or "Applied Global Services" not in title:
        return None
    metrics = {}
    for row in table.astype(str).values.tolist():
        values = cells(row)
        if not values:
            continue
        if values[0] in ("Revenue", "Net revenue", "Net sales"):
            metrics["revenue"] = numbers(row)
        elif values[0] in ("Operating income (loss)", "Operating income"):
            metrics["profit"] = numbers(row)
    if not all(len(v) >= 4 for v in metrics.values()) or len(metrics) != 2:
        return None
    return {name: [metrics["revenue"][i], metrics["profit"][i]] for i, name in enumerate(title[:4])}


def read_file(period):
    path = CACHE / f"official_{period}.html"
    return pd.read_html(io.BytesIO(path.read_bytes()))


def parse(period, which="quarter"):
    tables = read_file(period)
    for i, table in enumerate(tables):
        title = heading(table)
        if "Semiconductor Systems" not in title or "Applied Global Services" not in title:
            continue
        if which == "quarter" and "Three Months Ended" not in title:
            continue
        if which == "ytd" and "Nine Months Ended" not in title:
            continue
        if which == "annual" and "Three Months Ended" in title:
            continue
        if not ("Operating Income" in title or "Operating income" in title):
            continue
        if not ("Net Sales" in title or "Net Revenue" in title or "Net revenue" in title or "Revenue" in title):
            continue
        if which in ("quarter", "annual"):
            group = extract_group_table(table, which)
            if group:
                return {"table": i, "data": group, "method": "horizontal"}
        rows = extract_rows(table, which)
        if "Total" in rows and "Semiconductor Systems" in rows and "Applied Global Services" in rows:
            return {"table": i, "data": rows, "method": "segment_rows"}
    raise ValueError(f"{period} {which}: segment revenue/profit table not located")


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
                keys = set(annual["data"]) & set(ytd["data"])
                data = {key: [annual["data"][key][j] - ytd["data"][key][j] for j in (0, 1)] for key in keys}
                if "Display" in annual["data"] and "Display and Adjacent Markets" in ytd["data"]:
                    data["Display"] = [annual["data"]["Display"][j] - ytd["data"]["Display and Adjacent Markets"][j] for j in (0, 1)]
                if "Corporate and Other" in annual["data"] and "Display" not in annual["data"] and "Display and Adjacent Markets" not in annual["data"]:
                    display = "Display" if "Display" in ytd["data"] else "Display and Adjacent Markets"
                    data["Other"] = [annual["data"]["Corporate and Other"][j] - ytd["data"]["Corporate and Other"][j] - ytd["data"][display][j] for j in (0, 1)]
                    data.pop("Corporate and Other", None)
                result[period] = {"table": annual["table"], "data": data, "method": "annual_minus_nine_months", "input_tables": [f"{period}:table {annual['table']}", f"{year}Q3:table {ytd['table']}"]}
            data = result[period]["data"]
            for index, metric in enumerate(("revenue", "operating_profit")):
                actual = data["Total"][index]
                calculated = sum(value[index] for key, value in data.items() if key != "Total")
                if actual != calculated:
                    raise ValueError(f"{period} {metric}: segments sum {calculated}, total {actual}")
    path = ROOT / "database" / "AMAT" / "html-research" / "checks" / "segment-extraction.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for period, item in result.items():
        print(period, item["method"], item["data"].get("Total"), list(item["data"]))


if __name__ == "__main__":
    build()
