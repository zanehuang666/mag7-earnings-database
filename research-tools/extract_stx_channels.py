"""Audit Seagate's disclosed sales-channel revenue and storage operating metrics."""
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/STX/html-research"
CACHE = ROOT / ".research-cache/tier2/STX"
EXTRA = {
    "2020-10-02": ("extra_stx-20201002.htm", "https://www.sec.gov/Archives/edgar/data/1137789/000113778920000117/stx-20201002.htm"),
    "2021-12-31": ("extra_stx-20211231.htm", "https://www.sec.gov/Archives/edgar/data/1137789/000113778922000014/stx-20211231.htm"),
    "2022-09-30": ("extra_stx-20220930.htm", "https://www.sec.gov/Archives/edgar/data/1137789/000113778922000123/stx-20220930.htm"),
}


def number(row, start=0):
    vals = []
    for cell in row[start:]:
        s = str(cell).strip().replace(",", "").replace("$", "")
        if s and s != "nan" and (not vals or vals[-1] != s):
            vals.append(s)
    for s in vals[1 if start == 0 else 0:]:
        if re.fullmatch(r"\(?-?\d+(?:\.\d+)?\)?", s):
            return float(s[1:-1])*-1 if s.startswith("(") else float(s)
    return None


def channel(table, ytd=False):
    rows = table.astype(str).values.tolist()
    text = table.to_string().lower()
    if "revenues by channel" not in text or "distributors" not in text or "retailers" not in text:
        return None
    if "revenues by channel (%)" in text:
        return None
    start = 0
    if ytd:
        cols = [i for row in rows[:5] for i, x in enumerate(row) if "Nine Months Ended" in x]
        if not cols:
            return None
        start = min(cols)
    values = {}
    for row in rows:
        name = str(row[0]).strip()
        if name in ("Original equipment manufacturers", "OEMs", "Distributors", "Retailers"):
            key = "OEMs" if name in ("Original equipment manufacturers", "OEMs") else name
            values[key] = number(row, start)
    return values if len(values) == 3 and all(v is not None for v in values.values()) else None


def operating(table):
    rows = table.astype(str).values.tolist()
    text = table.to_string().lower()
    if "hdd exabytes shipped" not in text or "revenues by market (%)" not in text:
        return None
    section = None
    values = {"market_share_percent": {}, "hdd_exabytes": {}}
    for row in rows:
        name = str(row[0]).strip()
        low = name.lower()
        if low.startswith("revenues by market (%)"):
            section = "market_share_percent"
        elif low.startswith("hdd exabytes shipped"):
            section = "hdd_exabytes"
        elif low.startswith("hdd price per terabyte"):
            values["hdd_price_per_tb"] = number(row)
            section = None
        elif section and name in ("Mass capacity", "Legacy", "Other", "Data Center", "Edge IoT", "Nearline", "Non-nearline", "Total"):
            v = number(row)
            if v is not None:
                values[section][name] = v
    return values if values["hdd_exabytes"] else None


def extract(path):
    tables = pd.read_html(io.BytesIO(path.read_bytes()))
    out = {"channel": [], "channel_ytd": [], "operating": []}
    for idx, table in enumerate(tables):
        for key in out:
            val = operating(table) if key == "operating" else channel(table, key == "channel_ytd")
            if val:
                out[key].append([idx, val])
    return {key: vals[0] if vals else None for key, vals in out.items()}


def fiscal(end):
    y, m = int(end[:4]), int(end[5:7])
    return f"FY{y+1 if m in (9,10,12) else y}Q{1 if m in (9,10) else 2 if m in (12,1) else 3 if m in (3,4) else 4}"


def main():
    periods = json.loads((BASE / "data/periods.json").read_text(encoding="utf-8"))["records"]
    sources = {x["source_id"]: x for x in json.loads((BASE / "data/sources.json").read_text(encoding="utf-8"))["records"]}
    jobs = [{"end": end, "path": CACHE/name, "url": url, "old_id": None} for end,(name,url) in EXTRA.items()]
    for p in periods:
        sid = f"official_{p['period_id']}"
        if p.get("quarter_end") and sid in sources:
            jobs.append({"end": p["quarter_end"], "path": CACHE/f"{sid}.html", "url": sources[sid]["url"], "old_id": p["period_id"]})
    jobs.sort(key=lambda x: x["end"])
    out = []
    for job in jobs:
        result = extract(job["path"])
        pid = fiscal(job["end"])
        out.append({"period_id": pid, "end": job["end"], "url": job["url"], "old_id": job["old_id"], **result})
        print(pid, "channel", bool(result["channel"]), "ytd", bool(result["channel_ytd"]),
              "operating", bool(result["operating"]))
    check = BASE / "checks/channel-extraction.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("total", len(out), "channel", sum(bool(x["channel"]) for x in out))


if __name__ == "__main__":
    main()
