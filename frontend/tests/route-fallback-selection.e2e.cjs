const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { baseUrl, createTestPage, rankingResult } = require('./ui-fixtures.cjs');

// Mock inference and route responses; never write route selections or call Jev.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    let selectionWrites = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({
      json: { enabled: false, configured: false, available: false },
    }));
    await page.route('**/api/agent/route-selections', route => {
      selectionWrites++;
      return route.fulfill({ json: {} });
    });
    await page.route('**/api/agent/query/stream', route => {
      const { query } = route.request().postDataJSON();
      const base = rankingResult();
      const shortest = base.candidates.find(candidate => candidate.route_type === 'shortest');
      shortest.route.properties.stairs_segment_count = 1;
      shortest.route.properties.stairs_distance_m = 12;
      const result = { ...base, selected_route_type: null, compared_route_type: null,
        recommendation_status: 'no_supported_preferences',
        recommendation_reason: '요청한 회피 조건을 만족하는 경로가 없어 자동 추천을 보류했습니다.',
        recommendation_factors: [], candidates: [shortest],
        unsupported_preferences: [{ factor: 'stairs_distance_m', reason: 'No generated route satisfies this hard avoidance condition' }],
      };
      const interpretation = { origin_name: '출발 학교', destination_name: '도착 병원',
        departure_time: '22:00:00', profile: 'pedestrian',
        preferences: [{ factor: 'stairs_distance_m', direction: 'avoid', weight: 1 }] };
      return route.fulfill({ contentType: 'application/x-ndjson', body: JSON.stringify({ type: 'result',
        data: { query, model: 'ui-test', interpretation, resolved_origin: null, resolved_destination: null, result } }) + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill('밤 10시에 출발 학교에서 도착 병원까지 계단을 피해서 안내해줘.');
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    const card = page.locator('#route-results .route-card');
    await card.waitFor();
    assert.equal(await card.count(), 1);
    assert.equal(await card.getAttribute('aria-pressed'), 'true');
    assert.match(await card.getAttribute('class'), /route-card--active/);
    assert.equal(await card.locator('.route-swatch--active').count(), 1);
    assert.match(await card.innerText(), /최단경로/);
    assert.match(await page.locator('.route-review-warning').innerText(), /아래 경로는 최단 경로이며 맞춤 경로가 아닙니다\./);
    assert.equal(await card.locator('.recommendation-icons').count(), 0, 'Fallback must not claim the avoidance condition was applied');
    assert.equal(await page.locator('[data-route-cap="0"] path').first().getAttribute('fill'), '#0054bb');
    await page.locator('.route-map-sign').waitFor({ state: 'visible' });
    assert.equal(await page.locator('.route-map-sign > span').innerText(), '최단경로');
    const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../output/screenshots');
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'shortest-fallback-selected.png') });
    assert.equal(selectionWrites, 0, 'Visual default selection must not write feedback');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', shortest_selected: true, map_highlighted: true,
      warning_retained: true, selectionWrites, browserErrors: errors }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
