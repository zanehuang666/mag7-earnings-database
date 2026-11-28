/* EPS markers come from the per-quarter database JSON files. */
let EPS_CHART = [];
fetch('./data/eps_chart_markers.json', {cache:'no-store'}).then(r=>r.json()).then(d=>{EPS_CHART=d.records||[];if(MARKET)renderMarketChart()});

function renderMarketChart(){
  if(!MARKET||!DATA)return;
  const box=$('marketChart'),series=MARKET.series||{},qqq=series.QQQ;
  if(!qqq||qqq.points.length<2){box.innerHTML='<span class="muted">暂无行情快照</span>';return}
  const colors={QQQ:'#173f59',MSFT:'#268f74',AAPL:'#636b75',GOOGL:'#d29a24',AMZN:'#d26b36',NVDA:'#7756a8',META:'#2879a8',TSLA:'#b44949'};
  const focus=series[selectedTicker]?selectedTicker:null;
  const visible=focus&&focus!=='QQQ'?['QQQ',focus]:['QQQ','MSFT','AAPL','GOOGL','AMZN','NVDA','META','TSLA'].filter(s=>series[s]);
  const indexed={};for(const s of visible){const item=series[s],base=item.points[0].close;indexed[s]=item.points.map(p=>({...p,value:p.close/base*100}))}
  const W=1000,H=300,L=48,R=18,T=18,B=36,t0=dateOnly(qqq.points[0].date).getTime(),t1=dateOnly(qqq.points.at(-1).date).getTime();
  const values=visible.flatMap(s=>indexed[s].map(p=>p.value)),min=Math.floor(Math.min(...values)/10)*10,max=Math.ceil(Math.max(...values)/10)*10,span=max-min||1;
  const x=d=>L+(dateOnly(d).getTime()-t0)/(t1-t0)*(W-L-R),y=v=>T+(max-v)/span*(H-T-B);
  const path=s=>indexed[s].map((p,i)=>`${i?'L':'M'}${x(p.date).toFixed(1)},${y(p.value).toFixed(1)}`).join(' ');
  const grid=[0,.25,.5,.75,1].map(f=>{const value=max-f*span,yy=y(value);return `<line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" stroke="#e4e9e5"/><text x="${L-7}" y="${yy+4}" text-anchor="end" font-size="10" fill="#68736c">${value.toFixed(0)}</text>`}).join('');
  const lines=visible.map(s=>`<path d="${path(s)}" fill="none" stroke="${colors[s]||'#637d8d'}" stroke-width="${s==='QQQ'||s===focus?2.6:1.4}" stroke-opacity="${s==='QQQ'||s===focus?1:.22}" vector-effect="non-scaling-stroke"/>`).join('');
  const nearest=(s,d)=>indexed[s].reduce((best,p)=>Math.abs(dateOnly(p.date)-dateOnly(d))<Math.abs(dateOnly(best.date)-dateOnly(d))?p:best,indexed[s][0]);
  const eligible=EPS_CHART.filter(e=>visible.includes(e.ticker)&&e.report_date>=qqq.points[0].date&&e.report_date<=qqq.points.at(-1).date&&e.report_date>=indexed[e.ticker][0].date&&e.report_date<=indexed[e.ticker].at(-1).date);
  const marks=eligible.map(e=>{const p=nearest(e.ticker,e.report_date),q=nearest('QQQ',e.report_date),color=e.result==='beat'?'#087052':e.result==='miss'?'#b04c45':'#b87513';const tip=encodeURIComponent(JSON.stringify({ticker:e.ticker,date:e.report_date,quarter:e.quarter,close:p.close,currency:series[e.ticker].currency,performance:p.value-100,relative:p.value-q.value,actual:e.actual_eps,consensus:e.consensus_eps,surprise:e.surprise_pct,result:e.result}));return `<g><line x1="${x(p.date)}" y1="${T}" x2="${x(p.date)}" y2="${H-B}" stroke="${color}" stroke-opacity="${focus?.18:.07}" stroke-dasharray="3 5"/><circle class="market-dot" data-tip="${tip}" cx="${x(p.date)}" cy="${y(p.value)}" r="${focus?5:3.4}" fill="${color}" fill-opacity="${focus?1:.85}" stroke="#fff" stroke-width="2"/></g>`}).join('');
  const years=[...new Set(qqq.points.map(p=>p.date.slice(0,4)))].map(year=>`<text x="${Math.max(L,x(year+'-01-01'))}" y="${H-10}" font-size="10" fill="#68736c">${year}</text>`).join('');
  box.innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="QQQ 与公司股价表现及 EPS 预期差">${grid}<line x1="${L}" y1="${y(100)}" x2="${W-R}" y2="${y(100)}" stroke="#68736c" stroke-opacity=".35" stroke-dasharray="4 4"/>${lines}${marks}${years}</svg><div class="chart-tip hidden" id="chartTip"></div>`;
  const tip=$('chartTip');box.querySelectorAll('.market-dot').forEach(dot=>{dot.onmouseenter=ev=>{const d=JSON.parse(decodeURIComponent(dot.dataset.tip)),cls=d.performance>=0?'positive':'negative',rel=d.relative>=0?'positive':'negative',result=d.result==='beat'?'超预期':d.result==='miss'?'低于预期':'符合预期';tip.innerHTML=`<strong>${esc(d.ticker)} · ${esc(d.quarter)}</strong><span class="tip-date">${d.date} 财报发布</span><div class="tip-grid"><span>收盘价</span><b>${d.currency==='USD'?'$':d.currency+' '}${d.close.toFixed(2)}</b><span>序列起点至今</span><b class="${cls}">${d.performance>=0?'+':''}${d.performance.toFixed(1)}%</b><span>相对 QQQ</span><b class="${rel}">${d.relative>=0?'+':''}${d.relative.toFixed(1)} pct</b><span>EPS 实际 / 预期</span><b>${d.actual} / ${d.consensus}</b><span>EPS 预期差</span><b>${result} ${d.surprise>=0?'+':''}${d.surprise}%</b></div>`;const rect=box.getBoundingClientRect();tip.style.left=`${Math.min(rect.width-130,Math.max(130,ev.clientX-rect.left))}px`;tip.style.top=`${ev.clientY-rect.top}px`;tip.classList.remove('hidden')};dot.onmouseleave=()=>tip.classList.add('hidden')});
  $('marketTitle').textContent=focus?`${focus} 与 QQQ · 归一化表现`:'QQQ 与 Mag 7 · 归一化表现';
  $('marketNote').innerHTML=`${qqq.points[0].date} 至 ${qqq.points.at(-1).date}，全部序列起点=100。圆点颜色表示该季度 EPS 相对市场一致预期的结果。`;
  $('marketLegend').innerHTML=visible.map(s=>`<span class="line-key"><i style="background:${colors[s]||'#637d8d'}"></i>${s}</span>`).join('')+'<span><i style="background:#087052"></i>绿色＝超预期</span><span><i style="background:#b04c45"></i>红色＝低于预期</span><span><i style="background:#b87513"></i>橙色＝符合预期</span>';
}
