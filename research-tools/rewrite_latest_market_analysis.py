"""Rewrite only the two latest released Analysis reports per company.

The market evidence file is curated separately. The model receives no Preview.
Existing reports are archived before replacement. Every paid call is ledgered.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EVIDENCE = ROOT / "data/market_evidence_latest.json"
LEDGER = ROOT / "data/generation_budget_2025_2026.json"
CAP_RMB = 20.0  # Additional run allowance; historical spending is tracked separately.
PRICES = {"DeepSeek-V3.2-Exp": (2.0, 3.0), "DeepSeek-V4.1-Flash": (2.0, 8.0)}
MODEL = "DeepSeek-V3.2-Exp"
VERSION = "market-analysis-20261126"
OFFICIAL = {
    "AAPL_2026Q4": "https://www.apple.com/newsroom/2026/11/apple-reports-fourth-quarter-results/",
    "AAPL_2026Q3": "https://www.apple.com/newsroom/2026/07/apple-reports-third-quarter-results/",
    "TSLA_2026Q3": "https://ir.tesla.com/_flysystem/s3/sec/000162828026066738/tsla-20261021-gen.pdf",
    "TSLA_2026Q2": "https://ir.tesla.com/_flysystem/s3/sec/000162828026049213/tsla-20260722-gen.pdf",
}
OFFICIAL_FACTS = {
    "AAPL_2026Q4": ["Apple fiscal 2026 Q4 ended September 26, 2026; released November 2.",
        "Revenue USD 114.5 billion, up 12% year over year; gross margin 47.9%; diluted EPS USD 2.10.",
        "Apple said tariff refunds added about 1 percentage point to gross margin and USD 0.05 to EPS.",
        "Operating cash flow USD 28 billion; Services revenue reached an all-time high."],
    "AAPL_2026Q3": ["Apple fiscal 2026 Q3 ended June 27, 2026; released July 30.",
        "Revenue USD 109.4 billion, up 16% year over year; gross margin 50.1%; diluted EPS USD 2.02.",
        "Apple said tariff refunds added about 2 percentage points to gross margin and USD 0.11 to EPS.",
        "iPhone, Mac and Services set June-quarter revenue records."],
    "TSLA_2026Q3": ["Tesla calendar 2026 Q3 released October 21.",
        "Automotive gross margin excluding regulatory credits was 18.1% (non-GAAP).",
        "Quarterly operating cash flow USD 4.697 billion; quarter-end figures are not trailing-twelve-month figures."],
    "TSLA_2026Q2": ["Tesla calendar 2026 Q2 released July 22.",
        "Revenue USD 28.236 billion, up 26% year over year; GAAP gross margin 16.8%.",
        "Operating cash flow USD 4.697 billion; capital expenditures USD 5.789 billion; free cash flow negative USD 1.092 billion."],
}

SYSTEM = """你是市场财报研究编辑。任务是概括财报发布后市场新闻和具名研究机构的分析，不写个人财报评论。
正文顺序：①主要结论；②核心业务变化及其机制；③这些变化如何改变增长、利润、现金流的预期；④市场如何定价，说明股价反应和具名机构分歧；⑤下一季最重要的业务验证点。每段要形成独立论点。
不要写市场财报前“原先计入了什么”，不要复核 Preview，不要提及 Preview。不要写孤立的免责声明、资料不足声明、口径提醒或防御性补充句。没有证据的内容直接省略。
结论必须归属 Reuters、AP、具名机构或其他给定新闻/机构来源；仅用公司原文核对经营数字与指引。市场报道的理解与本稿推断须区分。只有资料明确支持时才写股价幅度、机构评级或目标价。每个关键事实在附近给直接来源链接。币种、财年和季度要准确，尤其区分日历季度与公司财季。
先在内部按 ASD-STE100 清晰英文写提纲：明确主语、稳定术语、一句一个主要判断。再译写自然中文。最终正文 800—1100 个汉字左右，标题和来源列表不计。避免冗长背景，保留业务→预期变化→定价的因果链。
输出 JSON：english_outline（简短英文提纲）, markdown（中文正文）。不要代码围栏。"""

REVIEW = """你是质疑稿件的第一位读者。仅基于随附来源，提出三个能改变文章理解的具体问题；逐一核对来源，并修订稿件。
修订稿须保留 800—1100 个汉字左右、业务→预期变化→定价的结构。删除为防御而写的补充句。不能引入未见于来源的机构观点、数字、股价或日期。不得提及 Preview。
输出 JSON：reader_questions（恰好三条）, checks（三条对应核查结果）, markdown（修订稿）。不要代码围栏。"""


def load(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_json(content: str):
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return json.loads(text[text.index("{"): text.rindex("}") + 1])


def api(model: str, system: str, user: dict, max_tokens=3300):
    base = os.environ.get("PARATERA_BASE_URL") or "https://llmapi.paratera.com"
    base = base.rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = {"model": model, "temperature": 0.15, "max_tokens": max_tokens,
            "enable_thinking": False,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]}
    req = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode("utf-8"),
        {"Authorization": "Bearer " + os.environ["PARATERA_API_KEY"], "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=200) as response:
        return json.load(response)


def response_content(result):
    return (result.get("choices") or [{}])[0].get("message", {}).get("content", "")


def bill(ledger, result, model, label):
    usage = result.get("usage") or {}
    inp = int(usage.get("prompt_tokens") or 12000)
    out = int(usage.get("completion_tokens") or 3300)
    cost = (inp * PRICES[model][0] + out * PRICES[model][1]) / 1_000_000
    ledger["spent_rmb_estimate"] = round(float(ledger["spent_rmb_estimate"]) + cost, 6)
    ledger.setdefault("calls", []).append({"item": label, "model": model,
        "input_tokens": inp, "output_tokens": out, "cost_rmb": round(cost, 6)})
    save(LEDGER, ledger)
    return cost


def call_with_fallback(ledger, system, payload, label):
    # Reserve a conservative amount before the request so retries cannot overrun the cap.
    if float(ledger["spent_rmb_estimate"]) + 0.07 > float(ledger["run_start_spent_rmb"]) + CAP_RMB:
        raise RuntimeError("BUDGET_STOP")
    model = ledger.get("market_analysis_model", MODEL)
    try:
        result = api(model, system, payload)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:350]
        if model != MODEL or ("No deployments available" not in detail and exc.code != 404):
            raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
        model = "DeepSeek-V4.1-Flash"
        ledger["market_analysis_model"] = model
        result = api(model, system, payload)
    bill(ledger, result, model, label)
    return parse_json(response_content(result))


def build_payload(key, articles):
    ticker, quarter = key.split("_")
    packet_path = ROOT / "database" / ticker / "earnings" / quarter / "materials/analysis.json"
    packet = load(packet_path, {})
    if key in OFFICIAL:
        packet = {"ticker": ticker, "calendar_quarter": quarter,
                  "sources": [OFFICIAL[key]], "facts": OFFICIAL_FACTS[key],
                  "official_release_confirmed": True,
                  "verification_status": "official_release_checked_2026-11-26",
                  "cutoff": "2026-11-26T00:00:00Z"}
        if not packet_path.exists():
            save(packet_path, packet)
    if not packet.get("official_release_confirmed") or not packet.get("sources"):
        raise ValueError("official earnings source absent")
    clean_articles = []
    seen = set()
    for item in articles:
        url = item.get("url", "").split("?")[0]
        if not url or url in seen:
            continue
        seen.add(url)
        clean_articles.append({"title": item.get("title", ""), "url": url,
            "search_excerpt": item.get("snippet", "")[:700],
            "article_excerpt": item.get("article_text", "")[:5500]})
    if not clean_articles or not any(a["article_excerpt"] or a["search_excerpt"] for a in clean_articles):
        raise ValueError("market reporting absent")
    return {"ticker": ticker, "quarter": quarter,
            "official_sources": packet["sources"], "verified_official_facts": packet.get("facts", []),
            "market_reporting": clean_articles, "research_date": "2026-11-26"}


def checks(markdown, payload):
    errors = []
    chars = len(re.findall(r"[\u4e00-\u9fff]", markdown))
    if chars < 700 or chars > 1450:
        errors.append(f"length {chars}")
    if not markdown.lstrip().startswith("# "):
        errors.append("title")
    if len(re.findall(r"^## ", markdown, re.M)) < 3:
        errors.append("structure")
    if not any(url in markdown for url in payload["official_sources"]):
        errors.append("official source citation")
    if not any(a["url"] in markdown for a in payload["market_reporting"]):
        errors.append("market source citation")
    if re.search(r"(?i)preview|前瞻复核|无同期", markdown):
        errors.append("preview language")
    if re.search(r"无法确认|资料不足|不能证明|需要注意的是|值得注意的是|由于缺乏", markdown):
        errors.append("defensive language")
    return errors


def replace_report(key, draft, packet, audit):
    ticker, quarter = key.split("_")
    folder = ROOT / "database" / ticker / "earnings" / quarter / "analysis"
    folder.mkdir(parents=True, exist_ok=True)
    md = folder / "analysis.md"
    meta = folder / "analysis.meta.json"
    old_meta = load(meta, {})
    if old_meta.get("rewrite_version") == VERSION:
        return False
    if md.exists():
        history = folder / "history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix in (".md", ".meta.json", ".checks.json"):
            old = folder / ("analysis" + suffix)
            if old.exists():
                (history / ("analysis-" + stamp + suffix)).write_bytes(old.read_bytes())
    md.write_text(draft.rstrip() + "\n", encoding="utf-8")
    save(meta, {**old_meta, "status": "generated_review_pending",
        "rewrite_version": VERSION, "model": audit["model"],
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": packet["official_sources"] + [a["url"] for a in packet["market_reporting"]],
        "output_sha256": hashlib.sha256(md.read_bytes()).hexdigest()})
    save(folder / "analysis.checks.json", audit)
    return True


def main():
    if not os.environ.get("PARATERA_API_KEY"):
        raise SystemExit("PARATERA_API_KEY missing; no paid calls")
    evidence = load(EVIDENCE, {})
    if len(evidence) != 46:
        raise SystemExit(f"Expected 46 target quarters; got {len(evidence)}")
    ledger = load(LEDGER)
    if ledger is None:
        raise SystemExit("Cost ledger absent")
    ledger.setdefault("run_start_spent_rmb", float(ledger["spent_rmb_estimate"]))
    results = {"updated": [], "failed": {}}
    for key, articles in evidence.items():
        report = ROOT / "database" / key.replace("_", "/earnings/") / "analysis/analysis.meta.json"
        if load(report, {}).get("rewrite_version") == VERSION:
            continue
        try:
            payload = build_payload(key, articles)
            first = call_with_fallback(ledger, SYSTEM, payload, key + "/draft")
            draft = first["markdown"]
            second = call_with_fallback(ledger, REVIEW,
                {"sources": payload, "draft": draft}, key + "/review")
            final = second["markdown"]
            errors = checks(final, payload)
            if len(second.get("reader_questions", [])) != 3:
                errors.append("reader questions")
            if errors:
                # One targeted edit pass is cheaper than accepting an unusable article.
                third = call_with_fallback(ledger, REVIEW,
                    {"sources": payload, "draft": final, "fix_errors": errors}, key + "/repair")
                final = third["markdown"]
                errors = checks(final, payload)
                if errors:
                    raise ValueError("QA: " + ", ".join(errors))
                second = third
            audit = {"version": VERSION, "english_outline": first.get("english_outline", ""),
                "reader_questions": second.get("reader_questions", []),
                "checks": second.get("checks", []),
                "source_urls": payload["official_sources"] + [a["url"] for a in payload["market_reporting"]],
                "model": ledger.get("market_analysis_model", MODEL)}
            replace_report(key, final, payload, audit)
            results["updated"].append(key)
            print(key, "OK", flush=True)
        except (ValueError, KeyError, RuntimeError, urllib.error.URLError, TimeoutError) as exc:
            results["failed"][key] = str(exc)[:180]
            print(key, "FAILED", str(exc)[:180], flush=True)
            if "BUDGET_STOP" in str(exc):
                break
        # Progress survives a workflow interruption.
        save(ROOT / "data/market_analysis_run.json", results)
        time.sleep(0.2)
    print(json.dumps({"updated": len(results["updated"]), "failed": results["failed"],
        "new_cost_rmb": round(float(ledger["spent_rmb_estimate"]) - float(ledger["run_start_spent_rmb"]), 4)},
        ensure_ascii=False), flush=True)
    if results["failed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
