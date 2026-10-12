const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');

// UI-only requests are intercepted: no actual Jev/LLM inference or route writes.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const result = { recommendation_id: null, selected_route_type: null, recommendation_status: 'no_supported_preferences', recommendation_reason: 'UI test', recommendation_notes: [], compared_route_type: null, recommendation_criteria: [], candidates: [], unsupported_preferences: [] };
    let fail = false;
    let releaseSearch;
    let searchStarted;
    let gate;
    let started;
    function deferSearch() {
      gate = new Promise(resolve => { releaseSearch = resolve; });
      started = new Promise(resolve => { searchStarted = resolve; });
    }
    deferSearch();
    await page.route('**/api/weather?**', route => {
      const time = new URL(route.request().url()).searchParams.get('departure_time');
      const date = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date());
      return route.fulfill({ json: { date, departure_time: time, forecast_status: 'available', solar: null, forecast: { temperature_c: 20, wind_speed_ms: 1.2, sky: 1, precipitation_type: 0 } } });
    });
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.route('**/api/places/resolve?**', route => route.fulfill({ json: { id: 1, name: new URL(route.request().url()).searchParams.get('name'), category: null, address: null, source: 'ui-test', latitude: 37.463, longitude: 126.68 } }));
    await page.route('**/api/agent/execute', async route => {
      searchStarted();
      await gate;
      return route.fulfill(fail ? { status: 400, json: { detail: 'UI test failure' } } : { json: result });
    });
    await page.route('**/api/agent/query/stream', async route => {
      searchStarted();
      await gate;
      const interpretation = { origin_name: '주안역', destination_name: '인하대학교', departure_time: '21:00', profile: 'pedestrian', preferences: [] };
      return route.fulfill({ contentType: 'application/x-ndjson', body: [
        { type: 'interpreted', data: interpretation },
        fail ? { type: 'error', detail: 'UI test failure' } : { type: 'result', data: { query: 'UI test', model: 'ui-test', interpretation, resolved_origin: null, resolved_destination: null, result } },
      ].map(event => JSON.stringify(event)).join('\n') + '\n' });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const heading = page.locator('#map-weather .weather-hud-heading');
    await heading.waitFor();
    assert.match((await heading.textContent()).trim(), /^현재 미추홀구 \d{2}\/\d{2} \d{2}:\d{2} 기준의 예보입니다$/);
    await page.locator('.weather-hud-values').waitFor();
    const weatherSurface = await page.locator('.search-weather').evaluate(element => {
      const style = getComputedStyle(element), line = getComputedStyle(element, '::before');
      return { background: style.backgroundColor, border: style.borderTopWidth,
        lineBorder: line.borderTopWidth, lineContent: line.content };
    });
    assert.equal(weatherSurface.background, 'rgba(0, 0, 0, 0)');
    assert.equal(weatherSurface.border, '0px');
    assert.equal(weatherSurface.lineBorder, '0px');
    assert.equal(weatherSurface.lineContent, 'none');
    async function assertWeatherGaps() {
      const gaps = await page.locator('.search-weather').evaluate(element => {
        const hud = element.querySelector('#map-weather').getBoundingClientRect();
        const panel = element.closest('#route-search-panel'), bounds = panel.getBoundingClientRect();
        const toolbar = panel.querySelector('.search-mode-toolbar').getBoundingClientRect();
        return { top: hud.top - toolbar.bottom,
          bottom: bounds.bottom - parseFloat(getComputedStyle(panel).borderBottomWidth) - hud.bottom };
      });
      assert(Math.abs(gaps.top - gaps.bottom) < 1, `Weather edge gaps: ${JSON.stringify(gaps)}`);
      assert(Math.abs(gaps.top - 10) < 1, 'Both weather edge gaps should be 10px');
      return gaps;
    }
    const weatherGaps = await assertWeatherGaps();
    const logo = page.getByRole('img', { name: '기상청', exact: true });
    await logo.waitFor();
    await logo.evaluate(image => image.decode());
    assert(await logo.evaluate(image => image.naturalWidth > 0));
    assert.equal(await logo.evaluate(image => getComputedStyle(image).height), '20px');
    assert.equal(await logo.evaluate(image => getComputedStyle(image.parentElement).marginRight), '8px');
    assert.equal(await page.locator('.weather-hud-values').evaluate(element => getComputedStyle(element).paddingTop), '4px');
    assert(await logo.evaluate(image => image.parentElement.nextElementSibling.classList.contains('weather-condition')));
    const rows = await page.locator('#map-weather').evaluate(element => {
      const heading = element.querySelector('.weather-hud-heading');
      const values = element.querySelector('.weather-hud-values');
      return { headingAlign: getComputedStyle(heading).textAlign, valuesAlign: getComputedStyle(values).textAlign,
        separators: [...values.childNodes].filter(node => node.nodeType === Node.TEXT_NODE).map(node => node.textContent),
        // A flex parent's inline-flex children are blockified in computed CSS.
        flexValues: [...values.children].every(child => getComputedStyle(child).display === 'flex'),
        verticalAlign: getComputedStyle(values).alignItems, horizontalAlign: getComputedStyle(values).justifyContent };
    });
    assert.equal(rows.headingAlign, 'center');
    assert.equal(rows.valuesAlign, 'center');
    assert.deepEqual(rows.separators, [' ', ' ', ' ']);
    assert(rows.flexValues);
    assert.equal(rows.verticalAlign, 'center');
    assert.equal(rows.horizontalAlign, 'center');
    await page.getByRole('button', { name: '직접 설정', exact: true }).click();
    await assertWeatherGaps();
    await page.getByRole('textbox', { name: '출발지', exact: true }).fill('주안역');
    await page.getByRole('textbox', { name: '도착지', exact: true }).fill('인하대학교');
    await page.getByRole('button', { name: /경로 기준/ }).click();
    await page.getByLabel('출발 시간', { exact: true }).fill('22:00');
    assert.match((await heading.textContent()).trim(), /^현재 /, 'Editing criteria alone does not apply requested weather');
    const initialHeading = await heading.textContent();
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await started;
    assert.equal(await heading.textContent(), initialHeading, 'Pending direct search keeps the current reference');
    releaseSearch();
    await page.waitForFunction(() => document.querySelector('.weather-hud-heading').textContent.includes('요청하신 미추홀구') && document.querySelector('.weather-hud-heading').textContent.includes('22:00'));
    const requestedFits = await heading.evaluate(element => element.scrollWidth <= element.clientWidth);
    assert(requestedFits, 'Reference sentence fits the narrow panel');
    const completedHeading = await heading.textContent();
    fail = true;
    deferSearch();
    await page.getByLabel('출발 시간', { exact: true }).fill('19:00');
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await started;
    assert.equal(await heading.textContent(), completedHeading);
    releaseSearch();
    await page.getByText('UI test failure', { exact: true }).waitFor();
    assert.equal(await heading.textContent(), completedHeading, 'Failed repeat search keeps the last completed reference');
    await page.reload({ waitUntil: 'domcontentloaded' });
    await heading.waitFor();
    assert.match((await heading.textContent()).trim(), /^현재 /);
    await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill('밤 9시에 주안역에서 인하대학교까지 안내해줘.');
    const aiInitialHeading = await heading.textContent();
    deferSearch();
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await started;
    assert.equal(await heading.textContent(), aiInitialHeading);
    releaseSearch();
    await page.getByText('UI test failure', { exact: true }).waitFor();
    assert.equal(await heading.textContent(), aiInitialHeading, 'An interpreted time followed by failure does not apply weather');
    fail = false;
    deferSearch();
    await page.getByRole('button', { name: '길찾기', exact: true }).click();
    await started;
    assert.equal(await heading.textContent(), aiInitialHeading);
    releaseSearch();
    await page.waitForFunction(() => document.querySelector('.weather-hud-heading').textContent.includes('요청하신 미추홀구') && document.querySelector('.weather-hud-heading').textContent.includes('21:00'));
    const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../output');
    fs.mkdirSync(output, { recursive: true });
    await page.locator('.search-weather').screenshot({ path: path.join(output, 'ui-weather-reference.png') });
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ rows, weatherGaps, directTime: '22:00', completedAiTime: '21:00', pendingAndFailedSearchPreserveWeather: true, requestedFits, browserErrors: errors, result: 'passed' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
