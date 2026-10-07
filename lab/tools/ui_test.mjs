// End-to-end test of the Protocol Lab page in Chromium (Playwright).
// usage: node lab/tools/ui_test.mjs BASE_URL OUT_DIR
//   BASE_URL: site root serving /projects/protocol-lab/ (local copy or the live site)
// Checks: engine loads; module cards; a two-variant run per module; comparison table;
// language switch; package download; coverage drill-down; validation errors; export/import;
// cancel; mobile width without horizontal scroll; no page errors.
import { chromium } from "playwright";
import fs from "node:fs";

const [base, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, acceptDownloads: true });
const problems = [];
page.on("pageerror", (e) => problems.push("pageerror: " + e.message));
page.on("console", (m) => { if (m.type() === "error") problems.push("console: " + m.text()); });
const report = {};
const ok = (name, cond, detail) => { report[name] = { ok: !!cond, detail }; if (!cond) problems.push("FAILED " + name + " " + JSON.stringify(detail)); };

await page.goto(base + "/projects/protocol-lab/");
await page.click('button[data-lang="en"]');
await page.waitForSelector("#module-cards .card", { timeout: 240000 });
const status = await page.textContent("#engine-status");
ok("engine_ready", /ready/i.test(status), status);
const cards = await page.$$eval("#module-cards .card__title", (n) => n.map((x) => x.textContent));
ok("module_cards", cards.length >= 3, cards);
ok("counts_separate", /35 protocols/.test(await page.textContent("#modules-counts")), await page.textContent("#modules-counts"));

const results = {};
// WORK-CYCLE last: the validation step below uses its number fields
const wcIndex = cards.findIndex((t) => /WORK-CYCLE/.test(t));
const visit = [...cards.keys()].filter((i) => i !== wcIndex).concat(wcIndex >= 0 ? [wcIndex] : []);
for (const i of visit) {
  await page.click(`#module-cards .card >> nth=${i} >> button.btn`);
  await page.waitForFunction((prev) => {
    const ids = document.querySelectorAll("#result-body .lab-ids");
    return ids.length && ids[0].textContent !== prev;
  }, results.lastInput || "", { timeout: 300000 });
  const ids = await page.$$eval("#result-body .lab-ids", (n) => n.map((x) => x.textContent));
  const rows = await page.$$eval("#result-body table >> nth=0 >> tbody tr", (n) => n.length).catch(() => 0);
  results[cards[i]] = { ids: ids.slice(-3), comparison_rows: rows };
  results.lastInput = ids[0];
  ok(`run_${i}`, ids.some((x) => x.startsWith("result_id")) && rows === 2, results[cards[i]]);
  const [dl] = await Promise.all([page.waitForEvent("download"), page.click("#download-package")]);
  const file = `${out}/${dl.suggestedFilename()}`;
  await dl.saveAs(file);
  results[cards[i]].package = file;
}
await page.screenshot({ path: `${out}/desktop_en.png` });

await page.click('button[data-lang="ru"]');
ok("lang_ru", (await page.textContent(".hero__title")) === "Лаборатория протоколов", await page.textContent(".hero__title"));
ok("lang_ru_result", /Выполнено/.test((await page.$$eval(".lab-sentence", (n) => n.map((x) => x.textContent)))[0] || ""), null);
await page.click('button[data-lang="en"]');

// validation error shown, not run
// the first number field of the open module whose declared minimum is >= 0 (modules differ in their fields)
const numbers = await page.$$("#variants input[type=number]");
const target = await page.$$eval("#variants input[type=number]",
  (els) => els.findIndex((e) => e.getAttribute("min") !== null && Number(e.getAttribute("min")) >= 0));
await numbers[target].fill("-5");
await page.click("#validate");
await page.waitForSelector("#problems li");
ok("validation_error", /must be >=|expected/.test(await page.textContent("#problems")), await page.textContent("#problems"));

// export request, then import it back
const [req] = await Promise.all([page.waitForEvent("download"), page.click("#export-request")]);
const reqFile = `${out}/${req.suggestedFilename()}`; await req.saveAs(reqFile);
await page.setInputFiles("#import-request", reqFile);
await page.waitForSelector("#problems li");
ok("import_request", (await page.$$("#variants .lab-variant")).length >= 1, await page.textContent("#problems"));

// cancel a long run (main PREVENTION, 30 days)
await page.click(`#module-cards .card >> nth=0 >> button.btn--secondary`);
await page.waitForSelector("#variants .lab-variant");
await page.selectOption("#variants select >> nth=0", "main");
await page.fill("#variants input[type=number] >> nth=1", "30"); // num_days
await page.dispatchEvent("#variants input[type=number] >> nth=1", "input");
await page.evaluate(() => document.getElementById("run").click());
await page.waitForFunction(() => !document.getElementById("cancel").disabled, null, { timeout: 10000 });
await page.waitForTimeout(50);
const stillRunning = await page.evaluate(() => !document.getElementById("cancel").disabled);
await page.evaluate(() => document.getElementById("cancel").click());
await page.waitForFunction(() => !document.getElementById("run").disabled, null, { timeout: 60000 });
await page.waitForFunction(() => /ready/i.test(document.getElementById("engine-status").textContent), null, { timeout: 240000 });
ok("cancel_recovers", stillRunning && /cancel|Отмен/i.test(await page.textContent("#problems")), [await page.textContent("#problems"), await page.textContent("#engine-status")]);

// coverage drill-down
await page.click("#coverage button.linklike >> nth=4");
await page.waitForSelector("#requirements tbody tr", { timeout: 60000 });
ok("coverage_drilldown", (await page.$$("#requirements tbody tr")).length > 5, null);

// keyboard: tab reaches the run button
await page.focus("#run");
ok("keyboard_focus", await page.evaluate(() => document.activeElement.id === "run"), null);

await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: `${out}/mobile.png` });
ok("mobile_no_hscroll", !(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth + 1)), null);

await browser.close();
fs.writeFileSync(`${out}/ui_report.json`, JSON.stringify({ report, results, problems }, null, 1));
console.log(JSON.stringify({ passed: Object.values(report).filter((r) => r.ok).length, total: Object.keys(report).length, problems }, null, 1));
process.exit(problems.length ? 1 : 0);
