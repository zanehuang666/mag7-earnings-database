"""Audit WDC segment and end-market disclosures across its Flash separation."""
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/WDC/html-research"
CACHE = ROOT / ".research-cache/tier2/WDC"
SEGMENTS = {"HDD", "Flash", "Flash-based"}
MARKETS = {"Client Devices", "Data Center Devices & Solutions", "Client Solutions", "Cloud", "Client", "Consumer"}
EXTRA = {
    "2020-10-02": ("extra_wdc-20201002.htm", "https://www.sec.gov/Archives/edgar/data/106040/000010604020000061/wdc-20201002.htm"),
    "2021-12-31": ("extra_wdc-20211231.htm", "https://www.sec.gov/Archives/edgar/data/106040/000010604022000018/wdc-20211231.htm"),
    "2022-09-30": ("extra_wdc-20220930.htm", "https://www.sec.gov/Archives/edgar/data/106040/000010604022000065/wdc-20220930.htm"),
}


def numeric(row, start=0):
    vals = []
    for cell in row[start:]:
        x = str(cell).strip().replace(",", "").replace("$", "")
        if x and x != "nan" and (not vals or vals[-1] != x):
            vals.append(x)
    for x in vals[1 if start == 0 else 0:]:
        if re.fullmatch(r"\(?-?\d+\)?", x):
            return -int(x[1:-1]) if x.startswith("(") else int(x)
    return None


def parse_table(table, kind, ytd=False):
    rows = table.astype(str).values.tolist()
    text = table.to_string().lower()
    if kind == "segment" and not (("hdd" in text and "flash" in text) and ("revenue" in text or "sales" in text)):
        return None
    if kind == "market" and not ("cloud" in text and "client" in text and "consumer" in text) and not ("client devices" in text and "client solutions" in text):
        return None
    start = 0
    if ytd:
        cols = [i for row in rows[:5] for i, x in enumerate(row) if "Nine Months Ended" in x]
        if not cols:
            return None
        start = min(cols)
    section = "revenue"
    revenue, profit = {}, {}
    for row in rows:
        name = str(row[0]).strip()
        low = name.lower()
        if low.startswith("gross profit") or low.startswith("segment gross profit"):
            section = "gross_profit"
        elif low.startswith("gross margin"):
            section = "margin"
        elif low.startswith("revenue by end market") or low.startswith("net revenue by end market"):
            section = "revenue"
        elif kind == "segment" and "hard disk drives" in low:
            val = numeric(row, start)
            if val is not None and section == "revenue":
                revenue["HDD"] = val
        elif name in (SEGMENTS if kind == "segment" else MARKETS):
            val = numeric(row, start)
            if val is not None:
                target = revenue if section == "revenue" else profit if section == "gross_profit" else None
                if target is not None:
                    target[name] = val
    if kind == "segment" and len(revenue) < 2:
        return None
    if kind == "market" and len(revenue) < 3:
        return None
    return {"revenue": revenue, "gross_profit": profit}


def extract(path):
    tables = pd.read_html(io.BytesIO(path.read_bytes()))
    out = {k: [] for k in ("segment", "market", "segment_ytd", "market_ytd")}
    for i, table in enumerate(tables):
        for kind in out:
            result = parse_table(table, kind.removesuffix("_ytd"), kind.endswith("_ytd"))
            if result:
                out[kind].append([i, result])
    return {k: v[0] if v else None for k, v in out.items()}


def fiscal(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"FY{y+1 if m in (9,10,12) else y}Q{1 if m in (9,10) else 2 if m in (12,1) else 3 if m in (3,4) else 4}"


def main():
    periods = json.loads((BASE / "data/periods.json").read_text(encoding="utf-8"))["records"]
    sources = {x["source_id"]: x for x in json.loads((BASE / "data/sources.json").read_text(encoding="utf-8"))["records"]}
    jobs = []
    for end, (name, url) in EXTRA.items():
        jobs.append({"end": end, "path": CACHE / name, "url": url, "old_id": None})
    for p in periods:
        sid = f"official_{p['period_id']}"
        if p.get("quarter_end") and sid in sources:
            jobs.append({"end": p["quarter_end"], "path": CACHE / f"{sid}.html", "url": sources[sid]["url"], "old_id": p["period_id"]})
    jobs.sort(key=lambda x: x["end"])
    out = []
    for job in jobs:
        result = extract(job["path"])
        pid = fiscal(job["end"])
        out.append({"period_id": pid, "end": job["end"], "url": job["url"], "old_id": job["old_id"], **result})
        print(pid, "segment", bool(result["segment"]), "market", bool(result["market"]),
              "profit", bool(result["segment"] and result["segment"][1]["gross_profit"]))
    check = BASE / "checks/segment-extraction.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("total", len(out), "markets", sum(bool(x["market"]) for x in out), "segments", sum(bool(x["segment"]) for x in out))


if __name__ == "__main__":
    main()
