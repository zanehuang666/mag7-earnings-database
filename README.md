# Mag 7 Earnings Database

这是第一梯队财报日历试用版的独立公开副本。`index.html` 和 `calendar.html` 是展示入口，`reports/<ticker>/overview.html` 保留现有公司研究页面；`database/<ticker>/` 是按公司划分的可下载文件库。[打开网页](https://zanehuang666.github.io/mag7-earnings-database/)；[浏览全部文件](https://github.com/zanehuang666/mag7-earnings-database)。原仓库未被修改。

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

`analysis-prompt.placeholder.md` 只标识待提供的写作要求；已有研究稿和资料索引按原状态保存，不自动提升为已核实报告。`data/report_index.json` 记录公司 HTML 的研究状态，`data/research_index.json` 记录季度内容路径。新仓库公开发布前应检查资料中是否包含不宜公开的内容。

GitHub Pages 从本仓库根目录的页面、索引、报告和 `database/` 组装站点。`sync-data.yml` 复用原项目的 Mag 7 日历、行情、宏观和 Microsoft 研究自动更新；第一梯队扩展公司的逐季资料包与公司 HTML 当前仍为保留的静态研究快照，后续研究需依照各公司 skill 单独复核更新。Paratera 凭证仅配置为 Actions Secrets，绝不放入仓库文件；`check-paratera.yml` 提供手动连通性检查。
