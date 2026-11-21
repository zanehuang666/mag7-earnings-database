"""Budget-capped one-time Markdown draft generator for 2025/2026 expansion."""
from __future__ import annotations

import concurrent.futures
import json
import os
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
        year = "2025" if ticker in FIRST else "2026" if ticker in SECOND else None
        if year is None:
            continue
        for quarter in sorted((folder / "earnings").glob(year + "Q*")):
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


def request_model(model, prompt, evidence):
    key = os.environ["PARATERA_API_KEY"]
    base = os.getenv("PARATERA_BASE_URL", "https://llmapi.paratera.com").rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = {"model": model, "temperature": 0.1, "max_tokens": 2700, "enable_thinking": False,
            "response_format": {"type": "json_object"},
            "messages": [{"role": "system", "content": prompt},
                         {"role": "user", "content": json.dumps(evidence, ensure_ascii=False)}]}
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
    output_tokens = int(usage.get("completion_tokens") or 2700)
    cost = (input_tokens * prices[0] + output_tokens * prices[1]) / 1_000_000
    with LOCK:
        ledger = STATE["ledger"]
        ledger["spent_rmb_estimate"] += cost
        ledger["calls"].append({"item": label, "model": model, "input_tokens": input_tokens,
                                "output_tokens": output_tokens, "cost_rmb": round(cost, 6)})
        save(LEDGER, ledger)


def generate(item):
    ticker, quarter, stage, packet, output = item
    label = f"{ticker}/{quarter}/{stage}"
    with LOCK:
        # Reserve a conservative 0.10 RMB per in-flight request. All known
        # models cost less than this with the fixed prompt and output ceiling.
        if STATE["ledger"]["spent_rmb_estimate"] + STATE["ledger"]["reserved_rmb"] + 0.10 > LIMIT_RMB:
            return label, "BUDGET_STOP"
        STATE["ledger"]["reserved_rmb"] += 0.10
        save(LEDGER, STATE["ledger"])
        model = STATE["model"]
    try:
        evidence = compact(packet)
        prompt = (f"你是谨慎的中文财报研究编辑。写 {ticker} {quarter} {stage}。先形成简短英文中间稿，再编辑中文。"
                  "每句一个主要意思，核对事实、财年、币种、口径和来源。提出恰好三个怀疑读者问题。"
                  "只返回 JSON：english_draft（简短英文），reader_questions（三条），fact_checks（简短中文），markdown。"
                  "markdown 是约 500—700 中文字的 Markdown，直接链接所给官方来源。来源不足可写更短，并标待核。"
                  "严禁补造共识、股价反应或未提供的数字。10-K 全年值绝不可称为 Q4 单季值。"
                  "历史 Preview 必须在标题标明‘历史资料重建’，只使用上一份财报的事实，不声称为当时发表的预测。"
                  "Analysis 若无真正的财报前定稿，写明‘无同期 Preview’，不能把历史重建稿当成同期预测。")
        response = None
        try:
            response = request_model(model, prompt, evidence)
        except RuntimeError as exc:
            if "NO_DEPLOYMENT" not in str(exc) or model != "DeepSeek-V3.2-Exp":
                raise
            with LOCK:
                STATE["model"] = "DeepSeek-V4.1-Flash"
                model = STATE["model"]
                STATE["ledger"]["selected_model"] = model
                save(LEDGER, STATE["ledger"])
            response = request_model(model, prompt, evidence)
        charge(model, response.get("usage") or {}, label)
        content = response["choices"][0]["message"].get("content") or ""
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
        return label, "OK"
    except Exception as exc:
        with LOCK:
            STATE["ledger"].setdefault("failed_items", []).append(label)
            STATE["ledger"].setdefault("errors", {})[label] = repr(exc)[:300]
            save(LEDGER, STATE["ledger"])
        return label, "ERROR " + repr(exc)[:300]
    finally:
        with LOCK:
            STATE["ledger"]["reserved_rmb"] = max(0, STATE["ledger"]["reserved_rmb"] - 0.10)
            save(LEDGER, STATE["ledger"])


def main():
    if not os.getenv("PARATERA_API_KEY"):
        raise RuntimeError("PARATERA_API_KEY missing")
    STATE["ledger"] = load(LEDGER, {"limit_rmb": LIMIT_RMB, "spent_rmb_estimate": 0.0,
                                    "reserved_rmb": 0.0, "calls": [], "failed_items": [], "errors": {}})
    STATE["ledger"]["reserved_rmb"] = 0.0
    STATE["model"] = STATE["ledger"].get("selected_model", "DeepSeek-V3.2-Exp")
    all_items = list(candidates())
    call_limit = int(os.getenv("RESEARCH_CALL_LIMIT", "12"))
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        for label, status in executor.map(generate, all_items[:call_limit]):
            print(label, status, flush=True)
    print("Estimated spent RMB", round(STATE["ledger"]["spent_rmb_estimate"], 4), flush=True)


if __name__ == "__main__":
    main()
