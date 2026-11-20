"""Audit published research index against files, sources, and stage boundaries."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    index = json.loads((ROOT / "data/research_index.json").read_text(encoding="utf-8"))
    counts = Counter()
    issues = []
    for event_id, event in index["events"].items():
        for stage_name, stage in event["stages"].items():
            status = stage["status"]
            counts[status] += 1
            path = stage.get("path")
            packet_path = stage.get("source_packet")
            if not path:
                continue
            article = ROOT / path
            if not article.is_file():
                issues.append(f"{event_id}/{stage_name}: missing Markdown")
                continue
            text = article.read_text(encoding="utf-8")
            if not text.startswith("# "):
                issues.append(f"{event_id}/{stage_name}: missing title")
            if stage_name == "preview" and ("## Analysis" in text or "无同期 Preview" in text):
                issues.append(f"{event_id}/{stage_name}: Analysis content in Preview")
            if status == "generated_review_pending":
                checks = article.with_suffix(".checks.json")
                if not checks.is_file():
                    issues.append(f"{event_id}/{stage_name}: missing process record")
                if not packet_path or not (ROOT / packet_path).is_file():
                    issues.append(f"{event_id}/{stage_name}: missing source packet")
                else:
                    packet = json.loads((ROOT / packet_path).read_text(encoding="utf-8"))
                    if not any(url in text for url in packet.get("sources", [])):
                        issues.append(f"{event_id}/{stage_name}: no supplied source URL cited")
    result = {"events": len(index["events"]), "stage_status": dict(counts), "issues": issues}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if issues:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
