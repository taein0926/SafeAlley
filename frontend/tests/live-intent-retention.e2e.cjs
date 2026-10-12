const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl, createTestPage } = require('./ui-fixtures.cjs');
const factors = ['distance', 'streetlight', 'cctv', 'safety', 'stairs', 'crossing', 'bridge', 'time'];

// Mocked preview endpoints only: no Jev payment and no Qwen/DB route search.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome', args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  let releaseSecond;
  let releaseFourth;
  let secondArrived;
  const heldResponse = new Promise(resolve => { releaseSecond = resolve; });
  const heldFreshResponse = new Promise(resolve => { releaseFourth = resolve; });
  const secondRequest = new Promise(resolve => { secondArrived = resolve; });
  try {
    const page = await createTestPage(browser);
    let calls = 0;
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: true, configured: true, available: true } }));
    await page.route('**/api/agent/intent-preview', async route => {
      const { query } = route.request().postDataJSON();
      const index = ++calls;
      if (index === 2) { secondArrived(); await heldResponse; }
      if (index === 4) await heldFreshResponse;
      const applied = index === 1 ? ['time', 'stairs'] : index === 2 ? ['time', 'stairs', 'cctv'] : index === 3 ? ['time', 'cctv'] : [];
      await route.fulfill({ json: { query, model: 'retention-test-fixture', conditions: factors.map(factor => ({ factor, state: applied.includes(factor) ? 'applied' : 'not_applied' })) } });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    const input = page.getByRole('textbox', { name: '문장으로 경로 요청' });
    const cards = page.getByRole('list', { name: '실시간 분석' });
    await input.fill('밤 10시에 계단을 피해서 ');
    await cards.getByRole('listitem', { name: '계단 회피: 적용', exact: true }).waitFor();
    await input.fill('밤 10시에 계단을 피해서 CCTV가 많은 길 ');
    await page.getByRole('status', { name: '조건 분석 진행 중', exact: true }).waitFor();
    assert.equal(await cards.getByRole('listitem', { name: '계단 회피: 적용', exact: true }).count(), 1);
    assert.equal(await cards.getByRole('listitem', { name: '시간대 고려: 적용', exact: true }).count(), 1);
    // Wait for the request to reach the fixture while retaining the accepted cards.
    let timeout;
    try {
      await Promise.race([secondRequest, new Promise((_, reject) => {
        timeout = setTimeout(() => reject(new Error('Second mocked preview did not arrive')), 30000);
      })]);
    } finally { clearTimeout(timeout); }
    assert.equal(calls, 2);
    assert.equal(await cards.getByRole('listitem', { name: '계단 회피: 적용', exact: true }).count(), 1);
    releaseSecond();
    await cards.getByRole('listitem', { name: 'CCTV 우선: 적용', exact: true }).waitFor();
    await input.fill('밤 10시에 계단은 피하지 않아도 돼. CCTV가 많은 길 ');
    assert.equal(await cards.getByRole('listitem', { name: '계단 회피: 적용', exact: true }).count(), 1);
    await cards.getByRole('listitem', { name: '계단 회피: 미적용', exact: true }).waitFor();
    assert.deepEqual(await cards.locator('.recommendation-badge').evaluateAll(elements => elements.map(el => el.getAttribute('aria-label').split(':')[0])), ['최단 거리', '가로등 우선', 'CCTV 우선', '안전시설', '계단 회피', '건널목 회피', '육교 우선', '시간대 고려']);
    assert.equal(await page.locator('.recommendation-badge-status, .live-preview-hint, .live-preview-notice').count(), 0);
    await input.fill('');
    assert.equal(await cards.count(), 0);
    await input.fill('계단을 ');
    assert.equal(await cards.getByRole('listitem', { name: '계단 회피: 분석 중', exact: true }).count(), 1);
    releaseFourth();
    await cards.getByRole('listitem', { name: '계단 회피: 미적용', exact: true }).waitFor();
    console.log(JSON.stringify({ result: 'passed', paid_api_calls: 0, retain_while_pending: true, withdrawal_updates: true, empty_input_resets: true }));
  } finally { releaseSecond(); releaseFourth(); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
