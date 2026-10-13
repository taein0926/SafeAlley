const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { baseUrl, createTestPage, rankingResult } = require('./ui-fixtures.cjs');

// Mock inference/routing, not UI behavior. No DB writes or paid preview calls.
const query = '서화초에서 인천대까지 가로등 많고 cctv 많은 길로 안내해. 계단은 피했으면 하고 밤 8시에 갈거야.';
const interpretation = { origin_name: '서화초', destination_name: '인천대',
  departure_time: '20:00:00', profile: 'pedestrian', preferences: [
    { factor: 'streetlight_score', direction: 'maximize', weight: 1 },
    { factor: 'cctv_score', direction: 'maximize', weight: 1 },
    { factor: 'stairs_distance_m', direction: 'avoid', weight: 1 },
  ] };
const origin = { name: '서화초등학교', source: 'test', category: 'school',
  address: '인천광역시 미추홀구 도화동', latitude: 37.466, longitude: 126.67 };
const campuses = ['112-19', '995'].map((lot, index) => ({ name: '인천대학교',
  source: 'molit-gis-building', category: 'building', address: `인천광역시 미추홀구 도화동 ${lot}`,
  latitude: 37.45 + index * .005, longitude: 126.65 + index * .005 }));

(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    const requests = [];
    const buildingRequests = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/buildings') buildingRequests.push(request.url());
    });
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({
      json: { enabled: false, configured: false, available: false },
    }));
    await page.route('**/api/places/resolve?**', route => {
      assert.equal(new URL(route.request().url()).searchParams.get('name'), '서화초');
      return route.fulfill({ json: origin });
    });
    await page.route('**/api/agent/query/stream', route => {
      const request = route.request().postDataJSON();
      requests.push(request);
      assert.equal(request.query, query);
      const events = [{ type: 'interpreted', data: interpretation }];
      if (requests.length === 1) {
        assert.equal(request.destination, undefined);
        events.push({ type: 'error', detail: { code: 'place_selection_required',
          message: '이름과 주소를 확인하고 선택해 주세요.', place_name: '인천대',
          target: 'destination', candidates: campuses } });
      } else {
        assert.deepEqual(request.origin, { latitude: origin.latitude, longitude: origin.longitude });
        assert.deepEqual(request.destination, { latitude: campuses[1].latitude, longitude: campuses[1].longitude });
        events.push({ type: 'result', data: { query, model: 'ui-test', interpretation,
          resolved_origin: null, resolved_destination: null, result: rankingResult() } });
      }
      return route.fulfill({ contentType: 'application/x-ndjson',
        body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const input = page.getByRole('textbox', { name: '문장으로 경로 요청' });
    await input.fill(query);
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    const choices = page.getByRole('region', { name: '장소 후보' });
    await choices.getByText('도착지를 선택하세요', { exact: true }).waitFor();
    assert.equal(await choices.locator('.place-candidate-select').count(), 2);
    assert.equal(await choices.getByRole('button', { name: /위치 보기/ }).count(), 2);
    assert.equal(await choices.getByText('선택', { exact: true }).count(), 0);
    assert.equal(await choices.getByText('위치 보기', { exact: true }).count(), 0);
    const rows = await choices.locator('li').evaluateAll(elements => elements.map(row => {
      const selection = row.querySelector('.place-candidate-select');
      const preview = row.querySelector('.place-candidate-preview');
      const left = selection.getBoundingClientRect();
      const right = preview.getBoundingClientRect();
      return { gap: getComputedStyle(row).gap, border: getComputedStyle(row).borderTopWidth,
        divider: getComputedStyle(preview).borderLeftWidth, previewWidth: right.width,
        separation: right.left - left.right, previewText: preview.innerText.trim(),
        nestedButtons: row.querySelectorAll('button button').length };
    }));
    for (const row of rows) {
      assert.equal(row.gap, '0px');
      assert.equal(row.border, '1px');
      assert.equal(row.divider, '1px');
      assert.equal(row.previewWidth, 44);
      assert.equal(row.separation, 0);
      assert.equal(row.previewText, '');
      assert.equal(row.nestedButtons, 0);
    }
    assert.equal(await page.getByRole('alert').count(), 0, 'Candidate selection is not a search failure');
    assert.equal(await page.getByText('경로 검색을 마치지 못했어요', { exact: true }).count(), 0);
    assert.equal(requests.length, 1, 'Do not route before user chooses a campus');
    assert.equal(await choices.getByText(/인하대학교/).count(), 0);
    const target = campuses[0];
    const cameraRequest = page.waitForRequest(request => {
      const url = new URL(request.url());
      if (url.pathname !== '/api/buildings') return false;
      const bbox = url.searchParams.get('bbox')?.split(',').map(Number);
      return bbox && bbox[0] <= target.longitude && bbox[2] >= target.longitude
        && bbox[1] <= target.latitude && bbox[3] >= target.latitude
        // Building requests use 0.004-degree cache tiles and may batch
        // several columns beyond the neighborhood preview rectangle.
        && bbox[2] - bbox[0] < .04 && bbox[3] - bbox[1] < .025;
    }, { timeout: 30000 });
    await choices.getByRole('button', { name: /112-19 위치 보기/ }).click();
    await cameraRequest.catch(async error => {
      console.error(JSON.stringify({ buildingRequests, browserErrors: errors }));
      const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../output/screenshots');
      fs.mkdirSync(output, { recursive: true });
      await page.screenshot({ path: path.join(output, 'place-preview-debug.png') });
      throw error;
    });
    const marker = page.locator('.place-preview-marker');
    await marker.waitFor({ state: 'visible' });
    assert.equal(await marker.locator('strong').innerText(), target.name);
    assert.equal(await marker.locator('.place-preview-caption span').innerText(), target.address);
    assert.equal(await choices.locator('.place-candidate-preview circle').first().getAttribute('r'), '6', 'Use a magnifier, not a route endpoint pin');
    await page.waitForFunction(() => {
      const canvas = document.querySelector('.cesium-widget canvas')?.getBoundingClientRect();
      const dot = document.querySelector('.place-preview-dot')?.getBoundingClientRect();
      return canvas && dot && Math.abs(dot.x + dot.width / 2 - canvas.x - canvas.width / 2) < 30
        && Math.abs(dot.y + dot.height / 2 - canvas.y - canvas.height / 2) < 30;
    });
    assert.equal(requests.length, 1, 'Location preview must not start route calculation');
    assert.equal(await choices.locator('.place-candidate-select').count(), 2, 'Preview must leave candidates available');
    assert.equal(await input.inputValue(), query);
    const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../output/screenshots');
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'place-campus-candidates.png') });
    await choices.locator('.place-candidate-select').filter({ hasText: '도화동 995' }).click();
    await page.waitForFunction(() => !document.querySelector('.place-candidates')
      && document.querySelector('.route-card'));
    await marker.waitFor({ state: 'hidden' });
    assert.equal(requests.length, 2);
    assert.equal(await input.inputValue(), query);
    assert.equal(await page.getByRole('button', { name: '직접 설정', exact: true }).isVisible(), true);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', campus_choice: true, location_preview_moves_camera_only: true, preview_name_address: true, original_query_preserved: true,
      selected_coordinates_sent: true, no_silent_inha_fallback: true, browser_errors: errors }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
