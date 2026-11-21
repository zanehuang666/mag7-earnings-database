/* Public library view: the company files and Markdown metadata are authoritative. */
(async function loadLibrary() {
  let library;
  try {
    const response = await fetch('./data/library_index.json', {cache: 'no-store'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    library = await response.json();
  } catch (error) {
    const links = document.getElementById('databaseLinks');
    if (links) links.insertAdjacentHTML('beforeend', '<span>季度文件索引暂不可用，请从 GitHub 公司文件夹浏览。</span>');
    return;
  }
  for (let attempt = 0; attempt < 100 && !DATA; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  if (!DATA) return;

  const knownCompanies = new Set(DATA.companies.map(company => company.ticker));
  for (const company of library.companies) {
    if (!knownCompanies.has(company.ticker)) {
      DATA.companies.push({ticker: company.ticker, company: company.company});
      knownCompanies.add(company.ticker);
    }
    FIRST_TIER_RESEARCH.add(company.ticker);
    if (company.html_path) {
      REPORT_META[company.ticker] = {...(REPORT_META[company.ticker] || {}), path: company.html_path};
    }
  }

  const knownEvents = new Set(DATA.calendar.formal.events.map(event => event.id));
  for (const record of library.events) {
    QUARTER_RESEARCH[record.id] = record;
    if (!record.date || knownEvents.has(record.id)) continue;
    const empty = {verdict: '等待官方资料', summary: '季度原始资料与研究稿见公司文件夹。',
                   points: ['核对官方财报与下一季指引'], risks: ['资料与日期仍需复核']};
    DATA.calendar.formal.events.push({id: record.id, ticker: record.ticker, company: record.company,
      date: record.date, fiscal_period: record.quarter,
      status: record.released ? 'reported' : 'estimated',
      preview: empty, aftercheck: empty,
      source: {label: record.date_basis === 'calendar' ? '财报日历' : '公司或监管资料（日期可能为申报日）',
               url: record.stages.analysis?.source_packet || record.stages.preview?.source_packet || '#'}});
    knownEvents.add(record.id);
  }

  const previousSelectCompany = selectCompany;
  selectCompany = function selectLibraryCompany(ticker) {
    previousSelectCompany(ticker);
    if (!REPORT_META[ticker]) {
      document.getElementById('companyReport').insertAdjacentHTML('beforeend',
        ` <a href="https://github.com/zanehuang666/mag7-earnings-database/tree/main/database/${encodeURIComponent(ticker)}" target="_blank" rel="noopener">GitHub 公司文件夹 ↗</a>`);
    }
  };

  const previousRenderPanel = renderPanel;
  renderPanel = function renderLibraryPanel() {
    previousRenderPanel();
    if (mode !== 'formal' || !selected) return;
    const record = QUARTER_RESEARCH[selected.id];
    if (!record) return;
    const stage = kind === 'aftercheck' ? 'analysis' : 'preview';
    const item = record.stages[stage];
    if (item?.path) {
      document.getElementById('verdict').textContent = item.summary || '已保存 Markdown 研究稿';
    }
    const box = document.getElementById('quarterMarkdown');
    if (box && item?.versions?.length) {
      const links = item.versions.map(path => `<li><a href="./${encodeURI(path)}" download>${esc(path.split('/').pop())}</a></li>`).join('');
      box.insertAdjacentHTML('beforeend', `<details><summary>查看历史版本（${item.versions.length}）</summary><ul>${links}</ul></details>`);
    }
    if (record.date_basis !== 'calendar') {
      document.getElementById('researchMeta').textContent += ' · 日历日期待 IR 核对';
    }
  };

  const links = document.getElementById('databaseLinks');
  links.insertAdjacentHTML('beforeend',
    '<a href="./data/library_index.json" target="_blank">完整季度文件索引 ↗</a>' +
    '<a href="./data/html_coverage.json" target="_blank">HTML 历史覆盖状态 ↗</a>' +
    '<a href="https://github.com/zanehuang666/mag7-earnings-database/blob/main/RESEARCH_EXPANSION_INDEX.md" target="_blank">GitHub 下载目录 ↗</a>');
  renderCompanyButtons();
  renderCalendar();
})();
