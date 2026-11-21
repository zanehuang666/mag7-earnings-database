"""Build source-limited 11-chart HTML drafts from issuer/SEC quarter packets.

Only the consolidated financial series present in primary sources are plotted.
Business splits, quantity/price, and guidance remain visibly unresearched.
Existing company HTML and authored data are never overwritten by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "research-tools" / "report-renderer" / "scripts"
TARGETS = {"CRWV": "CoreWeave", "ASML": "ASML", "SNDK": "SanDisk", "WDC": "Western Digital",
           "STX": "Seagate", "AMAT": "Applied Materials", "CSCO": "Cisco", "LRCX": "Lam Research"}
LABELS = {"Revenue": "consolidated_revenue", "Operating income": "consolidated_operating_profit",
          "Operating cash flow": "ocf"}


def save_json(path, rows, ticker):
    path.write_text(json.dumps({"schema_version": "diagnostic-official-v1", "company_id": ticker.lower(),
                                "updated_at": date.today().isoformat(), "records": rows},
                               ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def source_from_md(path):
    text = path.read_text(encoding="utf-8")
    url = re.search(r"\[SEC 原件\]\((https?://[^)]+)\)", text)
    end = re.search(r"报告期末：(\d{4}-\d{2}-\d{2})", text)
    filing = re.search(r"申报日期：(\d{4}-\d{2}-\d{2})", text)
    facts = re.findall(r"^- (Revenue|Operating income|Operating cash flow): USD ([\d,]+) \((quarter|full fiscal year[^;]*)[^\n]*", text, re.M)
    return {"url": url.group(1) if url else None, "end": end.group(1) if end else None,
            "published": filing.group(1) if filing else None, "facts": facts}


def source_from_packet(path):
    x = json.loads(path.read_text(encoding="utf-8"))
    facts = re.findall(r"(Revenue|Operating income|Operating cash flow): USD ([\d,]+) \((quarter|full fiscal year[^;]*)", "\n".join(x.get("facts", [])))
    return {"url": (x.get("sources") or [None])[0], "end": None,
            "published": (x.get("cutoff") or "")[:10], "facts": facts,
            "text_facts": x.get("facts", [])}


def quarter_number(name):
    match = re.fullmatch(r"(20\d\d)Q([1-4])", name)
    return (int(match.group(1)), int(match.group(2))) if match else None


def collect(ticker):
    base = ROOT / "database" / ticker
    rows = {}
    for path in sorted((base / "html-research" / "materials" / "official-filings").glob("20*Q*.md")):
        if quarter_number(path.stem):
            rows[path.stem] = source_from_md(path)
    for path in sorted((base / "earnings").glob("20*Q*/materials/analysis.json")):
        q = path.parents[1].name
        if quarter_number(q):
            rows[q] = source_from_packet(path)
            event = path.parents[1] / "event.json"
            if event.exists():
                rows[q]["end"] = json.loads(event.read_text(encoding="utf-8")).get("period_end")
    return {q: value for q, value in rows.items() if value.get("url")}


def build(ticker, company, candidate=False):
    folder = ROOT / "database" / ticker / "html-research"
    output = folder / "output" / ("auto-update-candidate.html" if candidate else "overview.html")
    data = folder / ("auto-data" if candidate else "data")
    view_file = data / "report-view.json"
    old_view = json.loads(view_file.read_text(encoding="utf-8")) if view_file.exists() else {}
    own_draft = old_view.get("auto_generated_from_official_packets") or (
        (data / "facts.json").exists() and
        json.loads((data / "facts.json").read_text(encoding="utf-8")).get("schema_version") == "diagnostic-official-v1")
    if (output.exists() or (data / "facts.json").exists()) and not own_draft:
        return ticker, "authored HTML/data preserved"
    if own_draft and old_view.get("output_sha256") and output.exists():
        current_hash = hashlib.sha256(output.read_bytes()).hexdigest()
        if current_hash != old_view["output_sha256"]:
            return ticker, "manual HTML edit preserved"
    materials = collect(ticker)
    if not materials:
        return ticker, "no official packet"
    fingerprint = hashlib.sha256(json.dumps(materials, sort_keys=True, ensure_ascii=False).encode("utf-8"))
    for component in (SKILL / "render_html.py", SKILL.parent / "assets" / "report-runtime.js"):
        fingerprint.update(component.read_bytes())
    source_digest = fingerprint.hexdigest()
    if own_draft and old_view.get("source_digest") == source_digest and output.exists():
        return ticker, "official sources unchanged"
    first = min(quarter_number(q) for q in materials)
    last = max(quarter_number(q) for q in materials)
    periods, sources, facts = [], [], []
    year, quarter = first
    while (year, quarter) <= last:
        q = f"{year}Q{quarter}"
        packet = materials.get(q)
        sid = f"official_{q}"
        if packet:
            sources.append({"source_id": sid, "publisher": company,
                            "document_type": "issuer release or SEC filing", "title": f"{company} {q} official source",
                            "url": packet["url"], "published_at": packet.get("published"),
                            "is_company_official": True})
        periods.append({"period_id": q, "fiscal_year": year, "fiscal_quarter": quarter,
                        "fiscal_label": q + "（日历归档）", "quarter_end": packet.get("end") if packet else None,
                        "status": "reported" if packet else "not_researched",
                        "comparability_events": ["以报告期末所在日历季度归档；不等于公司财年季度。"]})
        if packet:
            for label, raw, basis in packet["facts"]:
                if basis != "quarter" or label not in LABELS:
                    continue
                metric = LABELS[label]
                facts.append({"fact_id": f"{q}:{metric}:group", "period_id": q,
                              "period_type": "quarter", "metric_id": metric,
                              "original_metric_name": label, "entity_id": "group", "parent_entity_id": "group",
                              "entity_level": "group", "value": int(raw.replace(",", "")) / 1_000_000,
                              "value_status": "reported", "unit_original": "USD millions", "currency": "USD",
                              "scale_original": "million", "display_scale": "亿美元", "gaap_basis": "US GAAP",
                              "accounting_scope": "consolidated", "definition_version": "SEC-2026",
                              "source_id": sid, "locator": f"SEC XBRL {label}; source packet {q}"})
            # A small number of non-US primary releases have explicitly stated
            # quarterly sales in EUR billions. Preserve currency without conversion.
            if ticker == "ASML":
                for item in packet.get("text_facts", []):
                    match = re.search(r"ASML Q[1-4] 20\d\d (?:total net )?sales EUR ([\d.]+) billion", item)
                    if match:
                        facts.append({"fact_id": f"{q}:consolidated_revenue:group", "period_id": q,
                                      "period_type": "quarter", "metric_id": "consolidated_revenue",
                                      "original_metric_name": "total net sales", "entity_id": "group",
                                      "parent_entity_id": "group", "entity_level": "group",
                                      "value": float(match.group(1)) * 1000, "value_status": "reported",
                                      "unit_original": "EUR millions", "currency": "EUR", "scale_original": "million",
                                      "display_scale": "亿欧元", "gaap_basis": "US GAAP",
                                      "accounting_scope": "consolidated", "definition_version": "ASML release",
                                      "source_id": sid, "locator": f"{q} official press release headline"})
                        break
        quarter += 1
        if quarter == 5:
            year, quarter = year + 1, 1
    if not any(f["metric_id"] == "consolidated_revenue" for f in facts):
        return ticker, "no sourced quarterly revenue"
    data.mkdir(parents=True, exist_ok=True)
    for kind, items in (("periods", periods), ("sources", sources), ("facts", facts),
                        ("classification", []), ("guidance", [])):
        save_json(data / f"{kind}.json", items, ticker)
    is_eur = ticker == "ASML"
    view = {
        "research_status": "diagnostic", "company_name": company,
        "auto_generated_from_official_packets": True, "source_digest": source_digest,
        "currency": "EUR" if is_eur else "USD", "display_unit": "亿欧元" if is_eur else "亿美元",
        "display_divisor": 100, "return_href": "../../../../calendar.html",
        "traditional_intro": "仅展示已定位官方申报文件的集团季度指标；业务分部、产品层级仍待逐季研究。",
        "ai_intro": "AI 相关业务及量价尚未逐季核实，相关图卡留空。",
        "chart_context_notes": {"g1": "诊断草稿：横轴按报告期末所在日历季度归档，非公司财年季度；10-K 全年值未当作 Q4。",
                                "g5": "分部与产品分类待核，不能从集团收入推断 AI 收入。",
                                "g8": "现金流仅使用可确认的季度值；年度或年初至今累计值不填入单季。",
                                "g10": "管理层 CapEx 指引修订尚未逐次核实。",
                                "g11": "自由现金流缺少完整资本开支证据时不计算。"}
    }
    view_file.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sys.path.insert(0, str(SKILL))
    from build_report import build as build_report
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".candidate.html")
    result = build_report(data, temporary)
    from verify_report import verify
    check = verify(temporary)
    if not check["ok"]:
        raise ValueError("static HTML verification failed: " + "; ".join(check["errors"]))
    temporary.replace(output)
    view["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
    view_file.write_text(json.dumps(view, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return ticker, f"{result['quarters']} quarters; {len(facts)} sourced facts"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ticker", choices=sorted(TARGETS))
    args = parser.parse_args()
    for ticker in ([args.ticker] if args.ticker else TARGETS):
        try:
            print(build(ticker, TARGETS[ticker]), flush=True)
            if ticker == "SNDK":
                print(build(ticker, TARGETS[ticker], candidate=True), flush=True)
        except Exception as exc:
            print(ticker, "ERROR", str(exc)[:500], flush=True)
            raise


if __name__ == "__main__":
    main()
