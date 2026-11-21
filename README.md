# Mag 7 Earnings Database

这是第一梯队财报日历试用版的独立公开副本。`index.html` 和 `calendar.html` 是展示入口，`reports/<ticker>/overview.html` 保留现有公司研究页面；`database/<ticker>/` 是按公司划分的可下载文件库。[打开网页](https://zanehuang666.github.io/mag7-earnings-database/)；[按公司浏览文件](DATABASE_INDEX.md)。原仓库未被修改。

[第一梯队 2025 与第二梯队 2026 季度研究目录](RESEARCH_EXPANSION_INDEX.md)列出 Preview、Analysis 和可读原始资料。模型生成文案需人工核查，预算记录保存在 `data/generation_budget_2025_2026.json`。

## 文件结构

```text
database/<ticker>/
  html-research/data/      # 云厂商或硬件 skill 的五类 JSON 与报告视图
  html-research/checks/    # 已有静态检查文件（如有）
  earnings/<YYYYQn>/
    event.json             # 本次财报日期和研究阶段状态
    materials/             # 本次财报资料包
    analysis/              # 已有 Preview / Analysis、元数据和待提供的 prompt 占位
reports/<ticker>/overview.html  # 现有 HTML 展示
data/                          # 日历与网页索引
```

`data/report_index.json` 记录公司 HTML 的研究状态，`data/research_index.json` 记录季度文章状态。逐季自动稿按 [写作要求](research-tools/quarterly-research.txt) 生成，英文中间稿、读者互检及事实核查存入同目录的 `*.checks.json`；旧稿存入 `history/`，人工稿不被自动任务覆盖。`generated_review_pending` 只表示有待审草稿，不等于来源逐值核实完成。`analysis-prompt.placeholder.md` 是先前的占位文件，正式要求以写作要求文件为准。

GitHub Pages 从本仓库根目录的页面、索引、报告和 `database/` 组装站点。`sync-data.yml` 复用原项目的 Mag 7 日历、行情、宏观和 Microsoft 研究自动更新；公司长期 HTML 与逐季资料包仍需按各公司 skill 复核更新。逐季文章生成工作流只允许手动触发，没有定时发送资料包。Paratera 凭证仅配置为 Actions Secrets，不写入仓库文件。
