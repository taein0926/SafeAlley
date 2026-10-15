const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');

// Verify the locally running production UI and existing local map/weather API.
// Preview is disabled in this test: no paid Jev inference or route/selection writes.
const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../output');
const app = fs.readFileSync(path.resolve(__dirname, '../src/App.tsx'), 'utf8');
const examples = app.match(/const SEARCH_EXAMPLES = \[([\s\S]*?)\] as const;/)[1].match(/"[^"\n]+"/g).map(JSON.parse);

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    let routeWrites = 0;
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => { if (request.method() === 'POST' && /\/api\/(agent\/query|routes)/.test(request.url())) routeWrites++; });
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const sidebar = page.locator('.sidebar-primary');
    const picker = page.getByRole('button', { name: '예시', exact: true });
    const grid = page.getByRole('group', { name: '예시 경로 검색' });
    const input = page.getByRole('textbox', { name: '문장으로 경로 요청' });
    await sidebar.waitFor();
    const actionWidths = await page.locator('.search-mode-toolbar').evaluate(toolbar => {
      const measure = element => ({
        example: element.querySelector('.example-picker-trigger').getBoundingClientRect().width,
        search: element.querySelector('.search-button').getBoundingClientRect().width,
      });
      const current = measure(toolbar);
      const old = toolbar.cloneNode(true);
      old.style.cssText = `position:absolute;visibility:hidden;pointer-events:none;width:${toolbar.getBoundingClientRect().width}px`;
      toolbar.parentElement.appendChild(old);
      old.querySelector('.example-picker-trigger').firstChild.textContent = '예시 선택 ';
      const previous = measure(old);
      old.remove();
      return { current, previous };
    });
    assert(actionWidths.previous.example - actionWidths.current.example >= 20);
    assert(Math.abs((actionWidths.current.search - actionWidths.previous.search)
      - (actionWidths.previous.example - actionWidths.current.example)) < 1, JSON.stringify(actionWidths));
    assert.equal((await sidebar.boundingBox()).width, 328);
    assert.equal(await grid.count(), 0);
    assert.equal(await page.locator('.sidebar-header #map-weather').count(), 0);
    await page.locator('.search-weather .weather-condition').waitFor();
    assert.equal(await page.locator('.search-weather #map-weather').count(), 1);
    const weatherFits = await page.locator('#map-weather').evaluate(e => e.scrollWidth <= e.clientWidth);
    assert(weatherFits, 'Weather must fit the narrowed search panel');

    await picker.click();
    assert.equal(await picker.getAttribute('aria-expanded'), 'true');
    const buttons = grid.getByRole('button');
    assert.equal(await buttons.count(), 4);
    assert.equal(await buttons.nth(0).textContent(), '가로등 · CCTV · 건널목');
    assert.equal(await buttons.nth(2).textContent(), '종합 조건');
    assert.equal(await buttons.nth(3).textContent(), '가로등 · 계단');
    const labelsFit = await buttons.evaluateAll(elements => elements.every(element => element.scrollWidth <= element.clientWidth));
    assert(labelsFit, 'Example labels fit the narrowed two-column popup');
    const boxes = await Promise.all([0, 1, 2, 3].map(index => buttons.nth(index).boundingBox()));
    assert.equal(boxes[0].y, boxes[1].y);
    assert.equal(boxes[2].y, boxes[3].y);
    assert(boxes[0].x < boxes[1].x && boxes[2].x < boxes[3].x);
    const menu = await grid.boundingBox();
    const trigger = await picker.boundingBox();
    const search = await page.locator('#route-search-panel').boundingBox();
    assert(menu.y + menu.height < trigger.y, 'Examples open above the selector');
    assert(menu.y >= search.y && menu.x >= search.x && menu.x + menu.width <= search.x + search.width, 'Popup is not clipped');
    await page.screenshot({ path: path.join(output, 'ui-example-picker-open.png') });
    await page.keyboard.press('Escape');
    assert.equal(await grid.count(), 0);
    assert.equal(await picker.getAttribute('aria-expanded'), 'false');
    await picker.click();
    await page.getByRole('button', { name: '2D 지도', exact: true }).click();
    assert.equal(await grid.count(), 0);

    // Record actual React value writes: a completed value alone could hide animation.
    await input.evaluate(element => {
      window.exampleInputValues = [];
      const descriptor = Object.getOwnPropertyDescriptor(element, 'value')
        || Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, 'value');
      Object.defineProperty(element, 'value', { ...descriptor,
        set(value) {
          if (this.id === 'ai-route-query') window.exampleInputValues.push(value);
          descriptor.set.call(this, value);
        },
      });
    });
    for (let index = 0; index < examples.length; index++) {
      await picker.click();
      await page.evaluate(() => { window.exampleInputValues = []; });
      await grid.getByRole('button').nth(index).click();
      assert.equal(await grid.count(), 0);
      assert.equal(await input.inputValue(), examples[index]);
      assert.deepEqual(await page.evaluate(() => window.exampleInputValues), [examples[index]], 'Example must arrive in one complete write');
      assert.equal(await input.evaluate(element => document.activeElement === element), true);
      assert.equal(await input.isEditable(), true);
      assert.equal(routeWrites, 0, 'Selecting an example must not submit a route');
    }
    await input.fill('바로 수정한 문장');
    await page.waitForTimeout(100);
    assert.equal(await input.inputValue(), '바로 수정한 문장', 'No timer may overwrite manual edits');
    await input.fill('');
    const view3d = page.getByRole('button', { name: '3D 지도', exact: true });
    const view2d = page.getByRole('button', { name: '2D 지도', exact: true });
    await view3d.click();
    assert.equal(await view3d.getAttribute('aria-pressed'), 'true');
    assert.equal(await view2d.getAttribute('aria-pressed'), 'false');
    await view2d.click();
    assert.equal(await view2d.getAttribute('aria-pressed'), 'true');
    await page.getByRole('button', { name: '직접 설정', exact: true }).click();
    await picker.click();
    assert.equal(await grid.getByRole('button').count(), 4);
    await page.keyboard.press('Escape');
    await picker.click();
    await grid.getByRole('button').nth(2).click();
    assert.equal(await input.inputValue(), examples[2]);
    assert.equal(await input.evaluate(element => document.activeElement === element), true, 'Example selected in direct mode focuses the new AI input');
    assert.equal(routeWrites, 0);
    await picker.click();
    await page.getByRole('button', { name: '검색·결과·상세 패널 접기', exact: true }).click();
    await page.getByRole('button', { name: '검색·결과·상세 패널 열기', exact: true }).click();
    assert.equal(await grid.count(), 0);
    assert.equal(await picker.getAttribute('aria-expanded'), 'false');
    await page.screenshot({ path: path.join(output, 'ui-search-weather-after.png') });
    assert.deepEqual(errors, [], 'No browser runtime errors');
    console.log(JSON.stringify({ sidebarWidth: 328, examples: examples.length, grid: '1 2 / 3 4', labelsFit, weatherFits, routeWrites, browserErrors: errors, result: 'passed' }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
