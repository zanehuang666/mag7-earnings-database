/* Presentation-only cleanup. The underlying research and calendar data stay intact. */
(() => {
  const databaseUrl = ticker => `https://github.com/zanehuang666/mag7-earnings-database/tree/main/database/${encodeURIComponent(ticker)}`;
  let queued = false;
  function clean() {
    queued = false;
    document.querySelectorAll('#companies .company').forEach(button => {
      const company = DATA?.companies?.find(item => item.ticker === button.dataset.ticker)
        || customCompanies?.find(item => item.ticker === button.dataset.ticker);
      if (company && button.textContent !== company.company) button.textContent = company.company;
      button.title = button.dataset.ticker;
    });
    document.querySelectorAll('.hero-nav, #syncSources, .library-coverage, .library-candidate').forEach(node => node.remove());
    document.querySelectorAll('#companyReport, #macroSources, #marketNote').forEach(root => {
      root.querySelectorAll('a').forEach(link => {
        const href = link.getAttribute('href') || '';
        if (!/\/overview\.html(?:[?#]|$)/i.test(href) && !/\/database\/[A-Z0-9.]+\/?$/i.test(href)) link.remove();
      });
    });
    document.querySelectorAll('#quarterMarkdown > a, #quarterMarkdown > details, #sourceList a').forEach(node => node.remove());
    const ticker = selectedTicker || selected?.ticker;
    for (const id of ['companyReport', 'eventPanel']) {
      const root = document.getElementById(id);
      if (!root || root.closest('.hidden') || !ticker) continue;
      const existingDatabaseLink = [...root.querySelectorAll('a')].find(link =>
        link.href.startsWith(databaseUrl(ticker)));
      if (existingDatabaseLink) {
        existingDatabaseLink.dataset.databaseLink = 'true';
        if (existingDatabaseLink.textContent !== '公司数据库 ↗') existingDatabaseLink.textContent = '公司数据库 ↗';
      } else {
        const link = document.createElement('a');
        link.href = databaseUrl(ticker);
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'source';
        link.dataset.databaseLink = 'true';
        link.textContent = '公司数据库 ↗';
        root.insertBefore(link, root.firstChild);
      }
      const report = REPORT_META?.[ticker];
      if (id === 'eventPanel' && report?.path && !root.querySelector('a[data-html-link]')) {
        const link = document.createElement('a');
        link.href = `./${report.path}`;
        link.target = '_blank';
        link.rel = 'noopener';
        link.className = 'source';
        link.dataset.htmlLink = 'true';
        link.textContent = '打开 HTML 研究 ↗';
        root.insertBefore(link, root.firstChild);
      }
    }
  }
  const observer = new MutationObserver(() => {
    if (!queued) { queued = true; requestAnimationFrame(clean); }
  });
  observer.observe(document.documentElement, {subtree: true, childList: true});
  clean();
})();
