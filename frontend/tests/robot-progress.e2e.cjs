const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');

// Scope: robot/blue-check rendering only. No paid inference or routing.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  let finish;
  const held = new Promise(resolve => { finish = resolve; });
  try {
    const page = await createTestPage(browser);
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.route('**/api/agent/intent-preview', () => { throw new Error('Unexpected paid preview'); });
    await page.route('**/api/agent/query/stream', async route => {
      await held;
      const interpretation = { origin_name: '주안역', destination_name: '병원', departure_time: '22:00:00', profile: 'pedestrian', preferences: [] };
      const result = { tool_call: { tool: 'rank_routes', arguments: {} }, recommendation_id: null, selected_route_type: null, selected_route: null,
        recommendation_status: 'no_supported_preferences', recommendation_reason: 'UI fixture', recommendation_notes: [], recommendation_factors: [],
        recommendation_conditions: [], compared_route_type: null, recommendation_criteria: [], candidates: [], unsupported_preferences: [] };
      await route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({ type: 'interpreted', data: interpretation }) + '\n' +
        JSON.stringify({ type: 'result', data: { query: route.request().postDataJSON().query, model: 'fixture', interpretation, resolved_origin: null, resolved_destination: null, result } }) + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill('밤 10시에 주안역에서 병원까지 안내해줘');
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await page.locator('.route-progress-robot').waitFor();
    const eyes = page.locator('.route-progress-robot-eyes');
    const dots = page.locator('.route-progress-thought-dot');
    assert.equal(await dots.count(), 3);
    assert.equal(await eyes.evaluate(e => getComputedStyle(e).animationName), 'route-progress-robot-blink');
    assert.equal(await page.locator('.route-progress-robot-head').evaluate(e => getComputedStyle(e).animationName), 'route-progress-robot-think');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    assert.equal(await eyes.evaluate(e => getComputedStyle(e).animationName), 'none');
    assert.equal(await dots.first().evaluate(e => getComputedStyle(e).animationName), 'none');
    finish();
    await page.locator('.route-progress-check').first().waitFor();
    assert.equal(await page.locator('.route-progress-robot').count(), 0);
    assert.equal(await page.locator('.route-progress-check').first().evaluate(e => getComputedStyle(e).color), 'rgb(23, 105, 223)');
    console.log(JSON.stringify({ result: 'passed', paid_calls: 0, robot_blink_and_motion: true, reduced_motion: true, blue_check: true }));
  } finally { finish(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
