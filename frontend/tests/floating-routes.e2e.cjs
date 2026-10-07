const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

const output = process.env.E2E_OUTPUT || path.resolve(__dirname, '../../../output/screenshots');
const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:3002/';

(async () => {
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({
    headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1440, height: 960 }, deviceScaleFactor: 1 });
    // Exercise real Qwen/DB routing without writing test recommendation/selection records.
    await page.route('**/api/agent/query/stream', async (route) => {
      const payload = route.request().postDataJSON();
      await route.continue({ postData: JSON.stringify({ ...payload, user_id: null }) });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });

    for (const [theme, time] of [['night', '밤 10시'], ['day', '오후 1시']]) {
      await page.getByRole('textbox', { name: '문장으로 경로 요청' }).fill(
        `${time}에 정부인천지방합동청사에서 두리하나어린이집까지 가로등과 CCTV가 많은 길로 안내해줘. 계단은 피하고 건널목은 적게 지나고 싶어`,
      );
      await page.getByRole('button', { name: '길찾기', exact: true }).click();
      await page.getByRole('heading', { name: 'AI가 길을 찾고 있어요', exact: true }).waitFor({ timeout: 180000 });
      await page.locator('#route-results .route-card').nth(1).waitFor();
      const question = page.getByRole('textbox', { name: '문장으로 경로 요청' });
      const searchButton = page.getByRole('button', { name: '길찾기', exact: true });
      const questionBefore = await question.boundingBox();
      const buttonBefore = await searchButton.boundingBox();
      const processing = page.getByRole('region', { name: '경로 검색 처리 내용' });
      await processing.evaluate((element) => { element.scrollTop = element.scrollHeight; });
      assert(await processing.evaluate((element) => element.scrollTop > 0), 'Process content must scroll independently');
      const questionAfter = await question.boundingBox();
      const buttonAfter = await searchButton.boundingBox();
      assert.equal(questionBefore.y, questionAfter.y, 'Question must stay fixed');
      assert.equal(buttonBefore.y, buttonAfter.y, 'Search button must stay fixed');
      await page.screenshot({ path: path.join(output, `safealley-fixed-question-scrolled-${theme}-20261006.png`) });
      await processing.evaluate((element) => { element.scrollTop = 0; });
      const panel = await page.locator('#route-results').boundingBox();
      const map = await page.locator('.map-stage').boundingBox();
      const cards = await page.locator('#route-results .route-card').all();
      const first = await cards[0].boundingBox();
      const second = await cards[1].boundingBox();
      const searchPanel = await page.locator('.sidebar-primary').boundingBox();
      assert(Math.abs(panel.x - searchPanel.x - searchPanel.width - 36.4) < 0.1, 'Cards must halve the empty gap beyond the 28px handle');
      assert(Math.abs(searchPanel.height - map.height * 0.95) < 1, 'Search panel must fill 95 percent of map height');
      assert(Math.abs(searchPanel.y + searchPanel.height / 2 - map.y - map.height / 2) < 1, 'Search panel must be vertically centered');
      assert(Math.abs(panel.y - searchPanel.y) < 1, 'Candidate header must start at the same height as the search panel');
      assert.equal(await page.locator('.route-progress-comparison, .route-progress-note').count(), 0);
      assert(panel.y - map.y >= 0 && panel.y - map.y < 40, 'Cards must start near map top');
      assert(first.y + first.height <= second.y, 'Cards must be stacked vertically');
      assert.equal(await page.locator('.sidebar-scroll #route-results').count(), 0);
      const color = await cards[0].evaluate((element) => getComputedStyle(element).backgroundColor);
      assert.match(color, /rgba\(/, 'Card background must be translucent');
      await cards[1].click();
      assert.equal(await cards[1].getAttribute('aria-pressed'), 'true');
      assert.equal(await page.locator('#route-results .route-card[aria-pressed=true]').count(), 1);
      await page.screenshot({ path: path.join(output, `safealley-floating-routes-${theme}-20261006.png`) });
      console.log(JSON.stringify({ theme, panel, map, cards: cards.length, background: color }));
    }

    const expandedCards = await page.locator('#route-results').boundingBox();
    const collapseHandle = await page.getByRole('button', { name: '검색·결과·상세 패널 접기' }).boundingBox();
    const expandedGap = expandedCards.x - collapseHandle.x - collapseHandle.width;
    await page.getByRole('button', { name: '검색·결과·상세 패널 접기' }).click();
    assert(await page.locator('#route-results').isVisible(), 'Floating cards survive sidebar collapse');
    const collapsedCards = await page.locator('#route-results').boundingBox();
    const reopenHandle = await page.getByRole('button', { name: '검색·결과·상세 패널 열기' }).boundingBox();
    assert(Math.abs(collapsedCards.x - reopenHandle.x - reopenHandle.width - expandedGap) < 0.1, 'Collapse must preserve the gap between handle and result cards');
    await page.getByRole('button', { name: '경로 후보 숨기기' }).click();
    assert(await page.locator('#route-results').isVisible(), 'Header remains available to restore cards');
    assert.equal(await page.locator('#route-results .route-card').count(), 0);
    await page.getByRole('button', { name: '경로 후보 보이기' }).click();
    assert.equal(await page.locator('#route-results .route-card').count(), 2);
    await page.getByRole('button', { name: '검색·결과·상세 패널 열기' }).click();
    assert(await page.locator('#route-results').isVisible());
    console.log('Floating route UI: passed');
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
