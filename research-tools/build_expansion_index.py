"""Build a readable index for the requested one-time report expansion."""
from pathlib import Path
import json

ROOT = Path(__file__).resolve().parents[1]
FIRST = ("MSFT", "AMZN", "META", "GOOGL", "ORCL", "NVDA", "AVGO", "AMD", "MU", "INTC", "SKHX", "SMSN")
SECOND = ("CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML")


def link(path: Path, label: str) -> str:
    return f"[{label}]({path.relative_to(ROOT).as_posix()})" if path.exists() else "待核"


def main():
    lines = ["# 2025 年以来季度研究目录", "",
             "第一、第二梯队均覆盖 2025 年以来已有原始资料的季度。",
             "历史 Preview 仅为基于前一份官方资料的事后重建，不是同期发表的预测。",
             "生成文案均为待审阅草稿；原始资料及核查过程见各公司季度文件夹。", ""]
    for title, tickers in (("第一梯队", FIRST), ("第二梯队", SECOND)):
        lines += [f"## {title}", "", "| 公司 | 季度 | 财报前稿 | 财报后稿 | 原始资料 |", "|---|---|---|---|---|"]
        for ticker in tickers:
            earnings = ROOT / "database" / ticker / "earnings"
            quarters = sorted(q for q in earnings.glob("20*Q*") if q.name[:4] >= "2025")
            for quarter in quarters:
                materials = quarter / "materials"
                lines.append(f"| {ticker} | {quarter.name} | {link(quarter / 'analysis' / 'preview.md', 'Preview')} | "
                             f"{link(quarter / 'analysis' / 'analysis.md', 'Analysis')} | "
                             f"{link(materials / 'README.md', '资料说明')} |")
        lines.append("")
    ledger_path = ROOT / "data" / "generation_budget_2025_2026.json"
    if ledger_path.exists():
        ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
        lines += ["## 模型费用", "", f"调用估算费用：¥{ledger.get('spent_rmb_estimate', 0):.4f} / ¥40 上限。", ""]
    (ROOT / "RESEARCH_EXPANSION_INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
