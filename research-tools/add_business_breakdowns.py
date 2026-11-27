"""Source-backed latest-quarter disclosures for reports lacking business detail."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = {
    "AVGO": ("2026Q3", "百万美元", [("半导体解决方案", "20,839", "—"), ("基础设施软件", "8,752", "—"), ("其中：AI 半导体（包含在半导体解决方案中）", "约 16,700", "—")], "AI 行是半导体解决方案的子集，不重复加总；公司未披露这两个业务的季度营业利润。", "https://investors.broadcom.com/news-releases/news-release-details/broadcom-inc-announces-third-quarter-fiscal-year-2026-financial"),
    "SMSN": ("2026Q3", "万亿韩元", [("设备解决方案 DS", "147.1", "106.5"), ("三星显示 SDC", "8.0", "1.1"), ("设备体验 DX", "未列绝对额", "-0.8"), ("其中：视觉显示与家电（DX 子集）", "13.9", "-0.2")], "分部之间存在内部交易；已披露行不可直接相加为集团收入或利润。", "https://news.samsung.com/global/samsung-electronics-announces-third-quarter-2026-results"),
    "CRWV": ("2026Q3", "百万美元", [("AI 云平台（单一报告分部）", "3,661", "207")], "公司没有披露可加总的产品/客户业务利润。早于上市披露的季度资料不完整，图中空白季度不作推算。", "https://investors.coreweave.com/financials/quarterly-results/"),
    "WDC": ("2026Q4", "百万美元", [("云 Cloud", "3,868", "—"), ("客户端 Client", "320", "—"), ("消费级 Consumer", "193", "—")], "按终端市场拆分，合计 4,381；公司未按这些类别披露季度营业利润。", "https://investor.wdc.com/static-files/3d436529-f9fb-4ab0-8d2a-cdee0e84e703"),
    "STX": ("2026Q4", "百万美元", [("存储业务（公司合并口径）", "4,233", "约 2,064")], "本季财报未提供可核对的云/企业/消费业务收入及营业利润分项；合并利润按 GAAP 营业利润率 48.8% 显示。", "https://investors.seagate.com/news/news-details/2026/Seagate-Technology-Reports-Fiscal-First-Quarter-2027-Financial-Results/default.aspx"),
    "AMAT": ("2026Q3", "百万美元", [("半导体系统", "7,040", "2,657"), ("应用全球服务", "1,781", "536"), ("其他（含显示业务）", "294", "-118")], "GAAP 分部营业利润；三项收入合计 9,115，营业利润合计 3,075。", "https://ir.appliedmaterials.com/news-releases/news-release-details/applied-materials-announces-third-quarter-2026-results"),
    "CSCO": ("2026Q4", "百万美元", [("网络", "11,132", "—"), ("安全", "2,120", "—"), ("协作", "1,136", "—"), ("可观测性", "279", "—"), ("服务", "3,850", "—")], "产品及服务收入合计 18,517；公司未按这些产品类别披露营业利润。", "https://investor.cisco.com/news/news-details/2026/CISCO-REPORTS-FIRST-QUARTER-EARNINGS/default.aspx"),
    "LRCX": ("2026Q3", "百万美元", [("设备系统", "5,732.907", "—"), ("客户支持及其他", "2,486.511", "—")], "两类收入合计 8,219.418；公司未按两类业务披露营业利润。", "https://investor.lamresearch.com/2026-10-21-Lam-Research-Corporation-Reports-Financial-Results-for-the-Quarter-Ended-September-27%2C-2026"),
    "ASML": ("2026Q3", "百万欧元", [("安装基础管理／服务及现场升级", "3,289", "—"), ("集团总收入（含光刻系统）", "11,662", "—")], "安装基础管理收入包含在集团总收入中；此处不按差额推算系统销售额或分部利润。", "https://investor.asml.com/news-releases/news-release-details/asml-reports-eu11.7-billion-total-net-sales-and-eu5.0-billion-net-income-q3-2026"),
    "AAPL": ("2026Q3", "百万美元", [("iPhone", "57,583", "—"), ("Mac", "10,792", "—"), ("iPad", "6,229", "—"), ("可穿戴、家居与配件", "8,300", "—"), ("服务", "31,573", "23,980")], "五类收入合计 114,477。服务栏为毛利润＝收入－销售成本；公司未披露这些产品类别的营业利润。", "https://www.apple.com/newsroom/pdfs/fy2026q4/FY26_Q4_Consolidated_Financial_Statements.pdf"),
    "TSLA": ("2026Q3", "百万美元", [("汽车", "20,560", "—"), ("能源生产及储能", "2,881", "—"), ("服务及其他", "4,605", "—")], "三类收入合计 28,046；公司未按这三个收入类别披露营业利润。", "https://ir.tesla.com/_flysystem/s3/sec/000162828026066738/tsla-20261021-gen.pdf"),
}

for ticker, (period, unit, rows, note, url) in DATA.items():
    payload = {"period": period, "unit": unit, "profit_label": "营业利润／注明时为毛利润", "rows": [dict(name=n, revenue=r, profit=p) for n, r, p in rows], "note": note, "source_url": url}
    path = ROOT / "database" / ticker / "html-research" / "data" / "business-breakdown.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(ticker, path)
