"""Organize the copied trial site into a company-first, downloadable database."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "database"
REPORT_INDEX = ROOT / "data" / "report_index.json"
RESEARCH_INDEX = ROOT / "data" / "research_index.json"


def move_contents(source: Path, destination: Path) -> None:
    if not source.exists():
        return
    destination.mkdir(parents=True, exist_ok=True)
    for child in source.iterdir():
        target = destination / child.name
        if target.exists():
            raise FileExistsError(target)
        shutil.move(str(child), str(target))
    source.rmdir()


def main() -> None:
    reports = json.loads(REPORT_INDEX.read_text(encoding="utf-8"))
    research = json.loads(RESEARCH_INDEX.read_text(encoding="utf-8"))
    replacements: dict[str, str] = {}
    for ticker, report in reports.items():
        company = DATABASE / ticker
        company.mkdir(parents=True, exist_ok=True)
        old_data = ROOT / "reports" / ticker / "data"
        move_contents(old_data, company / "html-research" / "data")
        old_checks = ROOT / "reports" / ticker / "checks"
        move_contents(old_checks, company / "html-research" / "checks")
        (company / "README.md").write_text(
            f"# {ticker}\n\n"
            f"- [HTML 展示](../../{report['path']})\n"
            f"- [HTML 研究数据与检查](html-research/)\n"
            f"- [逐季财报与分析](earnings/)\n\n"
            "原有研究状态见 `data/report_index.json`。资料索引或草稿不代表逐值核实。\n",
            encoding="utf-8",
        )
    for event in research["events"].values():
        ticker, quarter = event["ticker"], event["quarter"]
        earnings = DATABASE / ticker / "earnings" / quarter
        earnings.mkdir(parents=True, exist_ok=True)
        (earnings / "event.json").write_text(
            json.dumps({"ticker": ticker, "quarter": quarter,
                        "earnings_date": event.get("date"),
                        "stages": {k: v.get("status") for k, v in event["stages"].items()}},
                       ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        move_contents(ROOT / "research" / ticker / quarter, earnings / "analysis")
        move_contents(ROOT / "source-packets" / ticker / quarter, earnings / "materials")
        placeholder = earnings / "analysis" / "analysis-prompt.placeholder.md"
        placeholder.parent.mkdir(parents=True, exist_ok=True)
        placeholder.write_text(
            "# 财报分析提示词占位\n\n用户后续提供正式 prompt；当前不生成新分析文案。\n",
            encoding="utf-8",
        )
        for stage in event["stages"].values():
            for field, folder in (("path", "analysis"), ("source_packet", "materials")):
                old = stage.get(field)
                if old:
                    new = f"database/{ticker}/earnings/{quarter}/{folder}/{Path(old).name}"
                    replacements[old] = new
                    stage[field] = new
    for ticker in reports:
        old = f"reports/{ticker}/data/"
        replacements[old] = f"database/{ticker}/html-research/data/"
    RESEARCH_INDEX.write_text(json.dumps(research, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for page in (ROOT / "calendar.html", ROOT / "trial-offline.html"):
        if page.exists():
            text = page.read_text(encoding="utf-8")
            for old, new in sorted(replacements.items(), key=lambda pair: -len(pair[0])):
                text = text.replace(old, new)
            page.write_text(text, encoding="utf-8")
    for folder in (ROOT / "research", ROOT / "source-packets"):
        for child in sorted(folder.glob("*")):
            if child.is_dir() and not any(child.iterdir()):
                child.rmdir()
        if folder.exists() and not any(folder.iterdir()):
            folder.rmdir()


if __name__ == "__main__":
    main()
