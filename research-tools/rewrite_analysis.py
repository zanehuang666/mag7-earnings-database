"""Rewrite generated quarterly analyses without replacing human edits.

Run with PARATERA_API_KEY. The historical ledger and this run share a hard cap.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import urllib.error
import urllib.request
from html.parser import HTMLParser
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEDGER = ROOT / "data/generation_budget_2025_2026.json"
CAP = 30.0
MODEL = "DeepSeek-V3.2-Exp"
PRICES = {"DeepSeek-V3.2-Exp": (2.0, 3.0), "DeepSeek-V4.1-Flash": (2.0, 8.0)}
VERSION = "analysis-v2-20261125"


class VisibleText(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hidden = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "noscript"}:
            self.hidden += 1
        if tag in {"p", "tr", "li", "h1", "h2", "h3"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "noscript"} and self.hidden:
            self.hidden -= 1

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def official_excerpt(url: str) -> str:
    """Select short, relevant passages from the linked official release."""
    if not url.startswith("https://"):
        return ""
    req = urllib.request.Request(url, headers={"User-Agent":
        "EarningsDatabase research contact zane.h.2500@gmail.com"})
    try:
        with urllib.request.urlopen(req, timeout=25) as response:
            raw = response.read(1_500_000).decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError):
        return ""
    parser = VisibleText()
    parser.feed(raw)
    lines = [" ".join(x.split()) for x in "".join(parser.parts).splitlines()]
    lines = [x for x in lines if 50 <= len(x) <= 1500]
    pattern = re.compile(r"revenue|segment|data.center|cloud|gross.margin|operating.income|cash.flow|capital.expenditure|guidance|outlook", re.I)
    selected = [x for x in lines if pattern.search(x)]
    return "\n".join(selected[:55])[:16000]


def read(path: Path, default=None):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def write(path: Path, obj):
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def matches_recorded_hash(md: Path, recorded: str | None) -> bool:
    if not recorded:
        return False
    raw = md.read_bytes()
    variants = {raw, raw.replace(b"\r\n", b"\n"),
                raw.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")}
    return any(hashlib.sha256(value).hexdigest() == recorded for value in variants)


def candidates():
    attempts = read(LEDGER, {}).get("rewrite_attempts", {})
    for md in sorted((ROOT / "database").glob("*/earnings/20*Q*/analysis/analysis.md")):
        if int(md.parts[-3][:4]) < 2025:
            continue
        meta = read(md.with_suffix(".meta.json"), {})
        if meta.get("status") not in {"generated_review_pending", "source_limited_deterministic"}:
            continue
        if not matches_recorded_hash(md, meta.get("output_sha256")):
            continue  # human edit: do not overwrite
        if meta.get("rewrite_version") == VERSION:
            continue
        if f"{md.parts[-5]}/{md.parts[-3]}/analysis-rewrite" in attempts:
            continue
        packet = read(md.parents[1] / "materials/analysis.json", {})
        if not packet.get("official_release_confirmed") or not packet.get("sources"):
            continue
        yield md, meta, packet


def evidence(md: Path, packet: dict):
    quarter = md.parents[1]
    prev = quarter / "analysis/preview.md"
    preview = prev.read_text(encoding="utf-8")[:7500] if prev.exists() else ""
    pmeta = read(prev.with_suffix(".meta.json"), {}) if prev.exists() else {}
    true_preview = bool(preview) and not pmeta.get("historical_reconstruction")
    return {
        "company": md.parts[-5], "quarter": quarter.name,
        "cutoff": packet.get("cutoff"), "sources": packet["sources"],
        "verified_facts": packet.get("facts", []), "source_note": packet.get("note", ""),
        "preview": preview if true_preview else "",
        "preview_status": "contemporaneous" if true_preview else "no contemporaneous preview",
        "official_release_excerpt": official_excerpt(packet["sources"][0]),
    }


SYSTEM = """你是中文买方财报研究编辑。根据提供的官方来源、已核事实和官方原文节选，写一篇可直接阅读的财报后分析 Markdown。
先在内部用简明英文梳理因果，再写自然中文；英文不输出。直接输出 Markdown，不输出 JSON 或代码围栏。
结构：标题与资料截止；主要结论；财报数据和主要产品；利润与现金；Preview 判断复核（若无同期 Preview，说明并改写为本季核心问题）；下一季判断与关键验证点；资料来源。
Analysis 的质量优先于篇幅：开头给出明确且有条件的判断，解释业务变化如何传至利润和现金，区分经营事实与推论；对 Preview 的关键判断逐项比较实际结果及偏差原因。避免把事实清单改写成空泛评论。
只使用证据中明确给出的数字。官方原文节选可能含相邻季度或全年数据，必须核对期间，无法确认则不用。每个关键数字附所给原始来源链接。没有分部、产品、资本开支、指引、共识或市场反应证据时，不编造；在对应章节简洁说明尚待核实及需查的具体项目。不要重复写大段免责声明，不要把全年值写成 Q4 单季。
如果 Preview 是事后重建，绝不当作同期预测。币种、财年、季度、会计口径必须清楚。输出约 700–1100 中文字，证据稀少时允许更短，但仍需有实质判断和具体核查路径。"""


def ask(model: str, payload: dict):
    base = os.getenv("PARATERA_BASE_URL", "https://llmapi.paratera.com").rstrip("/")
    url = base + ("/chat/completions" if base.endswith("/v1") else "/v1/chat/completions")
    body = {"model": model, "temperature": 0.2, "max_tokens": 6000,
            "enable_thinking": False, "thinking": {"type": "disabled"},
            "messages": [{"role": "system", "content": SYSTEM},
                         {"role": "user", "content": json.dumps(payload, ensure_ascii=False)}]}
    req = urllib.request.Request(url, json.dumps(body, ensure_ascii=False).encode(),
                                 {"Authorization": "Bearer " + os.environ["PARATERA_API_KEY"],
                                  "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def invalid_reasons(md: str, sources: list[str], payload: dict):
    reasons = []
    if not md.startswith("# ") or len(md) < 500:
        reasons.append("title_or_length")
    if not any(url in md for url in sources):
        reasons.append("source_link")
    if len(re.findall(r"^## ", md, re.M)) < 4:
        reasons.append("sections")
    if payload["preview_status"] != "contemporaneous" and not re.search(
            r"无同期\s*Preview|没有同期\s*Preview|无财报前定稿|没有财报前定稿", md):
        reasons.append("preview_status")
    return reasons


def main():
    ledger = read(LEDGER)
    if ledger is None:
        raise SystemExit("Historical cost ledger missing; refusing paid calls")
    spent = float(ledger["spent_rmb_estimate"])
    if not os.getenv("PARATERA_API_KEY"):
        raise SystemExit("PARATERA_API_KEY missing; no paid calls made")
    if spent >= CAP:
        raise SystemExit(f"Historical spend {spent:.4f} already reaches cap {CAP}")
    results = {"rewritten": 0, "rejected": 0, "failed": 0}
    selected_model = MODEL
    call_limit = int(os.getenv("REWRITE_CALL_LIMIT", "5"))
    for md, meta, packet in list(candidates())[:call_limit]:
        # Reserve a full 6,000 output tokens at the higher Flash tariff, plus
        # 12,000 input tokens. Stop before any call could cross the shared cap.
        reservation = (12000 * 2 + 6000 * 8) / 1_000_000
        if spent + reservation > CAP:
            print("BUDGET_STOP", round(spent, 6), flush=True)
            break
        payload = evidence(md, packet)
        label = f"{payload['company']}/{payload['quarter']}/analysis-rewrite"
        try:
            try:
                result = ask(selected_model, payload)
            except urllib.error.HTTPError as exc:
                detail = exc.read().decode("utf-8", "replace")[:300]
                if selected_model != MODEL or "No deployments available" not in detail:
                    raise RuntimeError(f"HTTP {exc.code}: {detail}") from exc
                selected_model = "DeepSeek-V4.1-Flash"
                result = ask(selected_model, payload)
        except (urllib.error.URLError, RuntimeError, ValueError, KeyError) as exc:
            results["failed"] += 1
            ledger.setdefault("rewrite_attempts", {})[label] = "api_error"
            write(LEDGER, ledger)
            print(label, "API_ERROR", str(exc)[:100], flush=True)
            continue
        usage = result.get("usage") or {}
        inp = int(usage.get("prompt_tokens") or 12000)
        out = int(usage.get("completion_tokens") or 6000)
        cost = (inp * PRICES[selected_model][0] + out * PRICES[selected_model][1]) / 1_000_000
        spent += cost
        ledger["spent_rmb_estimate"] = round(spent, 6)
        ledger["limit_rmb"] = CAP
        ledger.setdefault("calls", []).append({"item": label, "model": selected_model,
            "input_tokens": inp, "output_tokens": out, "cost_rmb": round(cost, 6)})
        write(LEDGER, ledger)  # charge even if the returned draft fails review
        choice = (result.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        draft = (message.get("content") or "").strip()
        if os.getenv("REWRITE_DEBUG_DRAFT") == "1":
            print(label, "DEBUG", json.dumps({"chars": len(draft),
                "model": selected_model, "finish_reason": choice.get("finish_reason"),
                "message_keys": list(message),
                "reasoning_chars": len(message.get("reasoning_content") or ""),
                "headings": len(re.findall(r"^## ", draft, re.M)),
                "cited": any(url in draft for url in packet["sources"]),
                "preview_marker": "无同期 Preview" in draft,
                "source_excerpt_chars": len(payload["official_release_excerpt"]),
                "draft": draft[:5000]}, ensure_ascii=False), flush=True)
        reasons = invalid_reasons(draft, packet["sources"], payload)
        if reasons:
            results["rejected"] += 1
            ledger.setdefault("rewrite_attempts", {})[label] = "quality_reject"
            write(LEDGER, ledger)
            print(label, "QUALITY_REJECT", ",".join(reasons), flush=True)
            continue
        history = md.parent / "history"
        history.mkdir(exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        for suffix in (".md", ".meta.json", ".checks.json"):
            old = md.with_suffix(suffix)
            if old.exists():
                (history / f"analysis-{stamp}{suffix}").write_bytes(old.read_bytes())
        md.write_text(draft + "\n", encoding="utf-8")
        meta.update({"status": "generated_review_pending", "model": selected_model,
                     "rewrite_version": VERSION, "generated_at": datetime.now(timezone.utc).isoformat(),
                     "output_sha256": hashlib.sha256(md.read_bytes()).hexdigest()})
        write(md.with_suffix(".meta.json"), meta)
        ledger.setdefault("rewrite_attempts", {})[label] = "rewritten"
        write(LEDGER, ledger)
        results["rewritten"] += 1
        print(label, "OK", flush=True)
    print(json.dumps({**results, "remaining": len(list(candidates())),
                      "historical_and_new_spend_rmb": round(spent, 6),
                      "cap_rmb": CAP}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
