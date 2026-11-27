import argparse, json, sys
from pathlib import Path

KINDS = ('sources','periods','facts','classification','guidance')
MISSING = {'not_disclosed','not_found','not_applicable','incomparable','pending_filing'}

def load_bundle(directory):
    data = {}
    for kind in KINDS:
        path = directory / f'{kind}.json'
        payload = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(payload.get('records'), list): raise ValueError(f'{path}: records must be array')
        data[kind] = payload['records']
    return data

def validate(data, allow_review_sources=False):
    errors, warnings = [], []
    ids = {kind: set() for kind in KINDS}
    key = {'sources':'source_id','periods':'period_id','facts':'fact_id','classification':'classification_id','guidance':'guidance_id'}
    for kind, rows in data.items():
        for row in rows:
            rid = row.get(key[kind])
            if not rid or rid in ids[kind]: errors.append(f'{kind}: missing/duplicate {key[kind]} {rid}')
            ids[kind].add(rid)
    for s in data['sources']:
        if s.get('is_company_official') is True and s.get('publisher') != 'fixture' and not str(s.get('url','')).startswith(('https://','http://')):
            errors.append(f'SRC-01 {s.get("source_id")}: official source URL must be http(s)')
    periods = data['periods']
    if not periods: errors.append('TIME-01: periods empty')
    else:
        first_period = min((p.get('fiscal_year',9999),p.get('fiscal_quarter',9)) for p in periods)
        if first_period > (2021,1): warnings.append('TIME-01: fiscal axis starts after FY2021Q1; check missing periods')
        fiscal = sorted((p for p in periods if isinstance(p.get('fiscal_year'),int) and isinstance(p.get('fiscal_quarter'),int)), key=lambda p:(p['fiscal_year'],p['fiscal_quarter']))
        for previous,current in zip(fiscal,fiscal[1:]):
            expected = (previous['fiscal_year']+1,1) if previous['fiscal_quarter']==4 else (previous['fiscal_year'],previous['fiscal_quarter']+1)
            if (current['fiscal_year'],current['fiscal_quarter']) != expected:
                errors.append(f'TIME-01 {current.get("period_id")}: fiscal quarter gap or duplicate after {previous.get("period_id")}')
    source_by_id = {s.get('source_id'): s for s in data['sources']}
    by_metric = {}
    display_candidates = {}
    for f in data['facts']:
        fid = f.get('fact_id')
        if f.get('period_id') not in ids['periods']: errors.append(f'TIME-01 {fid}: unknown period')
        status, value = f.get('value_status'), f.get('value')
        if status in MISSING and value is not None: errors.append(f'DATA-01 {fid}: missing status has value')
        if status not in MISSING and (not isinstance(value,(int,float)) or isinstance(value,bool)): errors.append(f'DATA-01 {fid}: numeric value required')
        if status not in MISSING and f.get('derivation') is None and (f.get('source_id') not in ids['sources'] or not f.get('locator')): errors.append(f'SRC-01 {fid}: original fact needs source and locator')
        source = source_by_id.get(f.get('source_id'))
        if status not in MISSING and f.get('derivation') is None and source and source.get('is_company_official') is not True and not (allow_review_sources and source.get('is_review_fixture') is True):
            is_progress = f.get('chart_slot') in ('traditional_progress','ai_progress','progressTradChart','progressAiChart')
            if not is_progress or not source.get('third_party_approval_id'):
                errors.append(f'SRC-03 {fid}: nonofficial fact lacks approved progress scope')
        if f.get('derivation'):
            for dep in f['derivation'].get('input_fact_ids',[]):
                if dep not in ids['facts']: errors.append(f'DATA-02 {fid}: unknown input {dep}')
        if f.get('profit_proxy',{}).get('is_proxy') and not f.get('approval_decision_id'): errors.append(f'PROFIT-03 {fid}: group proxy requires approval')
        display_key = (f.get('period_id'),f.get('period_type'),f.get('metric_id'),f.get('entity_id'))
        if status not in MISSING:
            display_candidates.setdefault(display_key, []).append(f)
        by_metric[(f.get('period_id'),f.get('metric_id'),f.get('entity_id'))] = f
    for key, candidates in display_candidates.items():
        if len(candidates)>1 and sum(f.get('display_selected') is True for f in candidates)!=1:
            errors.append(f'DATA-03 {key}: multiple numeric definitions require exactly one display_selected=true')
    display_facts = [next((f for f in candidates if f.get('display_selected') is True), candidates[-1]) for candidates in display_candidates.values()]
    qp_metrics = {'shipment_quantity','shipment_growth_yoy','shipment_growth_qoq','asp_absolute','asp_growth_yoy','asp_growth_qoq','implied_asp_growth_yoy','implied_asp_growth_qoq'}
    for f in display_facts:
        if f.get('metric_id') not in qp_metrics or f.get('value') is None:
            continue
        fid = f.get('fact_id')
        if not f.get('product_entity_id') or not f.get('measurement_unit') or not f.get('definition_version') or not f.get('original_wording'):
            errors.append(f'HW-QP-01 {fid}: product, unit, definition and original wording required')
        metric = f.get('metric_id','')
        expected_basis = 'yoy' if metric.endswith('_yoy') else 'qoq' if metric.endswith('_qoq') else None
        if expected_basis and f.get('comparison_basis') != expected_basis:
            errors.append(f'HW-QP-01 {fid}: comparison basis conflicts with metric')
        if metric.startswith('implied_asp_growth'):
            inputs = f.get('derivation',{}).get('input_fact_ids',[])
            if len(inputs) != 2:
                errors.append(f'HW-QP-02 {fid}: implied ASP needs revenue and quantity growth inputs')
            else:
                input_facts = [next((x for x in display_facts if x.get('fact_id')==id_),None) for id_ in inputs]
                if any(x is None or x.get('product_entity_id') != f.get('product_entity_id') or x.get('comparison_basis') != expected_basis or x.get('definition_version') != f.get('definition_version') or x.get('period_id') != f.get('period_id') for x in input_facts):
                    errors.append(f'HW-QP-02 {fid}: implied ASP inputs have incompatible product, period, basis or definition')
    for metrics, rule in (({'reported_segment_revenue','segment_revenue','platform_revenue','business_unit_revenue'},'REV-01'),
                          ({'operating_profit','segment_profit','segment_operating_profit'},'PROFIT-01')):
        seen = {}
        for f in display_facts:
            if f.get('metric_id') in metrics and f.get('period_type') == 'quarter':
                pair = (f.get('period_id'),f.get('entity_id'))
                if pair in seen:
                    errors.append(f'{rule} {pair}: overlapping displayed metrics {seen[pair]} and {f.get("metric_id")}')
                seen[pair] = f.get('metric_id')
    for g in data['guidance']:
        gid = g.get('guidance_id')
        source = source_by_id.get(g.get('source_id'))
        if source is None: errors.append(f'GUIDE-01 {gid}: source missing')
        elif source.get('is_company_official') is not True and not (allow_review_sources and source.get('is_review_fixture') is True): errors.append(f'GUIDE-01 {gid}: company guidance requires official source')
        if not g.get('locator') or not g.get('original_wording'): errors.append(f'GUIDE-01 {gid}: original wording and locator required')
        if g.get('guidance_kind') == 'range' and isinstance(g.get('low'),(int,float)) and isinstance(g.get('high'),(int,float)) and g['low'] > g['high']:
            errors.append(f'GUIDE-01 {gid}: low exceeds high')
        predecessor = g.get('revision_of_guidance_id')
        if predecessor and predecessor not in ids['guidance']: errors.append(f'GUIDE-01 {gid}: unknown revision predecessor')
        if g.get('comparability_status') == 'wording_unclear':
            if not g.get('wording_basis_note') or not g.get('display_approval_decision_id'):
                errors.append(f'GUIDE-04 {gid}: approved wording note and decision ID required')
            if g.get('hit_status') in ('hit','miss'):
                errors.append(f'GUIDE-04 {gid}: wording-unclear point cannot be scored against actual')
        if g.get('display_mode') == 'converted_amount' and (g.get('conversion_base_fact_id') not in ids['facts'] or g.get('converted_low') is None): errors.append(f'GUIDE-02 {g.get("guidance_id")}: conversion base/amount missing')
        if g.get('display_mode') == 'original_percent_band' and g.get('unit') != '%': errors.append(f'GUIDE-02 {g.get("guidance_id")}: percent unit required')
    for c in data['classification']:
        if c.get('source_id') not in ids['sources']: errors.append(f'CLASS-01 {c.get("classification_id")}: source missing')
        if c.get('side') not in {'traditional','ai','adjustment','unclassified'}: errors.append(f'CLASS-03 {c.get("classification_id")}: invalid side')
    for period in ids['periods']:
        def val(metric):
            xs=[f['value'] for f in display_facts if f.get('period_id')==period and f.get('metric_id')==metric and isinstance(f.get('value'),(int,float))]
            return xs[0] if len(xs)==1 else None
        group,ai,trad=val('consolidated_revenue'),val('ai_revenue'),val('traditional_revenue')
        if None not in (group,ai,trad) and abs(group-ai-trad)>max(.01,abs(group)*.0001): errors.append(f'CLASS-06 {period}: traditional + AI != group')
        segment_values=[f['value'] for f in display_facts if f.get('period_id')==period and f.get('period_type')=='quarter' and f.get('metric_id') in ('reported_segment_revenue','segment_revenue','platform_revenue','business_unit_revenue','revenue_adjustment') and (f.get('external_revenue_scope')!='includes_intersegment' or f.get('display_gross_with_elimination') is True) and isinstance(f.get('value'),(int,float))]
        if group is not None and segment_values and abs(sum(segment_values)-group)>max(.01,abs(group)*.0001):
            errors.append(f'REV-01 {period}: reportable segment revenue and adjustments != group')
        products=[f for f in display_facts if f.get('period_id')==period and f.get('period_type')=='quarter' and f.get('metric_id') in ('product_revenue','channel_revenue') and isinstance(f.get('value'),(int,float))]
        parents={f.get('parent_entity_id') for f in products if f.get('is_exhaustive_child_set') is True}
        for parent in parents:
            children=[f for f in products if f.get('parent_entity_id')==parent and f.get('is_exhaustive_child_set') is True]
            parent_facts=[f for f in display_facts if f.get('period_id')==period and f.get('entity_id')==parent and f.get('metric_id') in ('segment_revenue','reported_segment_revenue','platform_revenue','business_unit_revenue') and isinstance(f.get('value'),(int,float))]
            if len(parent_facts)==1 and abs(sum(f['value'] for f in children)-parent_facts[0]['value'])>max(.01,abs(parent_facts[0]['value'])*.0001):
                errors.append(f'HW-REV-02 {period} {parent}: exhaustive products do not equal parent revenue')
        operating_total=val('consolidated_operating_profit')
        profit_values=[f['value'] for f in display_facts if f.get('period_id')==period and f.get('period_type')=='quarter' and f.get('metric_id') in ('operating_profit','segment_profit','segment_operating_profit','corporate_adjustment') and isinstance(f.get('value'),(int,float))]
        proxies=[f for f in display_facts if f.get('period_id')==period and (f.get('profit_proxy') or {}).get('is_proxy') and f.get('metric_id')=='consolidated_operating_profit']
        if proxies and profit_values:
            errors.append(f'PROFIT-03 {period}: group proxy overlaps disclosed component profit')
        profit_complete = any(f.get('period_id')==period and f.get('profit_reconciliation_complete') is True for f in display_facts)
        if profit_complete and operating_total is not None and profit_values and abs(sum(profit_values)-operating_total)>max(.01,abs(operating_total)*.0001):
            errors.append(f'PROFIT-03 {period}: segment profit and adjustments != group operating profit')
        ocf,capex,fcf=val('ocf'),val('cash_capex'),val('derived_fcf')
        if None not in (ocf,capex,fcf) and abs(ocf-capex-fcf)>max(.01,abs(ocf)*.0001): errors.append(f'CASH-03 {period}: OCF - CapEx != FCF')
        reported_fcf=val('company_reported_fcf')
        if None not in (fcf,reported_fcf) and abs(fcf-reported_fcf)>max(.01,abs(fcf)*.0001):
            reported_fact=next((f for f in display_facts if f.get('period_id')==period and f.get('metric_id')=='company_reported_fcf'),None)
            if not reported_fact or not reported_fact.get('fcf_difference_note'):
                errors.append(f'CASH-04 {period}: company FCF differs from research FCF without explanation')
    return {'ok':not errors,'errors':errors,'warnings':warnings,'counts':{k:len(v) for k,v in data.items()}}

def main():
    ap=argparse.ArgumentParser();ap.add_argument('data_dir');ap.add_argument('--report');ap.add_argument('--review-fixture',action='store_true');args=ap.parse_args()
    try: report=validate(load_bundle(Path(args.data_dir)), allow_review_sources=args.review_fixture)
    except Exception as e: report={'ok':False,'errors':[str(e)],'warnings':[]}
    output=json.dumps(report,ensure_ascii=False,indent=2)
    if args.report: Path(args.report).write_text(output,encoding='utf-8')
    print(output);sys.exit(0 if report['ok'] else 1)
if __name__=='__main__': main()
