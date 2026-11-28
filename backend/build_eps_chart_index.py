"""Build the small static EPS marker feed from per-quarter source JSON files."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
rows = []
for path in sorted((ROOT / "database").glob("*/earnings/*/eps-surprise.json")):
    item = json.loads(path.read_text(encoding="utf-8"))
    if item.get("result") not in {"beat", "miss", "in_line"}:
        continue
    if not item.get("report_date"):
        continue
    rows.append({key: item.get(key) for key in
        ("ticker", "quarter", "report_date", "actual_eps", "consensus_eps", "difference", "surprise_pct", "result", "currency")})
out = ROOT / "data" / "eps_chart_markers.json"
out.write_text(json.dumps({"records": rows}, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
print(f"wrote {len(rows)} EPS chart markers")
