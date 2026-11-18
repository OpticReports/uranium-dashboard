// Render report.html and save each figure as a PNG (charts/*.png). Run: node shots.js [scale] [theme]
const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
(async () => {
  const study = path.dirname(__dirname); const scale = +(process.argv[2] || 2); const theme = process.argv[3] || 'light';
  const body = fs.readFileSync(path.join(study, 'report.html'), 'utf8');
  const html = `<!doctype html><html data-theme="${theme}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><style>body{margin:0;font:14px system-ui}</style></head><body>${body}</body></html>`;
  const b = await chromium.launch(); const pg = await b.newPage({ viewport: { width: +(process.argv[4] || 1000), height: 900 }, deviceScaleFactor: scale });
  const errs = []; pg.on('console', m => { if (m.type() === 'error') errs.push(m.text()); }); pg.on('pageerror', e => errs.push(String(e)));
  await pg.setContent(html, { waitUntil: 'load' }); await pg.waitForTimeout(300);
  const out = process.argv[5] || path.join(study, 'charts'); fs.mkdirSync(out, { recursive: true });
  const names = { f_eq: '01_equity', f_dd: '02_drawdown', f_exp: '03_exposure_10m_rule', f_ep: '04_episodes', f_forest: '05_all_53_rules', f_fr1: '06_frontier_2007_2026', f_fr2: '07_frontier_2017_2026', f_wf: '08_walk_forward', f_loo1: '09_legs_sharpe', f_loo2: '10_legs_drawdown', f_e1: '11_after_oversold', f_e2: '12_after_overbought' };
  for (const [id, n] of Object.entries(names)) await (await pg.$('#' + id)).screenshot({ path: path.join(out, n + '.png') });
  await pg.screenshot({ path: path.join(out, '_full.png'), fullPage: true });
  console.log('errors:', errs.length ? errs : 'none', 'scrollW', await pg.evaluate(() => document.documentElement.scrollWidth));
  await b.close();
})();
