"""Budget-capped incremental Markdown drafts for both tiers from 2025 onward."""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIRST = {"MSFT", "AMZN", "META", "GOOGL", "ORCL", "NVDA", "AVGO", "AMD", "MU", "INTC", "SKHX", "SMSN"}
SECOND = {"CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML"}
LEDGER = ROOT / "data" / "generation_budget_2025_2026.json"
LIMIT_RMB = 40.0
PRICE = {"DeepSeek-V3.2-Exp": (2.0, 3.0), "DeepSeek-V4.1-Flash": (2.0, 8.0)}
LOCK = threading.Lock()
STATE = {"model": "DeepSeek-V3.2-Exp", "ledger": None}


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def candidates():
    failed = set(STATE["ledger"].get("failed_items", []))
    for folder in sorted((ROOT / "database").iterdir()):
        ticker = folder.name
        if ticker not in FIRST | SECOND:
            continue
        for quarter in sorted((folder / "earnings").glob("20*Q*")):
            if int(quarter.name[:4]) < 2025:
                continue
            for stage in ("preview", "analysis"):
                packet_path = quarter / "materials" / (stage + ".json")
                output = quarter / "analysis" / (stage + ".md")
                if f"{ticker}/{quarter.name}/{stage}" in failed or (output.exists() and output.stat().st_size > 50):
                    continue
                packet = load(packet_path, None)
                if packet and packet.get("sources") and packet.get("facts"):
                    if stage == "analysis" and not packet.get("official_release_confirmed"):
                        continue
                    yield ticker, quarter.name, stage, packet, output


def compact(packet):
    facts = []
    remaining = 7500
    for item in packet["facts"]:
        item = str(item).strip()
        if not item or remaining < 100:
            break
        item = item[:min(850, remaining)]
        facts.append(item)
        remaining -= len(item)
    return {"cutoff": packet.get("cutoff"), "sources": packet["sources"][:3],
            "facts": facts, "historical_reconstruction": packet.get("historical_reconstruction", False),
            "note": packet.get("note", "")[:500]}


def request_model(model, prompt, evidence, json_mode=True):
    key = os.environ["PARATERA_API_KEY"]
    base = os.getenv("PARATERA_BASE_URL", "https://llmapi.paratera.com").rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = {"model": model, "temperature": 0.1, "max_tokens": 3000, "enable_thinking": False,
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)}]}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    request = urllib.request.Request(url, data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
                                     headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:400]
            if "No deployments available" in detail:
                raise RuntimeError("NO_DEPLOYMENT " + detail)
            if exc.code not in (429, 503) or attempt == 2:
                raise RuntimeError(f"HTTP {exc.code} {detail}")
            time.sleep(10 * (attempt + 1))


def charge(model, usage, label):
    prices = PRICE[model]
    input_tokens = int(usage.get("prompt_tokens") or 6000)
    output_tokens = int(usage.get("completion_tokens") or 4500)
    cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
    with LOCK:
        ledger = STATE["ledger"]
        ledger["spent_rmb_estimate"] += cost
        ledger["calls"].append({"item": label, "model": model, "input_tokens": input_tokens,
                                "output_tokens": output_tokens, "cost_rmb": round(cost, 6)})
        save(LEDGER, ledger)


def deterministic_draft(ticker, quarter, stage, packet, evidence, output, reason):
    """Preserve source-limited coverage if the cheap model exhausts its output."""
    url = evidence["sources"][0]
    historical = stage == "preview" and packet.get("historical_reconstruction")
    title = f"# {'历史资料重建：' if historical else ''}{ticker} {quarter} {'财报前瞻' if stage == 'preview' else '财报后分析'}（资料有限草稿）"
    lines = [title, "", f"资料截止：{packet.get('cutoff', '待核')}。以下仅根据[公司或监管原件]({url})可确认的项目整理。",
             "", "## 已核事实", ""]
    for fact in evidence["facts"]:
        label = fact
        label = re.sub(r"^Revenue:", "营收：", label)
        label = re.sub(r"^Operating income:", "营业利润：", label)
        label = re.sub(r"^Net income:", "净利润：", label)
        label = re.sub(r"^Operating cash flow:", "经营现金流：", label)
        label = label.replace("full fiscal year, not Q4 alone", "全年，不能当作 Q4 单季")
        label = label.replace("quarter;", "单季；")
        lines.append(f"- {label} [来源]({url})")
    if stage == "preview":
        lines += ["", "## 财报验证点", "",
                  "1. 核对当季收入、营业利润与上一份披露之间的变化；全年数据不能直接当作上季单季基数。",
                  "2. 核对经营现金流、产品或分部披露与管理层指引。资料包未提供的指标标为待核。",
                  "", "正面情形是收入增长伴随利润和现金同步改善；负面情形是增长未转化为利润或现金。二者均为待验证情形。"]
        if historical:
            lines += ["", "本稿为事后重建，不代表财报前实际发表的预测。"]
    else:
        lines += ["", "## 初步判断与待核", "",
                  "本季已披露数据可用于观察业务规模及利润变化，但资料包缺少完整分部、指引和可靠市场共识，相关差异待核。",
                  "无同期 Preview；不能事后补写预测再声称判断得到验证。",
                  "现金流与利润差异的原因需回到原始财报附注核对。"]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    save(output.with_suffix(".checks.json"), {"english_draft": "\n".join(evidence["facts"]),
        "reader_questions": ["财年与自然季度是否被混淆？", "利润与现金流的差异有何证据？", "哪些结论超出已提供的官方来源？"],
        "fact_checks": ["只使用所列来源。", "未提供的指引、共识和市场反应标待核。", "全年值不当作单季值。"],
        "generation_note": reason})
    save(output.with_suffix(".meta.json"), {"status": "source_limited_deterministic", "model": None,
        "generated_at": datetime.now(timezone.utc).isoformat(), "cutoff": packet.get("cutoff"),
        "sources": evidence["sources"], "historical_reconstruction": bool(historical)})


def generate(item):
    ticker, quarter, stage, packet, output = item
    label = f"{ticker}/{quarter}/{stage}"
    evidence = compact(packet)
    if packet.get("verification_status") in ("official_filing_text_collected", "official_release_discovered") and len(evidence["facts"]) <= 4:
        deterministic_draft(ticker, quarter, stage, packet, evidence, output,
                            "Sparse official source packet; no paid model call")
        return label, "SOURCE_LIMITED_NO_CALL"
    with LOCK:
        # Pessimistic allowance at the expensive model's rate, including a
        # large prompt and a complete 3000-token response.
        reservation = 0.25
        if STATE["ledger"]["spent_rmb_estimate"] + STATE["ledger"]["reserved_rmb"] + reservation > LIMIT_RMB:
            return label, "BUDGET_STOP"
        STATE["ledger"]["reserved_rmb"] += reservation
        save(LEDGER, STATE["ledger"])
        model = STATE["model"]
    try:
        prompt = (f"你是谨慎的中文财报研究编辑。写 {ticker} {quarter} {stage}。先形成简短英文中间稿，再编辑中文。"
                  "每句一个主要意思，核对事实、财年、币种、口径和来源。提出恰好三个怀疑读者问题。"
                  "只返回 JSON：english_draft（不超过80个英文词），reader_questions（三条短句），fact_checks（三条短句），markdown。"
                  "markdown 是约 500—700 中文字的 Markdown，直接链接所给官方来源。来源不足可写更短，并标待核。"
                  "严禁补造共识、股价反应或未提供的数字。10-K 全年值绝不可称为 Q4 单季值。"
                  "历史 Preview 必须在标题标明‘历史资料重建’，只使用上一份财报的事实，不声称为当时发表的预测。"
                  "Analysis 若无真正的财报前定稿，写明‘无同期 Preview’，不能把历史重建稿当成同期预测。")
        if stage == "preview":
            prompt = (f"根据以下已公开的上季官方事实，为 {ticker} {quarter} 写中文财报前瞻 Markdown。"
                      "只输出 Markdown，标题必须以 '# ' 开始。若是事后历史重建，标题必须写‘历史资料重建’。"
                      "全文约 350—550 中文字。概述上季业务及利润，提出本季两个验证问题和正负情形。"
                      "每个数字须链接所给来源。不要写本季实际结果，不编造共识或股价。")
        response = None
        try:
            response = request_model(model, prompt, evidence, json_mode=stage == "analysis")
        except RuntimeError as exc:
            if "NO_DEPLOYMENT" not in str(exc) or model != "DeepSeek-V3.2-Exp":
                raise
            with LOCK:
                STATE["model"] = "DeepSeek-V4.1-Flash"
                model = STATE["model"]
                STATE["ledger"]["selected_model"] = model
                save(LEDGER, STATE["ledger"])
            response = request_model(model, prompt, evidence, json_mode=stage == "analysis")
        charge(model, response.get("usage") or {}, label)
        content = response["choices"][0]["message"].get("content") or ""
        if stage == "preview":
            result = {"markdown": content,
                      "english_draft": "\n".join(evidence["facts"]),
                      "reader_questions": ["上季全年数字是否被误作单季数字？", "资料截止日之后的事实是否混入前瞻？", "两种情形的判断各由哪些官方事实支持？"],
                      "fact_checks": ["数字与口径只来自所列官方资料。", "预览不使用当季财报发布后的数据。", "没有可靠共识或市场反应时不填写。"]}
        else:
            result = json.loads(content)
        md = str(result.get("markdown") or "").strip()
        questions = result.get("reader_questions") or []
        if not md.startswith("# ") or len(questions) != 3 or not any(url in md for url in evidence["sources"]):
            raise ValueError("output format, reader check, or official citation missing")
        if stage == "preview" and packet.get("historical_reconstruction") and "历史资料重建" not in md[:150]:
            raise ValueError("historical preview label missing")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(md + "\n", encoding="utf-8")
        save(output.with_suffix(".checks.json"), {"english_draft": result.get("english_draft"),
                                                   "reader_questions": questions, "fact_checks": result.get("fact_checks")})
        save(output.with_suffix(".meta.json"), {"status": "generated_review_pending", "model": model,
                                                 "generated_at": datetime.now(timezone.utc).isoformat(),
                                                 "cutoff": packet.get("cutoff"), "sources": evidence["sources"],
                                                 "historical_reconstruction": bool(packet.get("historical_reconstruction"))})
        with LOCK:
            if label in STATE["ledger"].get("failed_items", []):
                STATE["ledger"]["failed_items"].remove(label)
                save(LEDGER, STATE["ledger"])
        return label, "OK"
    except Exception as exc:
        with LOCK:
            STATE["ledger"].setdefault("errors", {})[label] = repr(exc)[:300]
            STATE["ledger"].setdefault("fallback_items", []).append(label)
            save(LEDGER, STATE["ledger"])
        deterministic_draft(ticker, quarter, stage, packet, evidence, output, repr(exc)[:300])
        return label, "SOURCE_LIMITED " + repr(exc)[:300]
    finally:
        with LOCK:
            STATE["ledger"]["reserved_rmb"] = max(0, STATE["ledger"]["reserved_rmb"] - reservation)
            save(LEDGER, STATE["ledger"])


def main():
    has_key = bool(os.getenv("PARATERA_API_KEY"))
    STATE["ledger"] = load(LEDGER, {"limit_rmb": LIMIT_RMB, "spent_rmb_estimate": 0.0,
                                    "reserved_rmb": 0.0, "calls": [], "failed_items": [], "errors": {}, "fallback_items": []})
    STATE["ledger"]["reserved_rmb"] = 0.0
    STATE["model"] = STATE["ledger"].get("selected_model", "DeepSeek-V3.2-Exp")
    all_items = list(candidates())
    if not has_key:
        print("PARATERA_API_KEY missing; no paid calls; source packets retained", flush=True)
        return
    call_limit = int(os.getenv("RESEARCH_CALL_LIMIT", "12"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for label, status in executor.map(generate, all_items[:call_limit]):
            print(label, status, flush=True)
    print("Estimated spent RMB", round(STATE["ledger"]["spent_rmb_estimate"], 4), flush=True)


if __name__ == "__main__":
    main()
