(() => {
  "use strict";
  const M = window.REPORT_DATA;
  const NS = "http://www.w3.org/2000/svg";
  const H = 252, T = 22, B = 34, L = 50, R = 16;
  const colors = ["#253b59", "#416a92", "#a7bccd", "#b7955e", "#9b8397", "#157f82", "#73b7b1", "#5d9d98", "#527d92", "#b48a43"];
  const hidden = {};
  const tip = document.getElementById("tip");
  const svgEl = (name, attrs = {}) => {
    const el = document.createElementNS(NS, name);
    Object.entries(attrs).forEach(([k, v]) => el.setAttribute(k, String(v)));
    return el;
  };
  const fmt = v => Number.isFinite(v) ? Number(v).toLocaleString("zh-CN", {maximumFractionDigits: 2}) : "—";
  const real = v => typeof v === "number" && Number.isFinite(v);
  const evidence = (s,i) => s.evidence?.[i]?.locator ? `｜${s.evidence[i].locator}` : "";
  const plotVals = s => s.values.filter(real);
  function showTip(e, content) {
    tip.textContent = content;
    tip.style.display = "block";
    tip.style.left = `${Math.min(e.clientX + 12, innerWidth - 230)}px`;
    tip.style.top = `${Math.min(e.clientY + 12, innerHeight - 75)}px`;
  }
  function hover(el, content) {
    el.addEventListener("mousemove", e => showTip(e, content));
    el.addEventListener("mouseleave", () => {tip.style.display = "none";});
  }
  function label(svg, x, y, text, anchor = "middle") {
    const el = svgEl("text", {x, y, "text-anchor": anchor, class: "axis"});
    el.textContent = text;
    svg.append(el);
  }
  function axis(svg, min, max, xRight, xStep, labels) {
    const height = H - T - B, span = max - min || 1;
    const y = v => T + (max - v) / span * height;
    const tickStep = span / 4;
    const tickDigits = tickStep < 1 ? Math.min(6, Math.max(2, Math.ceil(-Math.log10(tickStep)) + 1)) : 2;
    for (let i = 0; i <= 4; i++) {
      const value = min + span * i / 4, yy = y(value);
      svg.append(svgEl("line", {x1:L, x2:xRight, y1:yy, y2:yy, class:"grid"}));
      label(svg, L - 6, yy + 3, Number(value.toFixed(tickDigits)).toLocaleString("zh-CN", {maximumFractionDigits:tickDigits}), "end");
    }
    if (min < 0 && max > 0) svg.append(svgEl("line", {x1:L, x2:xRight, y1:y(0), y2:y(0), stroke:"#718092", "stroke-width":1.4}));
    labels.forEach((q, i) => label(svg, L + (i + .5) * xStep, H - 8, q));
    return y;
  }
  function niceStep(value) {
    const power = Math.pow(10, Math.floor(Math.log10(value)));
    const fraction = value / power;
    return ([1, 2, 2.5, 5, 10].find(step => step >= fraction) || 10) * power;
  }
  function range(values, includeZero = true) {
    const all = values.filter(real);
    if (!all.length) return [-1, 1];
    let lo = Math.min(...all), hi = Math.max(...all);
    if (includeZero) {lo = Math.min(0, lo); hi = Math.max(0, hi);}
    if (includeZero && lo === 0 && hi === 0) return [0, 1];
    const span = hi - lo;
    const pad = span > 0 ? span * .06 : Math.max(Math.abs(hi) * .08, .01);
    if (includeZero) {
      lo = lo < 0 ? lo - pad : 0;
      hi = hi > 0 ? hi + pad : 0;
    } else {lo -= pad; hi += pad;}
    const step = niceStep(Math.max((hi - lo) / 4, 1e-9));
    lo = Math.floor(lo / step) * step;
    hi = Math.ceil(hi / step) * step;
    if (lo === hi) hi += step;
    return [Number(lo.toPrecision(12)), Number(hi.toPrecision(12))];
  }
  function makeLegend(container, chart, rerender) {
    const box = container.querySelector("[data-legend]") || document.querySelector(`[data-progress-legend="${chart.id}"]`);
    if (!box) return;
    box.replaceChildren();
    chart.series.forEach((s, i) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "legend-button" + (hidden[chart.id + "|" + s.key] ? " off" : "");
      button.dataset.key = s.key;
      const color = document.createElement("i");
      color.className = "key";
      color.style.background = colors[i % colors.length];
      button.append(color, document.createTextNode(s.name));
      if (chart.id === "g1") {
        const tag = document.createElement("span");
        tag.className = "group-tag " + (s.side === "ai" ? "ai" : "trad");
        tag.textContent = s.side === "ai" ? "AI相关" : "传统";
        button.append(tag);
      }
      button.addEventListener("click", () => {hidden[chart.id + "|" + s.key] = !hidden[chart.id + "|" + s.key]; rerender();});
      box.append(button);
    });
    if (chart.series.length) {
      const all = document.createElement("button");
      all.type = "button"; all.className = "legend-button show-all"; all.textContent = "显示全部";
      all.addEventListener("click", () => {chart.series.forEach(s => {delete hidden[chart.id + "|" + s.key];}); rerender();});
      box.append(all);
    }
  }
  function drawAnnual(card) {
    const plot = card.querySelector("[data-plot]");
    plot.className = "annual";
    plot.replaceChildren();
    const years = Object.keys(M.annual).filter(y => M.annual[y].actual !== null || M.annual[y].events.length).slice(-2);
    if (!years.length) {plot.textContent = "公司未给数值指引，年度实际亦未可得"; return;}
    years.forEach(year => {
      const info = M.annual[year];
      const box = document.createElement("div");
      const heading = document.createElement("b"); heading.textContent = `${year} 年 CapEx`;
      box.append(heading);
      const actual = document.createElement("div"); actual.className = "fine";
      actual.textContent = `年度实际：${fmt(info.actual)} ${M.unit}`;
      box.append(actual);
      if (!info.events.length) {
        const line = document.createElement("div"); line.className = "annual-event"; line.textContent = "公司未给数值指引"; box.append(line);
      } else {
        const comparable = info.events.filter(e => e.comparable);
        const numeric = comparable.map(e => real(e.value) ? e.value : real(e.low) ? e.low : e.high).filter(real);
        const [lo, hi] = range([...numeric, info.actual], false);
        const svg = svgEl("svg", {viewBox:"0 0 520 82", role:"img"});
        svg.append(svgEl("line", {x1:30, x2:490, y1:42, y2:42, stroke:"#dce3e9", "stroke-width":2}));
        const px = v => 30 + (v - lo) / (hi - lo) * 460;
        const points = [];
        comparable.forEach((event, i) => {
          const v = real(event.value) ? event.value : real(event.low) ? event.low : event.high;
          if (!real(v)) return;
          const cx = px(v), cy = 38 - (i % 2) * 9;
          points.push(`${cx},${cy}`);
          const dot = svgEl("circle", {cx, cy, r:5, fill:"#b05c53"});
          hover(dot, `${event.issued_at || ""} 指引：${fmt(v)} ${M.unit}${event.note ? "｜" + event.note : ""}`);
          svg.append(dot);
        });
        if (points.length > 1) svg.prepend(svgEl("polyline", {points:points.join(" "), fill:"none", stroke:"#b05c53", "stroke-width":2}));
        if (real(info.actual)) {
          const dot = svgEl("circle", {cx:px(info.actual), cy:58, r:5, fill:"#18865f"});
          hover(dot, `年度实际：${fmt(info.actual)} ${M.unit}`); svg.append(dot);
        }
        box.append(svg);
        info.events.forEach(event => {
          const line = document.createElement("div"); line.className = "annual-event";
          const value = real(event.value) ? event.value : real(event.low) && real(event.high) ? `${fmt(event.low)}—${fmt(event.high)}` : "—";
          line.textContent = `${event.issued_at || "日期未记"}：${typeof value === "number" ? fmt(value) : value} ${M.unit}`;
          if (!event.comparable) {
            const warning = document.createElement("span"); warning.className = "warning";
            warning.textContent = "｜净额指引，与毛额实际不可比"; line.append(warning);
          }
          if (event.note) {
            const note = document.createElement("span"); note.className = "warning";
            note.textContent = `｜${event.note}`; line.append(note);
          }
          box.append(line);
        });
      }
      plot.append(box);
    });
  }
  function renderChart(chart) {
    const node = document.getElementById(chart.id);
    if (!node) throw new Error(`missing chart card ${chart.id}`);
    const card = node.classList.contains("chart-card") ? node : node.closest(".chart-card");
    if (chart.type === "annual") {drawAnnual(card); card.dataset.rendered = "true"; return;}
    const visible = chart.series.map((s,i) => ({...s, color:colors[i % colors.length]})).filter(s => !hidden[chart.id + "|" + s.key]);
    const plot = card.querySelector("[data-plot]");
    makeLegend(card, chart, () => renderChart(chart));
    plot.replaceChildren();
    const note = card.querySelector("[data-note]");
    if (note) note.textContent = "";
    if (!visible.some(s => plotVals(s).length)) {
      const empty = document.createElement("div"); empty.className = "empty-plot";
      empty.textContent = chart.series.length ? "所选系列暂无可绘数值" : "已核查：该图数据未披露或尚未完成来源核实";
      plot.append(empty); card.dataset.rendered = "empty"; return;
    }
    const guide = chart.id === "g1" ? M.guide : null;
    const guideAmount = guide && guide.unit !== "%" && [guide.low, guide.high, guide.point].some(real);
    const slots = M.quarters.length + (guideAmount ? 1 : 0);
    const W = Math.max(1190, slots * 48 + L + R), step = (W - L - R) / slots, bw = Math.min(30, step * .65);
    const svg = svgEl("svg", {viewBox:`0 0 ${W} ${H}`, role:"img"});
    const sums = M.quarters.map((_,i) => visible.some(s => real(s.values[i])) ? visible.reduce((n,s) => n + (real(s.values[i]) ? s.values[i] : 0),0) : null);
    let values = visible.flatMap(plotVals);
    if (chart.type === "stack" || chart.type === "profit") {
      const pos = M.quarters.map((_,i) => real(sums[i]) ? visible.reduce((n,s) => n + Math.max(0, real(s.values[i]) ? s.values[i] : 0),0) : null);
      const neg = M.quarters.map((_,i) => real(sums[i]) ? visible.reduce((n,s) => n + Math.min(0, real(s.values[i]) ? s.values[i] : 0),0) : null);
      values = [...pos, ...neg, ...sums];
    }
    if (chart.type === "bridge") {
      const o = visible.find(s => s.key.endsWith("__ocf")), c = visible.find(s => s.key.endsWith("__cash_capex"));
      const f = visible.find(s => s.key.endsWith("__derived_fcf"));
      values = [];
      M.quarters.forEach((_,i) => {
        const ov = o && real(o.values[i]) ? o.values[i] : null;
        const cv = c && real(c.values[i]) ? c.values[i] : null;
        const fv = f && real(f.values[i]) ? f.values[i] : null;
        if (real(ov)) values.push(0, ov);
        if (real(cv)) values.push(real(ov) ? ov : 0, (real(ov) ? ov : 0) - cv);
        if (real(fv)) values.push(fv);
      });
    }
    if (guideAmount) values.push(...[guide.low, guide.high, guide.point].filter(real));
    const includeZero = chart.type !== "line" || chart.id === "progressTradChart" || chart.id === "progressAiChart";
    const [min,max] = range(values, includeZero);
    svg.setAttribute("data-y-min", String(min));
    svg.setAttribute("data-y-max", String(max));
    const y = axis(svg,min,max,W-R,step,M.quarters);
    (M.breakpoints || []).forEach(q => {
      const i = M.quarters.indexOf(q);
      if (i > 0) {
        const x = L + i * step;
        svg.append(svgEl("line", {x1:x,x2:x,y1:T,y2:H-B,stroke:"#9da8b4","stroke-width":1,"stroke-dasharray":"3 3"}));
        label(svg,x+3,T+9,"口径变更","start");
      }
    });
    const point = (s,i,v) => {
      const dot = svgEl("circle", {cx:L+(i+.5)*step, cy:y(v), r:3, fill:s.color});
      hover(dot, `${M.quarters[i]} · ${s.name}：${fmt(v)} ${s.unit || chart.unit}${evidence(s,i)}`);
      svg.append(dot);
    };
    const lineSeries = (s,vals) => {
      let run = [];
      const flush = () => {if(run.length > 1) svg.append(svgEl("polyline", {points:run.join(" "), fill:"none", stroke:s.color, "stroke-width":2.2})); run=[];};
      vals.forEach((v,i) => {if(real(v)) {run.push(`${L+(i+.5)*step},${y(v)}`); point(s,i,v);} else flush();}); flush();
    };
    if (chart.type === "stack" || chart.type === "profit") {
      M.quarters.forEach((q,i) => {
        let positive=0,negative=0;
        visible.forEach(s => {
          const v=s.values[i]; if(!real(v)) return;
          const from = v >= 0 ? positive : negative, to = from + v;
          if(v >= 0) positive = to; else negative = to;
          const rect=svgEl("rect", {x:L+(i+.5)*step-bw/2, y:Math.min(y(from),y(to)), width:bw, height:Math.abs(y(from)-y(to)), fill:s.color});
          hover(rect, `${q} · ${s.name}：${fmt(v)} ${chart.unit}${evidence(s,i)}`); svg.append(rect);
        });
      });
      if(chart.type === "profit") lineSeries({name:"所选分部利润合计",color:"#172a3e",unit:chart.unit},sums);
      if(chart.id === "g1" && M.quarters.length) {
        const i=M.quarters.length-1, x=L+(i+.5)*step-bw/2-2;
        for (const side of ["traditional","ai"]) {
          const subtotal=visible.filter(s=>s.side===side).reduce((n,s)=>n+(real(s.values[i])?s.values[i]:0),0);
          if(subtotal > 0) svg.append(svgEl("rect", {x, y:y(subtotal), width:bw+4, height:Math.abs(y(0)-y(subtotal)), fill:"none", stroke:side==="ai"?"#157f82":"#344f70", "stroke-width":1.2}));
        }
      }
    } else if(chart.type === "line") visible.forEach(s => lineSeries(s,s.values));
    else if(chart.type === "bar") visible.forEach(s => s.values.forEach((v,i) => {
      if(!real(v)) return;
      const rect=svgEl("rect", {x:L+(i+.5)*step-bw/2, y:Math.min(y(0),y(v)), width:bw, height:Math.abs(y(0)-y(v)), fill:s.color});
      hover(rect, `${M.quarters[i]} · ${s.name}：${fmt(v)} ${chart.unit}${evidence(s,i)}`); svg.append(rect);
    }));
    else if(chart.type === "bridge") {
      const o=visible.find(s=>s.key.endsWith("__ocf")), c=visible.find(s=>s.key.endsWith("__cash_capex")), f=visible.find(s=>s.key.endsWith("__derived_fcf"));
      M.quarters.forEach((q,i)=>{
        const x=L+(i+.5)*step-bw/2;
        if(o && real(o.values[i])) {const v=o.values[i],rect=svgEl("rect",{x,y:Math.min(y(0),y(v)),width:bw,height:Math.abs(y(0)-y(v)),fill:"#527d92"});hover(rect,`${q} · 经营现金流：${fmt(v)} ${chart.unit}${evidence(o,i)}`);svg.append(rect);}
        if(c && real(c.values[i])) {const base=o&&real(o.values[i])?o.values[i]:0,v=c.values[i],rect=svgEl("rect",{x,y:Math.min(y(base),y(base-v)),width:bw,height:Math.abs(y(base)-y(base-v)),fill:"#b48a43"});hover(rect,`${q} · 现金 CapEx：${fmt(v)} ${chart.unit}${evidence(c,i)}`);svg.append(rect);}
      });
      if(f) lineSeries({...f,color:"#274c6b"},f.values);
    }
    if(guide) {
      if(guideAmount) {
        const x=L+(M.quarters.length+.5)*step, low=real(guide.low)?guide.low:guide.point, high=real(guide.high)?guide.high:guide.point;
        if(real(low)&&real(high)) {
          const band=svgEl("line",{x1:x,x2:x,y1:y(low),y2:y(high),stroke:"#b05c53","stroke-width":7});
          hover(band,`${guide.target} 集团收入指引：${fmt(low)}—${fmt(high)} ${M.unit}`);svg.append(band);
          label(svg,x,H-8,`${guide.target} 指引`);
        }
      } else if (note) note.textContent=`${guide.target} 集团收入百分比指引：${fmt(guide.low)}%—${fmt(guide.high)}%（无同口径基期，未换算金额）`;
    }
    plot.append(svg); card.dataset.rendered="true";
  }
  try {
    M.charts.forEach(renderChart);
    for (const cid of ["progressTradChart","progressAiChart"]) {
      const rows=M.progress[cid], plot=document.getElementById(cid);
      const chart={id:cid,type:"line",series:rows,unit:rows[0]?.unit||"%"};
      const wrapper=plot.closest(".chart-card");
      wrapper.dataset.chart=cid;
      plot.dataset.plot="";
      renderChart(chart);
    }
    document.body.dataset.rendered="true";
    window.reportDiagnostics={ok:true,charts:M.charts.length};
  } catch (error) {
    window.reportDiagnostics={ok:false,error:String(error)};
    document.body.dataset.rendered="error";
    throw error;
  }
})();
