# HTML 报告更新流程

公开日历：[网页](https://zanehuang666.github.io/mag7-earnings-database/calendar.html)。报告、五类数据和原始来源都放在 `database/<公司>/html-research/`；季度 Preview／Analysis 放在同公司 `earnings/<季度>/`。

## 定时执行

`.github/workflows/sync-data.yml` 在工作日每天两次、周末每天一次检查快照，依次执行：

1. 从 SEC 及公司官网发现已发布财报，保存原件链接、日期和可核查资料包。2021—2024 年 SEC 摘要存入 `html-research/materials/official-filings/`，2025 年以来的季度资料存入 `earnings/`。
2. 通过 `research-tools/generate_budgeted.py` 生成季度 Markdown 草稿；费用计入 `data/generation_budget_2025_2026.json`，达到 ¥40 累计估算上限前停止调用。资料稀疏时生成“资料有限”草稿，不耗模型费用。已有自动稿记录来源指纹和文件哈希；来源变化时旧版进入 `analysis/history/`，人工稿或被人工修改的文件不会自动覆盖。
3. 运行 `research-tools/build_diagnostic_html.py`。只有带 `auto_generated_from_official_packets` 标记、且页面哈希未被人工修改的诊断报告才会自动重建。新增资料无变化时跳过。报告以五类 JSON 和单文件 HTML 保存，模板运行器在 `research-tools/report-renderer/`。
4. 重建 `data/library_index.json`、`data/html_coverage.json` 和 `data/html_update_queue.json`，网页从索引显示现行报告、自动候选稿、原始 Markdown 与更新状态。

## 资料与验收边界

诊断 HTML 仅绘制官方原件中能定位的集团季度数据。10-K 全年值不会当作第四季度单季值；公司财年与日历季度分别标注。分部收入、产品量价、指引及公司自定义自由现金流缺乏逐季证据时留空。诊断页不得标记为 `verified`。

已有人工研究页保持原版。新官方资料尚未映射到原页面时，`html_update_queue.json` 标记 `needs_source_mapping`；人工补齐分部与产品的来源、五类 JSON 和浏览器验收后再采用新版本。SanDisk 的自动资料候选稿保存在 `database/SNDK/html-research/output/auto-update-candidate.html`，不覆盖原页面。

自动任务运行成功只能证明脚本和静态检查通过。浏览器图表、移动端布局和逐值来源仍要单独核验；用户可在网页的 HTML 覆盖状态和更新队列查看当前缺口。
