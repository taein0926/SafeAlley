const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl } = require('./ui-fixtures.cjs');

// Exercise the actual first-session modal; no AI, paid preview or route writes.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    const intro = page.getByRole('dialog', { name: '안전 골목길', exact: true });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await intro.waitFor();
    // OSM and fire-service logos are decorative (alt="") next to their labels.
    const logos = intro.locator('img');
    assert.equal(await logos.count(), 8);
    for (const logo of await logos.all()) {
      await logo.evaluate(image => image.decode());
      assert(await logo.evaluate(image => image.naturalWidth > 0));
    }
    await page.getByRole('button', { name: '서비스 소개 닫기', exact: true }).click();
    await intro.waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => sessionStorage.getItem('safealley.welcome.dismissed.v1')), '1');
    await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill('주안역에서 병원까지');
    await page.reload({ waitUntil: 'domcontentloaded' });
    assert.equal(await intro.count(), 0, 'Reload in this session does not reopen the intro');
    await page.evaluate(() => sessionStorage.removeItem('safealley.welcome.dismissed.v1'));
    await page.reload({ waitUntil: 'domcontentloaded' });
    await intro.waitFor();
    await page.keyboard.press('Escape');
    await intro.waitFor({ state: 'hidden' });
    assert.equal(await page.evaluate(() => sessionStorage.getItem('safealley.welcome.dismissed.v1')), '1');
    assert.deepEqual(errors, []);
    console.log('Welcome intro: first session, logos, close, reload and ESC passed');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
