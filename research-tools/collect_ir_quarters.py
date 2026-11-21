"""Curated company IR packets for issuers without SEC quarterly XBRL."""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SECOND = {"CRWV", "NBIS", "SNDK", "WDC", "STX", "AMAT", "CSCO", "LRCX", "ASML"}
# Each fact below is taken from the linked issuer's dated earnings release.
RELEASES = {
    "SMSN": [
        ("2025Q1", "2025-04-30", "https://news.samsung.com/global/samsung-electronics-announces-first-quarter-2025-results", ["Samsung Electronics Q1 2025 consolidated revenue KRW 79.14 trillion; operating profit KRW 6.7 trillion.", "Device Solutions division revenue decreased quarter on quarter; Galaxy S25 and high-value products supported consolidated revenue."]),
        ("2025Q2", "2025-07-31", "https://news.samsung.com/global/samsung-electronics-announces-second-quarter-2025-results", ["Samsung Electronics Q2 2025 consolidated revenue KRW 74.6 trillion, down 5.8% quarter on quarter; operating profit KRW 4.7 trillion.", "Device Solutions sales increased but memory inventory adjustments and China export restriction costs hurt profit."]),
        ("2025Q3", "2025-10-30", "https://news.samsung.com/global/samsung-electronics-announces-third-quarter-2025-results", ["Samsung Electronics Q3 2025 consolidated revenue KRW 86.1 trillion, up 15.4% quarter on quarter; operating profit KRW 12.2 trillion.", "Device Solutions sales rose 19% quarter on quarter; Memory set a quarterly sales record, driven by HBM3E and server SSDs."]),
    ],
    "SKHX": [
        ("2025Q1", "2025-04-24", "https://news.skhynix.com/en/sk-hynix-announces-1q25-financial-results/", ["SK hynix Q1 2025 K-IFRS revenue KRW 17.6391 trillion, operating profit KRW 7.4405 trillion, net profit KRW 8.1082 trillion.", "Operating margin was 42%."]),
        ("2025Q2", "2025-07-24", "https://news.skhynix.com/en/sk-hynix-announces-2q25-financial-results/", ["SK hynix Q2 2025 K-IFRS revenue KRW 22.232 trillion, operating profit KRW 9.2129 trillion, net profit KRW 6.9962 trillion.", "HBM3E and NAND sales expanded amid AI memory demand; operating margin was 41%."]),
        ("2025Q3", "2025-10-29", "https://news.skhynix.com/en/sk-hynix-announces-3q25-financial-results/", ["SK hynix Q3 2025 K-IFRS revenue KRW 24.4489 trillion, operating profit KRW 11.3834 trillion, net profit KRW 12.5975 trillion.", "Operating margin 47%; 12-high HBM3E and server DDR5 supported record performance."]),
    ],
    "ASML": [
        ("2026Q1", "2026-04-15", "https://investor.asml.com/news-releases/news-release-details/q1-2026-financial-results", ["ASML Q1 2026 sales EUR 8.767 billion; gross margin 53.0%; net income EUR 2.757 billion.", "Q2 sales guidance was EUR 8.4–9.0 billion and gross margin 51–52%."]),
        ("2026Q2", "2026-07-15", "https://investor.asml.com/news-releases/news-release-details/q2-2026-financial-results", ["ASML Q2 2026 sales EUR 9.326 billion; gross margin 54.0%; net income EUR 2.918 billion.", "Installed Base Management sales EUR 2.762 billion; Q3 sales guidance EUR 11–12 billion."]),
        ("2026Q3", "2026-10-14", "https://investor.asml.com/news-releases/news-release-details/asml-reports-eu11.7-billion-total-net-sales-and-eu5.0-billion-net-income-q3-2026", ["ASML Q3 2026 sales EUR 11.662 billion; gross margin 57.5%; net income EUR 4.960 billion.", "Installed Base Management sales EUR 3.289 billion; Q4 sales guidance EUR 14.2–15.2 billion."]),
    ],
    "NBIS": [
        ("2026Q1", "2026-05-13", "https://assets.nebius.com/assets/6fc0ea6c-0884-4a1f-bed8-1f797eb9628f/Financial%20results_Q1%202026.pdf", ["Nebius Q1 2026 consolidated revenue USD 399.0 million; adjusted EBITDA USD 129.5 million (non-GAAP).", "Net income from continuing operations USD 621.2 million; purchased property, equipment and intangibles USD 2,472.9 million."]),
        ("2026Q2", "2026-08-12", "https://assets.nebius.com/assets/72a8c258-bbb7-4df7-ab9d-8698f6cb88fc/PR.pdf", ["Nebius Q2 2026 consolidated revenue USD 582.3 million; adjusted EBITDA USD 236.2 million (non-GAAP).", "Net loss from continuing operations USD 190.4 million."]),
        ("2026Q3", "2026-11-12", "https://assets.nebius.com/assets/508584f1-b73d-484f-b64f-f96a5bc3b515/Nebius%20Q3%202026%20Financial%20Results%20Press%20Release.pdf", ["Nebius Q3 2026 consolidated revenue USD 980.8 million; adjusted EBITDA USD 465.8 million (non-GAAP).", "Net loss from continuing operations USD 37.5 million."]),
    ],
}


def save_if_absent(path: Path, value):
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    initial_previews = {
        "SKHX": ("2025Q1", "2025-01-23", "https://news.skhynix.com/en/sk-hynix-announces-4q24-financial-results/", ["SK hynix Q4 2024 K-IFRS revenue KRW 19.7670 trillion; operating profit KRW 8.0828 trillion; net profit KRW 8.0065 trillion."]),
        "SMSN": ("2025Q1", "2025-01-31", "https://news.samsung.com/global/samsung-electronics-announces-fourth-quarter-and-fy-2024-results", ["Samsung Electronics Q4 2024 consolidated revenue KRW 75.8 trillion; operating profit KRW 6.5 trillion."]),
        "ASML": ("2026Q1", "2026-01-28", "https://www.investor.asml.com/news-releases/news-release-details/q4-2025-financial-results", ["ASML Q4 2025 sales EUR 9.718 billion; Q1 2026 sales guidance EUR 8.2–8.9 billion."]),
        "NBIS": ("2026Q1", "2026-02-12", "https://assets.nebius.com/assets/2829268f-924f-4846-87b5-2365b7e58b41/Financial%20results_Q4%202025_11022026.pdf", ["Nebius Q4 2025 consolidated revenue USD 227.7 million; adjusted EBITDA USD 15.0 million (non-GAAP).", "Operating cash from continuing operations USD 834.3 million; property and equipment purchases USD 2,056.0 million."]),
    }
    for ticker, (q, day, url, facts) in initial_previews.items():
        target = ROOT / "database" / ticker / "earnings" / q / "materials" / "preview.json"
        save_if_absent(target, {"ticker": ticker, "calendar_quarter": q, "cutoff": day + "T23:59:59Z",
            "sources": [url], "facts": facts, "historical_reconstruction": True,
            "verification_status": "manual_verified", "note": "Historical reconstruction using prior official release only."})
    for ticker, entries in RELEASES.items():
        for i, (q, day, url, facts) in enumerate(entries):
            folder = ROOT / "database" / ticker / "earnings" / q
            materials = folder / "materials"
            save_if_absent(folder / "event.json", {"ticker": ticker, "quarter": q, "earnings_date": day})
            save_if_absent(materials / "analysis.json", {"ticker": ticker, "calendar_quarter": q,
                "cutoff": day + "T23:59:59Z", "sources": [url], "facts": facts,
                "official_release_confirmed": True, "verification_status": "manual_verified",
                "note": "Curated from company IR release; article still needs editorial review."})
            if i:
                prior = entries[i - 1]
                save_if_absent(materials / "preview.json", {"ticker": ticker, "calendar_quarter": q,
                    "target_event_date": day, "cutoff": prior[1] + "T23:59:59Z",
                    "sources": [prior[2]], "facts": prior[3], "historical_reconstruction": True,
                    "verification_status": "manual_verified",
                    "note": "Historical reconstruction using previous release only."})
            if not (materials / "README.md").exists():
                materials.mkdir(parents=True, exist_ok=True)
                (materials / "README.md").write_text(f"# {ticker} {q} 官方原始资料\n\n[公司财报公告]({url})\n\n" +
                    "\n".join("- " + fact for fact in facts) + "\n", encoding="utf-8")
        if ticker in ("ASML", "NBIS"):
            prior = entries[-1]
            q = "2026Q4"
            folder = ROOT / "database" / ticker / "earnings" / q / "materials"
            save_if_absent(folder / "preview.json", {"ticker": ticker, "calendar_quarter": q,
                "cutoff": prior[1] + "T23:59:59Z", "sources": [prior[2]], "facts": prior[3],
                "verification_status": "manual_verified", "note": "Forward preview using latest available official release."})
    for ticker in SECOND - {"ASML", "NBIS"}:
        earnings = ROOT / "database" / ticker / "earnings"
        upcoming = earnings / "2026Q4" / "materials"
        if (upcoming / "analysis.json").exists() or (upcoming / "preview.json").exists():
            continue
        prior = sorted(earnings.glob("2026Q*/materials/analysis.json"))
        if not prior:
            continue
        packet = json.loads(prior[-1].read_text(encoding="utf-8"))
        save_if_absent(upcoming / "preview.json", {"ticker": ticker, "calendar_quarter": "2026Q4",
            "cutoff": packet["cutoff"], "sources": packet["sources"], "facts": packet["facts"],
            "verification_status": "official_filing_text_collected",
            "note": "Forward preview based on latest filed quarter; release schedule requires confirmation."})


if __name__ == "__main__":
    main()
