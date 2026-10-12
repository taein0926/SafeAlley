const assert = require("node:assert/strict");
const { chromium } = require("playwright");
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');

// Layout/state checks only: no paid inference or real route calculation.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: "chrome", args: ["--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    page.on("pageerror", error => errors.push(error.message));
    const factors = ["distance", "streetlight", "cctv", "safety", "stairs", "crossing", "bridge", "time"];
    let unavailable = false;
    let releasePreview;
    const previewGate = new Promise(resolve => { releasePreview = resolve; });
    await page.route("**/api/agent/intent-preview/status", route => route.fulfill({ json: { enabled: true, configured: true, available: true } }));
    await page.route("**/api/agent/intent-preview", async route => {
      await previewGate;
      if (unavailable) return route.fulfill({ status: 503, json: { detail: "UI test unavailable" } });
      const { query } = route.request().postDataJSON();
      await route.fulfill({ json: { query, model: "ui-test", conditions: factors.map(factor => ({ factor, state: ["streetlight", "stairs"].includes(factor) ? "applied" : "not_applied" })) } });
    });
    await page.route("**/api/agent/query/stream", route => route.fulfill({ contentType: "application/x-ndjson", body: JSON.stringify({ type: "error", detail: "UI test: no route calculation" }) + "\n" }));
    await page.goto(baseUrl, { waitUntil: "domcontentloaded" });
    const preview = page.locator("#route-search-panel .search-intent-preview");
    assert.equal(await preview.count(), 0);
    const query = page.getByRole("textbox", { name: "문장으로 경로 요청" });
    await query.fill("가로등이 많고 계단 없는 길");
    await preview.locator(".live-preview-dots").waitFor();
    assert.equal(await page.locator("#route-results").count(), 0);
    releasePreview();
    await page.getByText("요구사항 분석 완료", { exact: true }).waitFor();
    const layout = await preview.evaluate(element => {
      const badges = [...element.querySelectorAll(".recommendation-badge")];
      const grid = element.querySelector(".recommendation-icons").getBoundingClientRect();
      const input = document.querySelector(".ai-query textarea").getBoundingClientRect();
      const toolbar = document.querySelector(".search-mode-toolbar").getBoundingClientRect();
      return {
        labels: badges.map(e => e.lastElementChild.textContent),
        heights: badges.map(e => e.getBoundingClientRect().height),
        rows: [...new Set(badges.map(e => e.getBoundingClientRect().top))],
        gridHeight: grid.height,
        // Corner checks intentionally overhang; labels must still fit inside each card.
        fits: badges.every(e => {
          const card = e.getBoundingClientRect();
          const label = e.lastElementChild.getBoundingClientRect();
          return label.left >= card.left && label.right <= card.right;
        }),
        between: input.bottom <= element.getBoundingClientRect().top && grid.bottom <= toolbar.top,
        applied: badges.filter(e => e.dataset.applied === "true").length,
      };
    });
    assert.deepEqual(layout.labels, ["거리", "가로등", "CCTV", "안전시설", "계단", "건널목", "육교", "시간대"]);
    assert.equal(layout.rows.length, 2);
    assert.equal(layout.gridHeight, 56);
    assert(layout.heights.every(height => height === 26));
    assert(layout.fits && layout.between);
    assert.equal(layout.applied, 2);
    const checks = preview.locator('.condition-recognized-check');
    assert.equal(await checks.count(), 2);
    assert.equal(await preview.locator('[data-applied="false"] .condition-recognized-check').count(), 0);
    assert.equal(await checks.first().evaluate(element => getComputedStyle(element).color), 'rgb(211, 47, 47)');
    const checkStyle = await checks.first().evaluate(element => {
      const style = getComputedStyle(element);
      return { background: style.backgroundColor, top: style.top, right: style.right, width: style.width, height: style.height };
    });
    assert.deepEqual(checkStyle, { background: 'rgba(0, 0, 0, 0)', top: '-4px', right: '-3px', width: '15px', height: '15px' });
    assert(await page.locator('#route-search-panel').evaluate(element => element.scrollWidth <= element.clientWidth), 'Corner checks do not cause horizontal panel scrolling');
    await page.locator(".sidebar-primary").screenshot({ path: "output/ui-compact-intent.png" });
    await page.getByRole("button", { name: "길찾기", exact: true }).click();
    await preview.waitFor({ state: "detached" });
    await page.getByRole("button", { name: "길찾기", exact: true }).waitFor();
    await query.fill("");
    assert.equal(await preview.count(), 0);
    unavailable = true;
    await query.fill("CCTV가 많은 길");
    await page.getByText("요구사항 분석 불가", { exact: true }).waitFor();
    assert.equal(await preview.locator(".recommendation-badge").count(), 0);
    await page.getByRole("button", { name: "직접 설정", exact: true }).click();
    assert.equal(await preview.count(), 0);
    const inputHeights = await page.locator(".place-inputs .location-input").evaluateAll(elements => elements.map(e => e.getBoundingClientRect().height));
    assert(inputHeights.every(height => height === 40));
    await page.locator(".sidebar-primary").screenshot({ path: "output/ui-compact-direct.png" });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ layout, inputHeights, browserErrors: errors, result: "passed" }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
