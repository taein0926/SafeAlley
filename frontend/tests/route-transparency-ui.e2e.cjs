const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');

// Exercise the real result-card markup with mock routes; no inference or DB writes.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.route('**/api/places/resolve?**', route => route.fulfill({ json: { name: new URL(route.request().url()).searchParams.get('name'), latitude: 37.46, longitude: 126.68, source: 'ui-test', address: null, category: null } }));
    const candidate = (type, middle) => ({ route_type: type, preference_score: 80, metrics: {}, route: {
      type: 'Feature', geometry: { type: 'LineString', coordinates: [[126.68, 37.46], middle, [126.683, 37.466]] },
      properties: { route_type: type, total_distance_m: type === 'custom' ? 740 : 620, total_cost: 800, average_safety_score: 70, stairs_segment_count: 0, stairs_distance_m: 0, total_crosswalk_count: 2, pedestrian_bridge_count: 0, intersection_data_available: true, sidewalk_coverage_percent: 100, max_slope_percent: null, slope_coverage_percent: 0, road_segments: [] },
    } });
    await page.route('**/api/agent/execute', route => route.fulfill({ json: {
      recommendation_id: null, selected_route_type: 'custom', recommendation_status: 'ready', recommendation_reason: null, recommendation_notes: [], recommendation_factors: ['safety'], compared_route_type: 'shortest', recommendation_criteria: [], unsupported_preferences: [],
      candidates: [candidate('custom', [126.685, 37.463]), candidate('shortest', [126.681, 37.463])],
    } }));
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '직접 설정', exact: true }).click();
    await page.getByRole('textbox', { name: '출발지', exact: true }).fill('주안역');
    await page.getByRole('textbox', { name: '도착지', exact: true }).fill('인하대학교');
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await page.locator('#route-results .route-card').first().waitFor();
    const detailsLayout = await page.locator('#route-results .route-card-details').evaluateAll(elements => elements.map(element => ({
      followsMetrics: element.previousElementSibling?.classList.contains('route-card-primary'),
      border: getComputedStyle(element).borderTopWidth,
      padding: getComputedStyle(element).paddingTop,
    })));
    for (const details of detailsLayout) {
      assert.equal(details.followsMetrics, true);
      assert.equal(details.border, '0px');
      assert.equal(details.padding, '0px');
    }
    const styles = await page.locator('#route-results .route-card').evaluateAll(cards => cards.map(card => {
      const style = getComputedStyle(card);
      const parents = [];
      for (let parent = card.parentElement; parent; parent = parent.parentElement) {
        parents.push({ name: parent.id || parent.className || parent.tagName, background: getComputedStyle(parent).backgroundColor, blur: getComputedStyle(parent).backdropFilter });
      }
      return { active: card.classList.contains('route-card--active'), background: style.backgroundColor, blur: style.backdropFilter, opacity: style.opacity, textColor: getComputedStyle(card.querySelector('.route-card-primary')).color, distanceColor: getComputedStyle(card.querySelector('.route-card-primary > span')).color, detailsColor: getComputedStyle(card.querySelector('.route-card-details')).color, parents };
    }));
    console.log(JSON.stringify({ styles, errors }));
    if (process.env.E2E_INSPECT_ONLY !== '1') {
      for (const style of styles) {
        assert.equal(style.background, style.active ? 'rgba(242, 247, 255, 0.58)' : 'rgba(255, 255, 255, 0.5)');
        assert.equal(style.blur, 'blur(1px)');
        assert.equal(style.opacity, '1');
        assert.equal(style.textColor, 'rgb(32, 39, 53)');
        assert.equal(style.distanceColor, 'rgb(0, 0, 0)');
        assert.equal(style.detailsColor, 'rgb(0, 0, 0)');
      }
      const badges = await page.locator('#route-results .recommendation-badge').evaluateAll(elements => elements.map(element => ({
        applied: element.dataset.applied === 'true', background: getComputedStyle(element).backgroundColor,
      })));
      assert(badges.some(badge => badge.applied) && badges.some(badge => !badge.applied));
      for (const badge of badges) assert.equal(badge.background, badge.applied ? 'rgba(230, 239, 255, 0.7)' : 'rgba(242, 244, 247, 0.7)');
    }
    // Let the camera flight and background tiles settle before visual inspection.
    await page.waitForTimeout(8000);
    await page.screenshot({ path: `output/route-transparency-${process.env.E2E_INSPECT_ONLY === '1' ? 'before' : 'after'}.png` });
    assert.deepEqual(errors, []);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
