"""Audit both tiers' 2025 onward sources, saved drafts and spending cap."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
FIRST = ("MSFT", "AMZN", "META", "GOOGL", "ORCL", "NVDA", "AVGO", "AMD", "MU", "INTC", "SKHX", "SMSN")
SECOND = ("CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML")


def main():
    problems = []
    counts = {"drafts": 0, "model_drafts": 0, "source_limited_drafts": 0,
              "manual_drafts": 0, "analysis_unavailable": 0, "preview_unavailable": 0}
    for tickers in (FIRST, SECOND):
        for ticker in tickers:
            for folder in sorted((ROOT / "database" / ticker / "earnings").glob("20*Q*")):
                quarter = folder.name
                if quarter[:4] < "2025":
                    continue
                for stage in ("preview", "analysis"):
                    packet_path = folder / "materials" / f"{stage}.json"
                    article = folder / "analysis" / f"{stage}.md"
                    meta_path = folder / "analysis" / f"{stage}.meta.json"
                    if not packet_path.exists():
                        if not article.exists():
                            counts[f"{stage}_unavailable"] += 1
                            continue
                        problems.append(f"missing packet: {ticker}/{quarter}/{stage}")
                        continue
                    packet = json.loads(packet_path.read_text(encoding="utf-8"))
                    if not packet.get("sources") or not packet.get("facts"):
                        problems.append(f"empty packet: {ticker}/{quarter}/{stage}")
                    if not article.exists():
                        problems.append(f"missing article: {ticker}/{quarter}/{stage}")
                        continue
                    md = article.read_text(encoding="utf-8")
                    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {"status": "manual"}
                    counts["drafts"] += 1
                    if meta.get("status") == "source_limited_deterministic":
                        counts["source_limited_drafts"] += 1
                    elif meta.get("status") == "generated_review_pending":
                        counts["model_drafts"] += 1
                    else:
                        counts["manual_drafts"] += 1
                    if not md.startswith("# ") or not any(source in md for source in packet["sources"]):
                        problems.append(f"citation or title: {ticker}/{quarter}/{stage}")
                    if stage == "preview" and packet.get("historical_reconstruction") and "历史资料重建" not in md[:150]:
                        problems.append(f"historical preview label: {ticker}/{quarter}")
    ledger_path = ROOT / "data" / "generation_budget_2025_2026.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8")) if ledger_path.exists() else {}
    if ledger.get("spent_rmb_estimate", 0) > 40:
        problems.append("budget exceeded")
    print(json.dumps({"counts": counts, "spent_rmb_estimate": ledger.get("spent_rmb_estimate"),
                      "issues": problems}, ensure_ascii=False, indent=2))
    if problems:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
