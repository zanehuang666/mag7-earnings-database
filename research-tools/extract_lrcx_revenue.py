"""Audit Lam Research system/service revenue in fiscal quarters, including Q4 inputs."""
import io
import json
import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "database/LRCX/html-research"
CACHE = ROOT / ".research-cache/tier2/LRCX"


def value(row, start=0):
    vals = []
    for raw in row[start:]:
        v = str(raw).strip().replace(",", "").replace("$", "")
        if v and v != "nan" and (not vals or vals[-1] != v):
            vals.append(v)
    for v in vals[1 if start == 0 else 0:]:
        if re.fullmatch(r"\(?-?\d+\)?", v):
            return -int(v[1:-1]) if v.startswith("(") else int(v)
    return None


def parse(path, ytd=False):
    tables = pd.read_html(io.BytesIO(path.read_bytes()))
    found = []
    for idx, table in enumerate(tables):
        rows = table.astype(str).values.tolist()
        text = table.to_string().lower()
        if not ("system revenue" in text or "systems revenue" in text) or "customer support" not in text:
            continue
        head = rows[:5]
        start = 0
        if ytd:
            cols = [i for row in head for i, cell in enumerate(row) if "Nine Months Ended" in cell]
            if not cols:
                continue
            start = min(cols)
        revenue = {}
        for row in rows:
            label = str(row[0]).lower()
            if label.startswith(("system revenue", "systems revenue")):
                revenue["systems"] = value(row, start)
            elif label.startswith("customer support"):
                revenue["support"] = value(row, start)
        if len(revenue) == 2 and all(isinstance(v, int) for v in revenue.values()):
            found.append((idx, revenue))
    return found[0] if found else None


def main():
    periods = json.loads((BASE / "data/periods.json").read_text(encoding="utf-8"))["records"]
    sources = {s["source_id"]: s for s in json.loads((BASE / "data/sources.json").read_text(encoding="utf-8"))["records"]}
    out = []
    extra = [("FY2021Q1", "2020-09-27", "https://www.sec.gov/Archives/edgar/data/707549/000070754920000173/lrcx-20200927.htm"),
             ("FY2021Q2", "2020-12-27", "https://www.sec.gov/Archives/edgar/data/707549/000070754921000017/lrcx-20201227.htm")]
    for pid, end, url in extra:
        path = CACHE / f"{pid}.html"
        out.append({"period_id": pid, "end": end, "url": url, "old_id": None, "revenue": parse(path), "ytd": None})
    for period in periods:
        sid = f"official_{period['period_id']}"
        end = period.get("quarter_end")
        if not end:
            raise ValueError(f"{period['period_id']}: missing period end")
        year, month = int(end[:4]), int(end[5:7])
        fy, q = (year + 1, 1) if month == 9 else (year + 1, 2) if month == 12 else (year, 3) if month == 3 else (year, 4)
        pid = f"FY{fy}Q{q}"
        path = CACHE / f"{sid}.html"
        out.append({"period_id": pid, "end": end, "url": sources[sid]["url"], "old_id": period["period_id"],
                    "revenue": parse(path), "ytd": parse(path, True) if q == 3 else None})
    out.sort(key=lambda x: x["period_id"])
    check = BASE / "checks/revenue-extraction.json"
    check.parent.mkdir(parents=True, exist_ok=True)
    check.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for x in out:
        print(x["period_id"], x["revenue"], "ytd", bool(x["ytd"]))
    print("total", len(out), "revenue", sum(bool(x["revenue"]) for x in out))


if __name__ == "__main__":
    main()
