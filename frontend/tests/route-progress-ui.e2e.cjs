const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

// Mock the language/route response. Real local map assets are read; no model is called.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  let finishResponse;
  const held = new Promise(resolve => { finishResponse = resolve; });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: true, available: false } }));
    await page.route('**/api/agent/intent-preview', route => { throw new Error('Unexpected paid preview request'); });
    await page.route('**/api/agent/query/stream', async route => {
      await held;
      const query = route.request().postDataJSON().query;
      const interpretation = { origin_name: '주안역', destination_name: '인천사랑병원', departure_time: '22:00:00', profile: 'pedestrian', preferences: [{ factor: 'streetlight_score', direction: 'maximize', weight: 1 }] };
      const result = { tool_call: { tool: 'rank_routes', arguments: {} }, recommendation_id: null,
        selected_route_type: null, selected_route: null, recommendation_status: 'no_supported_preferences',
        recommendation_reason: '화면 검증용 응답', recommendation_notes: [], recommendation_factors: [],
        recommendation_conditions: [], compared_route_type: null, recommendation_criteria: [], candidates: [], unsupported_preferences: [] };
      const events = [{ type: 'interpreted', data: interpretation },
        ...Array.from({ length: 18 }, (_, index) => ({ type: 'route_progress', data: {
          id: `test-step-${index}`, message: `화면 검증 단계 ${index + 1}: 경로 조건 비교 내용을 표시했어요.`, state: 'completed',
        } })),
        { type: 'route_progress', data: { id: 'test-complete', message: '화면 검증이 완료됐어요.', state: 'completed' } },
        { type: 'result', data: { query, model: 'ui-test-fixture', interpretation, resolved_origin: null, resolved_destination: null, result } }];
      await route.fulfill({ contentType: 'application/x-ndjson', body: events.map(event => JSON.stringify(event)).join('\n') + '\n' });
    });
    await page.goto(process.env.E2E_BASE_URL || 'http://127.0.0.1:3002/', { waitUntil: 'domcontentloaded' });
    await page.locator('.route-form button[type=submit]').click();
    await page.getByRole('heading', { name: 'AI가 길을 찾고 있어요', exact: true }).waitFor();
    const mouth = page.locator('.route-progress-avatar--speaking .route-progress-mouth');
    assert.equal(await mouth.count(), 1);
    assert.equal(await mouth.evaluate(element => getComputedStyle(element).animationName), 'route-progress-mouth-talk');
    assert.equal(await page.locator('.route-progress-avatar').first().innerText(), '');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    assert.equal(await mouth.evaluate(element => getComputedStyle(element).animationName), 'none');
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    const tileResponse = page.waitForResponse(async response => /\/api\/streetlight-heatmap\/[a-f0-9]+\/\d+\/\d+\/\d+\.png$/.test(response.url()) && response.status() === 200 && (await response.body()).length > 1000, { timeout: 60000 });
    finishResponse();
    await page.getByText('화면 검증이 완료됐어요.', { exact: true }).waitFor();
    const scrollPane = page.getByRole('region', { name: '경로 검색 처리 내용' });
    await page.waitForFunction(() => {
      const pane = document.querySelector('.sidebar-scroll');
      return pane && pane.scrollTop > 0 && pane.scrollHeight - pane.clientHeight - pane.scrollTop <= 1;
    });
    const latest = page.locator('.route-progress-message').last();
    const paneBounds = await scrollPane.boundingBox();
    const latestBounds = await latest.boundingBox();
    assert(latestBounds.y >= paneBounds.y && latestBounds.y + latestBounds.height <= paneBounds.y + paneBounds.height + 1);
    assert.equal(await page.getByRole('textbox', { name: 'AI 경로 요청' }).isVisible(), true);
    assert.equal(await page.locator('.route-form button[type=submit]').isVisible(), true);
    const inputBounds = await page.getByRole('textbox', { name: 'AI 경로 요청' }).boundingBox();
    const buttonBounds = await page.locator('.route-form button[type=submit]').boundingBox();
    assert(inputBounds.y >= 0 && inputBounds.y + inputBounds.height <= paneBounds.y + 1);
    assert(buttonBounds.y >= 0 && buttonBounds.y + buttonBounds.height <= paneBounds.y + 1);
    assert.equal(await page.evaluate(() => window.scrollY), 0);
    await page.getByRole('img', { name: /등록된 가로등의 상대 밀집도/ }).waitFor();
    await tileResponse;
    await page.waitForTimeout(1000); // Give decoded PNG textures a bounded render interval.
    assert.equal(await page.locator('.route-progress-avatar--speaking').count(), 0);
    assert.equal(await page.locator('.route-progress-mouth').first().evaluate(element => getComputedStyle(element).animationName), 'none');
    assert.equal(await page.getByText('계산값 자세히 보기', { exact: true }).count(), 0);
    assert.equal(await page.getByText('가로등·CCTV는 등록 위치 기반 지표이며 실제 밝기·안전도를 뜻하지 않습니다.', { exact: true }).count(), 0);
    const output = path.resolve(__dirname, '../../../output/screenshots');
    fs.mkdirSync(output, { recursive: true });
    await page.screenshot({ path: path.join(output, 'safealley-speaking-lips-and-heatmap-20261007.png') });
    // Once complete, unrelated React updates must not pull the reader back down.
    await scrollPane.evaluate(element => { element.scrollTop = 0; });
    await page.getByRole('textbox', { name: 'AI 경로 요청' }).fill('다음 질문을 작성합니다.');
    await page.waitForTimeout(200);
    assert.equal(await scrollPane.evaluate(element => element.scrollTop), 0);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', model_calls: 0, scroll_to_latest_on_completion: true, fixed_inputs_visible: true, manual_scroll_preserved: true, speaking_lips: true, reduced_motion: true, stops_on_completion: true, removed_note_and_details: true, night_heatmap_tile: true }));
  } finally { finishResponse(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
