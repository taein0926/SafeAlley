const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { baseUrl, createTestPage, rankingResult } = require('./ui-fixtures.cjs');

// Use the real local DB candidate coordinates; mock inference/ranking only.
// No paid preview or recommendation writes. Real Gemma is checked separately.
(async () => {
  const response = await fetch(new URL('/api/places/resolve?name=' + encodeURIComponent('실버타운'), baseUrl));
  assert.equal(response.status, 400);
  const { detail } = await response.json();
  assert.equal(detail.code, 'place_selection_required');
  const candidates = detail.candidates;
  assert.equal(candidates.length, 7);
  const query = '밤 8시에 서화초에서 실버타운까지 가로등, CCTV 많은 길로 안내해줘. 계단도 피해서 안내해.';
  const interpretation = { origin_name: '서화초', destination_name: '실버타운', departure_time: '20:00:00', profile: 'pedestrian', preferences: [] };
  const requests = [];
  const resolves = [];
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (new URL(request.url()).pathname === '/api/places/resolve') resolves.push(new URL(request.url()).searchParams.get('name'));
    });
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.route('**/api/agent/query/stream', route => {
      const input = route.request().postDataJSON();
      requests.push(input);
      const events = [{ type: 'interpreted', data: interpretation }];
      if (requests.length === 1) events.push({ type: 'error', detail: { ...detail, target: 'destination' } });
      else {
        assert.deepEqual(input.destination, { latitude: candidates[2].latitude, longitude: candidates[2].longitude });
        events.push({ type: 'result', data: { query, model: 'ui-test', interpretation, resolved_origin: null, resolved_destination: null, result: rankingResult() } });
      }
      return route.fulfill({ contentType: 'application/x-ndjson', body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill(query);
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    const choices = page.getByRole('region', { name: '장소 후보' });
    await choices.getByText('도착지를 선택하세요', { exact: true }).waitFor();
    assert.deepEqual(await choices.locator('.place-candidate-letter').allTextContents(), ['A','B','C','D','E','F','G']);
    assert.equal(await choices.locator('.place-candidate-preview').count(), 0);
    await page.waitForFunction(() => {
      const cards = [...document.querySelectorAll('.place-candidate-pin')];
      const sidebar = document.querySelector('.sidebar-primary').getBoundingClientRect();
      const boxes = cards.map(card => card.getBoundingClientRect());
      return boxes.length === 7 && cards.every(card => getComputedStyle(card).visibility === 'visible')
        && boxes.every(box => box.x > sidebar.right && box.y >= 0 && box.right <= innerWidth && box.bottom <= innerHeight)
        && boxes.every((box, index) => boxes.slice(index + 1).every(other => box.right <= other.x || other.right <= box.x || box.bottom <= other.y || other.bottom <= box.y));
    }, { timeout: 30000 });
    assert.equal(requests.length, 1, 'Wait for explicit candidate choice');
    const pinOcclusion = await page.locator('.route-pins').evaluate(layer => {
      const sidebar = document.querySelector('.sidebar-primary');
      const box = sidebar.getBoundingClientRect();
      // Same real pin styling, positioned behind the search panel to test stacking.
      const probe = layer.querySelector('.place-candidate-pin').cloneNode(true);
      probe.removeAttribute('data-map-candidate');
      probe.style.transform = `translate(${box.x + 80}px, ${box.y + 40}px)`;
      probe.style.visibility = 'visible';
      layer.appendChild(probe);
      const hit = document.elementFromPoint(box.x + 95, box.y + 56);
      const occluded = !probe.contains(hit) && sidebar.contains(hit);
      probe.remove();
      return occluded;
    });
    assert(pinOcclusion, 'Search panel visually covers pins and receives pointer input');
    await page.waitForTimeout(8000); // Let imagery/building requests settle after the camera flight.
    assert.equal(await page.locator('.place-candidate-caption, .place-candidate-dot, .place-candidate-link').count(), 0, 'No map cards, circle dots or connecting lines');
    assert.deepEqual(await page.locator('.place-candidate-pin text').allTextContents(), ['A','B','C','D','E','F','G']);
    // Every pin must be directly clickable, even among nearby buildings.
    assert.deepEqual(await page.locator('.place-candidate-pin').evaluateAll(pins => pins.map(pin => {
      const box = pin.getBoundingClientRect();
      return pin.contains(document.elementFromPoint(box.x + box.width / 2, box.y + 16));
    })), Array(7).fill(true));
    const accent = await page.locator('.route-pins').evaluate(layer => ({
      border: getComputedStyle(layer.querySelector('.place-candidate-pin path')).stroke,
      borderWidth: getComputedStyle(layer.querySelector('.place-candidate-pin path')).strokeWidth,
      pin: getComputedStyle(layer.querySelector('.place-candidate-pin path')).fill,
      pinText: getComputedStyle(layer.querySelector('.place-candidate-pin text')).fill,
    }));
    assert.equal(accent.border, 'rgb(23, 105, 223)');
    assert.equal(accent.pin, 'rgb(255, 255, 255)');
    assert.equal(accent.pinText, accent.border);
    assert.equal(accent.borderWidth, '2px');
    const nightAccent = await page.locator('.route-pins').evaluate(layer => {
      const shell = layer.closest('.app-shell');
      const theme = shell.dataset.theme;
      shell.dataset.theme = 'night';
      const colors = [getComputedStyle(layer.querySelector('.place-candidate-pin path')).stroke,
        getComputedStyle(layer.querySelector('.place-candidate-pin path')).fill,
        getComputedStyle(layer.querySelector('.place-candidate-pin text')).fill];
      shell.dataset.theme = theme;
      return colors;
    });
    assert.deepEqual(nightAccent, [accent.border, accent.pin, accent.pinText]);
    const output = path.resolve(__dirname, '../../output/screenshots');
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'silver-town-all-candidates.png') });
    await page.getByRole('button', { name: /^C 실버타운 .* 도착지로 선택$/ }).click();
    await page.locator('#route-results .route-card').first().waitFor();
    assert.equal(await choices.count(), 0);
    assert.equal(await page.locator('.place-candidate-pin').count(), 0);
    assert.equal(requests.length, 2);
    assert.deepEqual(resolves, ['서화초'], 'The selected destination must not be resolved by name again');
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', candidates: 7, labels: 'A-G', all_visible: true, no_overlap: true, map_click_selects_exact_coordinates: true, destination_reresolve: false, browserErrors: errors }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
