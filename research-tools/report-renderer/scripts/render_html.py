"""Render the fixed hardware report page using the generic chart model."""
import html
import json
from pathlib import Path
from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parents[1]


def esc(value):
    return html.escape(str(value if value is not None else ""), quote=True)


def render(model, output):
    master = ROOT / "assets" / "cloud-report-11-chart-master.html"
    css = BeautifulSoup(master.read_text(encoding="utf-8"), "html.parser").style.string
    css += "\n.report-main{min-width:0}.chart-card{min-width:0}.scroll{max-width:100%}.scroll svg{min-width:1190px}.chart-note{font-size:10px;color:#64748b;margin-top:4px}.source-line a{margin-right:9px}.annual-event{font-size:10px;margin:4px 0}.annual-event .warning{color:#a15b35;font-weight:700}.kpi-value{white-space:normal}.kpi-value strong{overflow-wrap:anywhere}\n"
    sources = {s["id"]: s for s in model["sources"]}

    def source_line(ids):
        parts = []
        for sid in ids:
            source = sources.get(sid)
            if not source:
                continue
            url = source.get("url") or ""
            if url.startswith(("https://", "http://")):
                parts.append(f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(source["title"])}</a>')
            else:
                parts.append(esc(source["title"]))
        return "来源：" + (" · ".join(parts) if parts else "本期未披露可绘数据")

    nav_entries = [("nav-l1", "income", "收入"), ("nav-l2", "traditional-income", "传统业务收入"),
                   ("nav-l3", "traditional-profit", "传统业务利润情况"), ("nav-l3", "traditional-progress", "传统业务商业进展"),
                   ("nav-l2", "ai-income", "AI业务收入"), ("nav-l3", "ai-profit", "AI业务利润情况"),
                   ("nav-l3", "ai-progress", "AI业务商业进展"), ("nav-l1", "cash", "现金流"),
                   ("nav-l2", "ocf", "经营现金流"), ("nav-l2", "capex", "资本开支"),
                   ("nav-l2", "fcf", "自由现金流"), ("nav-l1", "source", "数据口径与来源")]
    nav = '<nav class="side-nav"><div class="nav-title">目录</div>'
    nav += "".join(f'<a class="{level}" href="#{anchor}">{title}</a>' for level, anchor, title in nav_entries) + "</nav>"

    kpis = []
    for i, k in enumerate(model["kpis"]):
        css_class = "cloud" if i in (2, 3) else "cash" if i in (4, 5) else ""
        value = "—" if k["value"] is None else f'{k["value"]:,.2f}'
        if i == 5:
            compare = f'上年同期 {k["prior"]:,.2f} {k["unit"]}' if k["prior"] is not None else "上年同期未披露"
        else:
            compare = f'同比 {k["yoy"]:+.1f}%' if k["yoy"] is not None else "同比暂无同口径数据"
        kpis.append(f'<div class="kpi {css_class}" data-kpi="{i}"><div class="kpi-period">{esc(model["last_quarter"])}</div><div class="kpi-label">{esc(k["name"])}</div><div class="kpi-value"><strong>{value}</strong><span>{esc(k["unit"])}</span></div><div class="kpi-compare">{esc(compare)}</div></div>')
    charts = {c["id"]: c for c in model["charts"]}

    def card(cid):
        c = charts[cid]
        context_note = model.get('chart_context_notes',{}).get(cid)
        context_html = f'<p class="fine">{esc(context_note)}</p>' if context_note else ''
        return (f'<div id="{cid}" data-chart="{cid}" class="chart-card"><div class="chart-top"><h3>{esc(c["title"])}</h3><span>{esc(c["unit"])}</span></div>'
                f'<div class="scroll" data-plot></div><div class="legend" data-legend></div><div class="chart-note" data-note></div>'
                f'{context_html}'
                f'<div class="source-line">{source_line(c["source_ids"])}</div></div>')

    def progress(cid, anchor, title):
        ids = sorted({sid for row in model["progress"][cid] for sid in row["source_ids"]})
        context_note = model.get('chart_context_notes',{}).get(cid)
        context_html = f'<p class="fine">{esc(context_note)}</p>' if context_note else ''
        return (f'<section class="section" id="{anchor}"><div class="section-head"><h3>{esc(title)}</h3></div><div class="chart-card">'
                f'<div class="chart-top"><h3>产品量价进展｜季度增长与下降</h3><span>季度折线</span></div><div class="scroll" id="{cid}"></div>'
                f'<div class="legend" data-progress-legend="{cid}"></div>{context_html}<div class="source-line">{source_line(ids)}</div></div></section>')

    source_items = []
    for s in model["sources"]:
        url = s.get("url") or ""
        item = f'<a href="{esc(url)}" target="_blank" rel="noopener">{esc(s["title"])}</a>' if url.startswith(("http://", "https://")) else esc(s["title"])
        source_items.append(f'<p class="fine">{item}｜{esc(s.get("published_at"))}</p>')

    review_banner = '' if model['research_status'] == 'verified' else '<div class="note">本页为样本复现草稿；数据来源仍需逐值回到公司原文核对，不作正式财报结论。</div>' if model['research_status'] == 'sample_reproduction' else '<div class="note">本页为流程诊断草稿：图表仅展示已核实的季度，其他历史季度尚未完成研究；不得作为完整财报研究使用。</div>' if model['research_status'] == 'diagnostic' else '<div class="note">本页已建立 FY2021Q1 至最新季度的官方财务历史草稿；历史指引、量价及例外事项仍待核实，尚非最终完成版。</div>' if model['research_status'] == 'financial_history_draft' else '<div class="note">数据来源仍需逐值核对；本页为研究草稿，不作正式财报结论。</div>'
    traditional_profit_heading = '集团利润情况（未按业务拆分）' if model.get('group_only_profit') else '传统业务利润情况'
    body = (f'<div class="layout">{nav}<main class="report-main"><header class="top"><div><div class="eyebrow"><a href="{esc(model["return_href"])}">返回硬件厂商财报研究</a></div>'
            f'<h1>{esc(model["company_name"])} 财报研究</h1></div><div class="asof">截至 {esc(model["last_quarter"])}<br>{esc(model["quarters"][0])}—{esc(model["last_quarter"])}｜币种：{esc(model["currency"])}｜单位：{esc(model["unit"])}</div></header>'
            f'{review_banner}<div class="kpis">{"".join(kpis)}</div><section class="section" id="income"><div class="section-head"><h2>一、收入</h2></div>{card("g1")}'
            f'<h3 class="section-head group" id="traditional-income">传统业务收入</h3><div class="business-list"><p>{esc(model["traditional_intro"])}</p></div>{card("g2")}'
            f'<h3 class="section-head group" id="traditional-profit">{traditional_profit_heading}</h3>{card("g3")}{card("g4")}{progress("progressTradChart","traditional-progress","传统业务商业进展")}'
            f'<h3 class="section-head group" id="ai-income">AI业务收入</h3><p class="segment-intro">{esc(model["ai_intro"])}</p>{card("g5")}'
            f'<h3 class="section-head group" id="ai-profit">AI业务利润情况</h3>{card("g6")}{card("g7")}{progress("progressAiChart","ai-progress","AI业务商业进展")}</section>'
            f'<section class="section" id="cash"><div class="section-head"><h2>二、现金流</h2></div><div class="section-head" id="ocf"><h3>经营现金流</h3></div>{card("g8")}'
            f'<div class="section-head" id="capex"><h3>资本开支</h3></div>{card("g9")}{card("g10")}<div class="section-head" id="fcf"><h3>自由现金流</h3></div>{card("g11")}</section>'
            f'<section class="section" id="source"><div class="section-head"><h2>数据口径与来源</h2></div><div class="two"><div class="chart-card"><h3>财报原文</h3>{"".join(source_items)}</div>'
            '<div class="chart-card"><h3>计算说明</h3><p class="fine">AI 代理可证实时，传统收入＋AI 代理收入＝集团收入。产品收入使用最细可加总披露层级；利润使用最细可得正式利润层级，保留历史分部名称。含内部交易的分部收入不进入集团堆叠。</p>'
            '<p class="fine">自由现金流＝经营现金流－图示现金 CapEx。无数据的图卡保留并注明原因。各卡来源与原始定义以公司披露为准。</p></div></div></section></main></div><div id="tip"></div>')
    payload = json.dumps(model, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    runtime = (ROOT / "assets" / "report-runtime.js").read_text(encoding="utf-8")
    content = f'<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(model["company_name"])} 财报研究</title><style>{css}</style></head><body>{body}<script>window.REPORT_DATA={payload};\n{runtime}</script></body></html>'
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(content, encoding="utf-8")
