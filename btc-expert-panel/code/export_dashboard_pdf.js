/**
 * export_dashboard_pdf.js - turns dashboard/index.html into a printable PDF.
 *
 *   npm install playwright chart.js
 *   node code/export_dashboard_pdf.js                     # -> dashboard/BTC_Expert_Panel_Dashboard.pdf
 *   node code/export_dashboard_pdf.js out.pdf             # choose the filename
 *
 * The dashboard is a web page: it scrolls, it has hover tooltips, and its tables sit in
 * horizontally scrolling boxes. A PDF has none of that, so this script:
 *   - pins the light theme, because a dark page wastes ink and reads badly on paper,
 *   - opens every scrolling box so no table is silently cut off at its right edge,
 *   - tells the renderer not to split a panel, a seat card or a table row across two pages,
 *   - lays it out on A4 landscape, which suits the dashboard's wide three-column grid.
 *
 * Chart.js is loaded from node_modules rather than the CDN so the export also works offline.
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const ROOT = path.resolve(__dirname, "..");
const PAGE = path.join(ROOT, "dashboard", "index.html");
const OUT = process.argv[2] || path.join(ROOT, "dashboard", "BTC_Expert_Panel_Dashboard.pdf");

const PRINT_CSS = `
  html, body { background: #fff !important; }
  .wrap { max-width: none; padding-inline: 14px; gap: 18px; }
  /* keep atomic only what reads as ONE object: a card, a table, a callout.
     Tall panels are allowed to split, otherwise a panel that does not fit leaves most of a
     page blank and the export runs to twice the length for no gain. */
  .seat, .verdict, .pending, .verdictbox, .zrow { break-inside: avoid; page-break-inside: avoid; }
  table, tr, .heat, .chartbox, .pfgrid { break-inside: avoid; page-break-inside: avoid; }
  /* Panels are atomic by default, so a card never starts as an empty bordered box at the foot
     of a page. The few panels that are genuinely taller than one page are allowed to split. */
  .panel { break-inside: avoid; page-break-inside: avoid; }
  section[aria-labelledby="score-h"], section[aria-labelledby="board-h"],
  section[aria-labelledby="new-h"], section[aria-labelledby="pf-h"],
  .notes section, .seats { break-inside: auto; page-break-inside: auto; }
  /* a heading and its blurb must not be stranded at the foot of a page without the chart */
  .panel-head, .panel > p, .legend { break-after: avoid; page-break-after: avoid; }
  #perf-sub, .panel-head p a { }
  h1, h2, h3 { break-after: avoid; page-break-after: avoid; }
  /* a PDF cannot scroll sideways, so let the wide things show in full */
  .scroll, .heatwrap { overflow: visible !important; }
  .heat .rowcells span { min-width: 1px !important; }
  .ranges, .tip { display: none !important; }        /* controls do nothing on paper */
  .hide-print { display: none !important; }           /* instructions about clicking and hovering */
  section.panel { box-shadow: none; }
`;

(async () => {
  if (!fs.existsSync(PAGE)) {
    console.error(`${PAGE} not found - run: python code/make_dashboard.py`);
    process.exit(1);
  }
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1120, height: 900 } });

  // serve Chart.js locally if it is installed, so the export does not need the network
  const local = path.join(ROOT, "node_modules", "chart.js", "dist", "chart.umd.js");
  if (fs.existsSync(local)) {
    await page.route(/cdnjs\.cloudflare\.com.*chart/i, r =>
      r.fulfill({ path: local, contentType: "application/javascript" }));
  }

  const errors = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.goto("file://" + PAGE, { waitUntil: "networkidle" }).catch(() => page.goto("file://" + PAGE));
  await page.evaluate(() => document.documentElement.setAttribute("data-theme", "light"));
  await page.addStyleTag({ content: PRINT_CSS });
  // strip instructions that only make sense on a live page
  await page.evaluate(() => {
    const dead = [/click a name in the legend/i, /click a column to sort/i, /hover a week/i,
                  /hover a cell/i, /hover for drawdown/i, /open this file in any browser/i];
    document.querySelectorAll("p, .muted, caption, th").forEach(el => {
      if (el.children.length === 0 && dead.some(r => r.test(el.textContent))) {
        el.textContent = el.textContent.replace(/\s*(Click|Hover)[^.]*\.\s*/g, " ").trim();
      }
    });
  });
  await page.waitForTimeout(2000);                    // let the charts finish drawing

  await page.pdf({
    path: OUT, format: "A4", landscape: true, printBackground: true,
    margin: { top: "12mm", bottom: "14mm", left: "8mm", right: "8mm" },
    displayHeaderFooter: true,
    headerTemplate: `<div style="font-size:7pt;color:#7C8392;width:100%;padding:0 10mm;font-family:sans-serif">BTC Expert Panel</div>`,
    footerTemplate: `<div style="font-size:7pt;color:#7C8392;width:100%;padding:0 10mm;font-family:sans-serif;display:flex;justify-content:space-between">
       <span>Research on historical data, not investment advice.</span>
       <span>Page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>`,
  });
  await browser.close();
  if (errors.length) console.error("page errors:", errors);
  console.log(`wrote ${OUT} (${(fs.statSync(OUT).size / 1024).toFixed(0)} KB)`);
})();
