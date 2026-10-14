const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl, createTestPage, rankingResult } = require('./ui-fixtures.cjs');

// Mock preview and search: keyboard checks never call live inference or save feedback.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const queries = [];
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({
      json: { enabled: false, configured: false, available: false },
    }));
    await page.route('**/api/agent/query/stream', route => {
      const { query } = route.request().postDataJSON();
      queries.push(query);
      return route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({
        type: 'result', data: { query, model: 'ui-test',
          interpretation: { origin_name: '주안역', destination_name: '병원',
            departure_time: null, profile: 'pedestrian', preferences: [] },
          resolved_origin: null, resolved_destination: null, result: rankingResult() },
      }) + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const input = page.getByRole('textbox', { name: '문장으로 경로 요청' });
    await input.press('Enter');
    assert.equal(queries.length, 0, 'Empty input must not search');
    await input.fill('주안역에서 병원까지');
    await input.press('Shift+Enter');
    await input.press('End');
    await page.keyboard.insertText('계단을 피해서 안내해줘.');
    assert.equal(await input.inputValue(), '주안역에서 병원까지\n계단을 피해서 안내해줘.');
    for (const extra of [{ isComposing: true }, { keyCode: 229 }, { repeat: true }]) {
      const prevented = await input.evaluate((element, extra) => {
        const event = new KeyboardEvent('keydown', { key: 'Enter', bubbles: true,
          cancelable: true, ...extra });
        element.dispatchEvent(event);
        return event.defaultPrevented;
      }, extra);
      assert.equal(prevented, !!extra.repeat);
      assert.equal(queries.length, 0, 'Composition and held Enter must not submit');
    }
    await input.press('Enter');
    await page.locator('#route-results .route-card').first().waitFor();
    assert.deepEqual(queries, ['주안역에서 병원까지\n계단을 피해서 안내해줘.']);
    assert.equal(await input.inputValue(), queries[0], 'Submit must not append a newline');
    assert.deepEqual(errors, []);
    console.log('AI keyboard: Enter search, Shift+Enter newline, IME, empty input and repeat passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
