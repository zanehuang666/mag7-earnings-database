"""Turn a sourced five-file company bundle into the fixed report chart model."""
from collections import defaultdict
from datetime import date

CHARTS = [
    ("g1", "01｜集团总收入及业务构成", "stack"),
    ("g2", "02｜传统业务收入及产品结构", "stack"),
    ("g3", "03｜传统业务利润", "profit"),
    ("g4", "04｜传统业务利润率", "line"),
    ("g5", "05｜AI 相关产品／业务代理收入", "stack"),
    ("g6", "06｜AI 相关业务利润", "profit"),
    ("g7", "07｜AI 相关业务利润率", "line"),
    ("g8", "08｜经营现金流", "bar"),
    ("g9", "09｜现金资本开支 CapEx", "bar"),
    ("g10", "10｜年度资本开支与管理层指引", "annual"),
    ("g11", "11｜经营现金流－CapEx＝自由现金流", "bridge"),
]


def _number(fact):
    v = fact.get("value")
    return v if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def _display(fact, divisor):
    v = _number(fact)
    if v is None:
        return None
    scale = str(fact.get("scale_original") or fact.get("unit_original") or "million").lower()
    if scale in ("billion", "十亿"):
        return v * 10 / divisor * 100
    if scale in ("thousand", "千"):
        return v / 1000 / divisor
    if scale in ("unit", "percent", "%", "ratio"):
        return v
    return v / divisor


def build_model(bundle, metadata):
    periods = sorted((p for p in bundle["periods"] if p.get("status") != "pre_release"), key=lambda p: (p["fiscal_year"], p["fiscal_quarter"]))
    if metadata.get("research_status") == "diagnostic" and not metadata.get("preserve_full_axis"):
        evidenced = {f["period_id"] for f in bundle["facts"] if f.get("period_type") == "quarter" and f.get("metric_id") == "consolidated_revenue" and _number(f) is not None}
        periods = [p for p in periods if p["period_id"] in evidenced]
    if not periods:
        raise ValueError("no reported periods")
    quarters = [p["period_id"] for p in periods]
    positions = {q: i for i, q in enumerate(quarters)}
    breakpoints = sorted({p["period_id"] for p in periods if p.get("comparability_events")} |
                         {c["valid_from_period_id"] for c in bundle["classification"] if c.get("break_from_previous") and c.get("valid_from_period_id") in positions},
                         key=lambda q: positions[q])
    source_by_id = {s["source_id"]: s for s in bundle["sources"]}
    fact_by_id = {f["fact_id"]: f for f in bundle["facts"]}
    candidates = [f for f in bundle["facts"] if f.get("period_type") == "quarter" and f.get("period_id") in positions]
    groups = defaultdict(list)
    for f in candidates:
        groups[(f.get("period_id"), f.get("metric_id"), f.get("entity_id"))].append(f)
    facts = [next((f for f in group if f.get("display_selected") is True), group[-1]) for group in groups.values()]
    facts_by_period = defaultdict(list)
    for f in facts:
        facts_by_period[f["period_id"]].append(f)
    classifications = bundle["classification"]
    divisor = metadata.get("display_divisor", 100)
    currency = metadata.get("currency") or next((f.get("currency") for f in facts if f.get("currency")), "USD")
    unit = metadata.get("display_unit") or ("亿元" if currency == "CNY" else "亿美元" if currency == "USD" else f"亿{currency}")

    def guidance_value(value, original_unit):
        if not isinstance(value, (int, float)):
            return None
        source_unit = str(original_unit or "million").lower()
        if source_unit == unit.lower():
            return value
        if source_unit in ("billion", "usd billion", "十亿美元"):
            return value * 10 if divisor == 100 else value * 1000 / divisor
        if source_unit in ("%", "percent"):
            return value
        return value / divisor

    def classification(entity, quarter):
        i = positions[quarter]
        matches = [c for c in classifications if c.get("entity_id") == entity and
                   positions.get(c.get("valid_from_period_id"), -1) <= i <= positions.get(c.get("valid_to_period_id"), len(quarters) - 1)]
        return matches[-1] if matches else None

    def side(f, q):
        proxy_side = (f.get("profit_proxy") or {}).get("placement_side")
        if proxy_side in ("traditional", "ai"):
            return proxy_side
        c = classification(f.get("entity_id"), q)
        return (c or {}).get("side") or f.get("side")

    def label(f, q):
        c = classification(f.get("entity_id"), q)
        return f.get("original_metric_name") if f.get("metric_id") in ("revenue_adjustment", "corporate_adjustment", "ai_revenue", "traditional_revenue") and f.get("original_metric_name") else (c or {}).get("official_name") or f.get("entity_id", "未命名")

    def one(q, metric, entity="group"):
        matches = [f for f in facts_by_period[q] if f.get("metric_id") == metric and f.get("entity_id", "group") == entity and _number(f) is not None]
        return matches[-1] if len(matches) == 1 else None

    def total(q, metric):
        f = one(q, metric)
        return _display(f, divisor) if f else None

    series = {cid: {} for cid, _, _ in CHARTS}
    sources_used = {cid: set() for cid, _, _ in CHARTS}
    sources_used.update({"progressTradChart": set(), "progressAiChart": set()})

    def add(cid, f, q, value=None, name=None, suffix=None):
        classified_side = side(f, q)
        key = f.get("entity_id", "group") + (suffix or ("__" + classified_side if cid in ("g1","g2","g3","g5","g6") and classified_side else ""))
        display_name = name or label(f, q)
        if (f.get("profit_proxy") or {}).get("is_proxy"):
            display_name += "（已批准代理）"
        row = series[cid].setdefault(key, {"key": key, "name": display_name, "side": classified_side, "values": [None] * len(quarters), "evidence":[None]*len(quarters), "source_ids": set(), "unit": unit})
        row["values"][positions[q]] = _display(f, divisor) if value is None else value
        row["evidence"][positions[q]] = {"source_id":f.get("source_id"),"locator":f.get("locator"),"fact_id":f.get("fact_id")}
        evidence_facts = [f] + [fact_by_id[ref] for ref in (f.get("derivation") or {}).get("input_fact_ids",[]) if ref in fact_by_id]
        for evidence_fact in evidence_facts:
            sid = evidence_fact.get("source_id")
            if sid in source_by_id:
                row["source_ids"].add(sid)
                sources_used[cid].add(sid)

    segment_metrics = {"reported_segment_revenue", "segment_revenue", "platform_revenue", "business_unit_revenue"}
    product_metrics = {"product_revenue", "service_revenue", "channel_revenue"}
    profit_metrics = {"operating_profit", "segment_profit", "segment_operating_profit"}
    for q in quarters:
        rows = facts_by_period[q]
        segments = [f for f in rows if f.get("metric_id") in segment_metrics and _number(f) is not None and (f.get("external_revenue_scope") != "includes_intersegment" or f.get("display_gross_with_elimination") is True)]
        products = [f for f in rows if f.get("metric_id") in product_metrics and _number(f) is not None and f.get("external_revenue_scope") != "includes_intersegment"]
        adjustments = [f for f in rows if f.get("metric_id") == "revenue_adjustment" and _number(f) is not None]
        for f in segments + adjustments:
            add("g1", f, q)
        if not segments and not adjustments:
            proxies = [one(q, metric) for metric in ("traditional_revenue", "ai_revenue")]
            if all(proxies):
                for f in proxies:
                    add("g1", f, q, suffix="__proxy")
            else:
                group_revenue = one(q, "consolidated_revenue")
                if group_revenue:
                    add("g1", group_revenue, q, name="集团总收入（构成待核）", suffix="__group_total")
        for s, cid in (("traditional", "g2"), ("ai", "g5")):
            expected = total(q, "traditional_revenue" if s == "traditional" else "ai_revenue")
            adjustment_rows = [f for f in adjustments if side(f, q) in (s, "adjustment") and s == "traditional"]
            chosen = []
            for parent in (f for f in segments if side(f, q) == s):
                children = [f for f in products if f.get("parent_entity_id") == parent.get("entity_id") and side(f, q) == s]
                complete = bool(children) and all(f.get("is_exhaustive_child_set") is True for f in children)
                matched = complete and abs(sum(_display(f, divisor) for f in children) - _display(parent, divisor)) < max(.02, abs(_display(parent, divisor)) * .0001)
                chosen.extend(children if matched else [parent])
            for parent in (f for f in segments if side(f, q) not in ("traditional", "ai")):
                chosen.extend(f for f in products if f.get("parent_entity_id") == parent.get("entity_id") and side(f, q) == s)
            if s == "traditional" and not chosen and expected is not None and total(q,"consolidated_revenue") == expected:
                chosen = [f for f in segments if side(f,q) not in ("ai",)]
            if expected is not None and abs(sum(_display(f, divisor) for f in chosen + adjustment_rows) - expected) > max(.02, abs(expected) * .0001):
                chosen = [f for f in segments if side(f, q) == s]
            if not chosen and not adjustment_rows and expected is not None:
                aggregate = one(q, "traditional_revenue" if s == "traditional" else "ai_revenue")
                if aggregate:
                    chosen = [aggregate]
            for f in chosen + adjustment_rows:
                add(cid, f, q)
        if metadata.get('group_only_profit'):
            group_profit = one(q, metadata.get('group_profit_metric', 'consolidated_operating_profit'))
            group_revenue = one(q, 'consolidated_revenue')
            if group_profit:
                add('g3', group_profit, q, name=metadata.get('group_profit_label', '集团营业利润'), suffix='__group')
                if group_revenue and _number(group_revenue):
                    add('g4', group_profit, q, value=_number(group_profit) / _number(group_revenue) * 100,
                        name=metadata.get('group_profit_label', '集团营业利润') + '率', suffix='__group_margin')
                    series['g4']['group__group_margin']['unit'] = '%'
                    if group_revenue.get('source_id') in source_by_id:
                        series['g4']['group__group_margin']['source_ids'].add(group_revenue['source_id'])
                        sources_used['g4'].add(group_revenue['source_id'])
        profit_rows = [f for f in rows if (f.get("metric_id") in profit_metrics | {"corporate_adjustment"} or
                       (f.get("metric_id") == "consolidated_operating_profit" and (f.get("profit_proxy") or {}).get("is_proxy"))) and _number(f) is not None]
        for f in profit_rows:
            s = "traditional" if f.get("metric_id") == "corporate_adjustment" else side(f, q)
            if s not in ("traditional", "ai"):
                continue
            cid, mid = ("g3", "g4") if s == "traditional" else ("g6", "g7")
            add(cid, f, q)
            rev = next((r for r in segments + products if r.get("entity_id") == f.get("entity_id") and _number(r) not in (None, 0)), None)
            if rev:
                pct = _number(f) / _number(rev) * 100
                add(mid, f, q, value=pct, name=label(f, q), suffix="__margin")
                margin_row = series[mid][f["entity_id"] + "__margin"]
                margin_row["unit"] = "%"
                margin_row["evidence"][positions[q]]["locator"] = f'利润 {f.get("fact_id")} ÷ 收入 {rev.get("fact_id")}'
                if rev.get("source_id") in source_by_id:
                    margin_row["source_ids"].add(rev["source_id"])
                    sources_used[mid].add(rev["source_id"])
        for f in rows:
            if f.get("metric_id") != "segment_operating_margin" or _number(f) is None:
                continue
            if any(p.get("entity_id") == f.get("entity_id") for p in profit_rows):
                continue
            s = side(f,q)
            if s not in ("traditional", "ai"):
                continue
            cid = "g4" if s == "traditional" else "g7"
            add(cid,f,q,value=_number(f),name=label(f,q)+"（公司披露）",suffix="__reported_margin")
            series[cid][f["entity_id"]+"__reported_margin"]["unit"] = "%"
        for metric, cid in (("ocf", "g8"), ("cash_capex", "g9"), ("ocf", "g11"), ("cash_capex", "g11"), ("derived_fcf", "g11")):
            f = one(q, metric)
            if f:
                add(cid, f, q, name={"ocf":"经营现金流", "cash_capex":"现金 CapEx", "derived_fcf":"自由现金流"}[metric], suffix="__" + metric)
                if metric == "cash_capex" and f.get("source_id") in source_by_id:
                    sources_used["g10"].add(f["source_id"])

    for cid in ("g4", "g7"):
        side_name = "traditional" if cid == "g4" else "ai"
        for q in quarters:
            revenue = total(q, "traditional_revenue" if side_name == "traditional" else "ai_revenue")
            pseries = series["g3" if cid == "g4" else "g6"]
            profits = [s["values"][positions[q]] for s in pseries.values() if s["values"][positions[q]] is not None]
            expected = {f.get("entity_id") for f in facts_by_period[q] if f.get("metric_id") in segment_metrics and side(f,q)==side_name and _number(f) is not None}
            disclosed = {f.get("entity_id") for f in facts_by_period[q] if f.get("metric_id") in profit_metrics and _number(f) is not None}
            if revenue not in (None, 0) and profits and len(expected)>1 and expected.issubset(disclosed):
                key = "__combined_margin"
                row = series[cid].setdefault(key, {"key":key, "name":"已披露分部综合利润率", "side":side_name, "values":[None]*len(quarters), "evidence":[None]*len(quarters), "source_ids":set(), "unit":"%"})
                row["values"][positions[q]] = sum(profits) / revenue * 100
                row["evidence"][positions[q]] = {"source_id":None,"locator":"由当期分部利润与收入计算","fact_id":None}

    for cid, metric in (("progressTradChart", "traditional"), ("progressAiChart", "ai")):
        series[cid] = {}
        candidates = [f for f in facts if (f.get("chart_slot") == cid or f.get("chart_slot") == metric + "_progress") and _number(f) is not None]
        by_key = defaultdict(dict)
        for f in candidates:
            by_key[(f.get("entity_id"), f.get("metric_id"), f.get("definition_version"))][f["period_id"]] = f
        for key, values in by_key.items():
            if not all(q in values for q in quarters[-8:]) and not any(v.get("approval_decision_id") for v in values.values()):
                continue
            f = next(iter(values.values()))
            row = {"key":"|".join(str(v) for v in key), "name":f'{f.get("entity_id")}｜{f.get("original_metric_name") or f.get("metric_id")}', "side":metric,
                   "values":[_number(values[q]) if q in values else None for q in quarters],
                   "evidence":[{"source_id":values[q].get("source_id"),"locator":values[q].get("locator"),"fact_id":values[q].get("fact_id")} if q in values else None for q in quarters],
                   "source_ids":{v["source_id"] for v in values.values() if v.get("source_id") in source_by_id}, "unit":f.get("unit_original") or "%"}
            series[cid][row["key"]] = row
            sources_used[cid].update(row["source_ids"])

    annual = defaultdict(lambda: {"actual":None, "events":[]})
    for p in periods:
        q = p["period_id"]
        capex = total(q, "cash_capex")
        if capex is not None:
            year = str(p["fiscal_year"])
            annual[year].setdefault("quarters", set()).add(q)
            annual[year]["actual"] = (annual[year]["actual"] or 0) + capex
    for year, value in annual.items():
        if len(value.get("quarters", set())) != 4:
            value["actual"] = None
        value.pop("quarters", None)
    for g in bundle["guidance"]:
        if g.get("metric_id") not in ("annual_capex", "annual_capex_guidance"):
            continue
        if not g.get("source_id") in source_by_id or source_by_id[g["source_id"]].get("is_company_official") is not True or not g.get("locator"):
            continue
        target = str(g.get("target_period_id", "")).replace("FY", "")[:4]
        if not target.isdigit():
            continue
        event = {"issued_at":g.get("issued_at"), "value":guidance_value(g.get("point"), g.get("unit")),
                 "low":guidance_value(g.get("low"), g.get("unit")), "high":guidance_value(g.get("high"), g.get("unit")),
                 "unit":g.get("unit") or unit, "note":g.get("wording_basis_note"), "wording":g.get("original_wording"),
                 "source_id":g.get("source_id"), "comparable":g.get("comparability_status") not in ("wording_unclear", "incomparable")}
        annual[target]["events"].append(event)
        sources_used["g10"].add(g["source_id"])
    for value in annual.values():
        value["events"].sort(key=lambda e: e.get("issued_at") or "")

    guide = None
    next_guides = [g for g in bundle["guidance"] if g.get("metric_id") == "consolidated_revenue" and g.get("target_period_id") not in positions]
    if next_guides:
        g = sorted(next_guides, key=lambda x: x.get("issued_at", ""))[-1]
        guide = {"target":g.get("target_period_id"),
                 "low":guidance_value(g.get("converted_low") if g.get("display_mode") == "converted_amount" else g.get("low"), g.get("converted_unit", "million") if g.get("display_mode") == "converted_amount" else g.get("unit")),
                 "high":guidance_value(g.get("converted_high") if g.get("display_mode") == "converted_amount" else g.get("high"), g.get("converted_unit", "million") if g.get("display_mode") == "converted_amount" else g.get("unit")),
                 "point":guidance_value(g.get("point"), g.get("unit")), "unit":"%" if g.get("display_mode") == "original_percent_band" else unit,
                 "source_id":g.get("source_id")}
        if g.get("source_id") in source_by_id:
            sources_used["g1"].add(g["source_id"])

    profit_names = {f.get('original_metric_name') for f in facts if f.get('metric_id') == 'segment_profit' and _number(f) is not None}
    profit_name = next(iter(profit_names)) if len(profit_names) == 1 else None
    chart_rows = []
    group_only_profit = any(row.get("key") == "group__group" for row in series["g3"].values())
    for cid, title, kind in CHARTS:
        if metadata.get('cash_flow_scope') == 'continuing_operations':
            if cid == 'g8': title = '08｜持续经营业务经营现金流'
            if cid == 'g11': title = '11｜持续经营 OCF－现金 CapEx＝研究自由现金流'
        if group_only_profit and cid == "g3":
            title = '03｜' + metadata.get('group_profit_label', '集团营业利润') + '（未按业务拆分）'
        if group_only_profit and cid == "g4":
            title = '04｜' + metadata.get('group_profit_label', '集团营业利润') + '率（未按业务拆分）'
        if profit_name and profit_name.lower() not in ('operating income', 'operating profit'):
            if cid in ('g3', 'g6'):
                title = title.replace('利润', profit_name)
            elif cid in ('g4', 'g7'):
                title = title.replace('利润率', profit_name + ' 率')
        if metadata.get('profit_chart_label') and cid in ('g3','g4','g6','g7'):
            side = '传统业务' if cid in ('g3','g4') else 'AI 相关业务'
            title = f'{cid[1:].zfill(2)}｜{side}{metadata["profit_chart_label"]}' + ('率' if cid in ('g4','g7') else '')
        rows = list(series[cid].values())
        for row in rows:
            row["source_ids"] = sorted(row["source_ids"])
        chart_rows.append({"id":cid,"title":title,"type":kind,"series":rows,"source_ids":sorted(sources_used[cid]),"unit":"%" if cid in ("g4","g7") else unit})
    for cid in ("progressTradChart", "progressAiChart"):
        for row in series[cid].values():
            row["source_ids"] = sorted(row["source_ids"])

    last = quarters[-1]
    prior = quarters[-5] if len(quarters) >= 5 else None
    kpi_specs = [("集团收入","consolidated_revenue"),("传统业务收入","traditional_revenue"),("AI 相关收入代理","ai_revenue"),
                 ("AI 代理业务利润率",None),("经营现金流","ocf"),("自由现金流","derived_fcf")]
    kpis = []
    for name, metric in kpi_specs:
        if metric:
            value = total(last, metric)
            old = total(prior, metric) if prior else None
            display_unit = unit
        else:
            ai = total(last, "ai_revenue")
            vals = [s["values"][-1] for s in series["g6"].values() if s["values"][-1] is not None]
            value = sum(vals) / ai * 100 if ai not in (None,0) and vals else None
            old = None
            display_unit = "%"
        change = (value / old - 1) * 100 if old not in (None,0) and value is not None else None
        kpis.append({"name":name,"value":value,"unit":display_unit,"yoy":change,"prior":old})

    source_list = [{"id":s["source_id"],"title":s.get("title") or s["source_id"],"url":s.get("url"),"published_at":s.get("published_at")}
                   for s in bundle["sources"] if s.get("is_company_official") or s.get("third_party_approval_id") or s.get("is_review_fixture")]
    return {"company_name":metadata.get("company_name") or bundle["sources"][0].get("publisher", "公司"),
            "quarters":quarters,"last_quarter":last,"currency":currency,"unit":unit,"charts":chart_rows,"progress":{
                "progressTradChart":list(series["progressTradChart"].values()), "progressAiChart":list(series["progressAiChart"].values())},
            "annual":{k:v for k,v in sorted(annual.items())},"guide":guide,"kpis":kpis,"sources":source_list,"breakpoints":breakpoints,
            "research_status":metadata.get("research_status") or "needs_source_review", "group_only_profit":group_only_profit,
            "preserve_full_axis":bool(metadata.get("preserve_full_axis")),
            "chart_context_notes":metadata.get("chart_context_notes") or {},
            "return_href":metadata.get("return_href") or "#source","traditional_intro":metadata.get("traditional_intro") or "按公司正式披露的传统业务及产品收入列示。",
            "ai_intro":metadata.get("ai_intro") or "AI 相关业务只按已核实的产品或终端市场代理口径列示；代理收入不等于纯 AI 收入。"}
