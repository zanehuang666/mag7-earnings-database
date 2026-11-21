"""Static verification for a generated offline report; browser QA remains separate."""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

from bs4 import BeautifulSoup


def verify(path):
    raw = path.read_text(encoding="utf-8")
    soup = BeautifulSoup(raw, "html.parser")
    errors = []
    for i in range(1, 12):
        node = soup.find(id=f"g{i}")
        if node is None or node.get("data-chart") != f"g{i}":
            errors.append(f"chart g{i} missing")
    for anchor in ("progressTradChart", "progressAiChart", "source", "traditional-income", "ai-income", "cash"):
        if soup.find(id=anchor) is None:
            errors.append(f"{anchor} missing")
    if len(soup.select(".kpis .kpi")) != 6:
        errors.append("six KPI cards required")
    for link in soup.select('nav.side-nav a[href^="#"]'):
        if soup.find(id=link["href"][1:]) is None:
            errors.append(f'broken nav {link["href"]}')
    script = soup.script.string if soup.script else ""
    if not script:
        errors.append("inline script missing")
        model = None
    else:
        check = subprocess.run(["node", "--check", "-"], input=script, text=True, capture_output=True)
        if check.returncode:
            errors.append("script syntax: " + check.stderr[:300])
        match = re.search(r"window\.REPORT_DATA=(.*?);\s*\n", script, flags=re.S)
        if not match:
            errors.append("embedded report data missing")
            model = None
        else:
            try:
                model = json.loads(match.group(1))
            except json.JSONDecodeError as exc:
                errors.append(f"embedded report data invalid: {exc}")
                model = None
    if model:
        quarters = model.get("quarters", [])
        charts = model.get("charts", [])
        if len(charts) != 11:
            errors.append("embedded model must contain 11 charts")
        if len(quarters) != len(set(quarters)) or not quarters:
            errors.append("quarter axis empty or duplicated")
        if model.get("last_quarter") != quarters[-1]:
            errors.append("latest quarter differs from axis")
        if model.get("research_status") == "diagnostic":
            group_chart = next((c for c in charts if c.get("id") == "g1"), None)
            plotted = [i for i in range(len(quarters)) if group_chart and any(isinstance(s.get("values", [None] * len(quarters))[i], (int, float)) for s in group_chart.get("series", []))]
            if len(plotted) != len(quarters):
                errors.append("diagnostic axis contains quarters without plottable group revenue")
            if not group_chart or not plotted:
                errors.append("diagnostic group revenue chart has no visible data")
        for chart in charts:
            for row in chart.get("series", []):
                if len(row.get("values", [])) != len(quarters):
                    errors.append(f'{chart.get("id")}: {row.get("key")} series length mismatch')
                if len(row.get("evidence", [])) != len(quarters):
                    errors.append(f'{chart.get("id")}: {row.get("key")} evidence length mismatch')
        for cid in ("progressTradChart", "progressAiChart"):
            for row in model.get("progress", {}).get(cid, []):
                if len(row.get("values", [])) != len(quarters):
                    errors.append(f"{cid}: progress length mismatch")
        if "虚构" in model.get("company_name", ""):
            pass
        elif any(text in raw for text in ("虚构数据原型", "星河企业软件")):
            errors.append("prototype text leaked into real report")
        for annual in model.get("annual", {}).values():
            for event in annual.get("events", []):
                if event.get("note") == "原话未明确现金口径" and event.get("comparable"):
                    errors.append("wording-unclear CapEx event marked comparable")
    return {"ok": not errors, "errors": errors, "note": "Static structure, embedded model and JS syntax verified; browser interaction and visual regression must be checked separately."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("html")
    parser.add_argument("--report")
    args = parser.parse_args()
    try:
        result = verify(Path(args.html))
    except Exception as exc:
        result = {"ok": False, "errors": [str(exc)]}
    output = json.dumps(result, ensure_ascii=False, indent=2)
    if args.report:
        Path(args.report).write_text(output, encoding="utf-8")
    print(output)
    sys.exit(0 if result["ok"] else 1)
