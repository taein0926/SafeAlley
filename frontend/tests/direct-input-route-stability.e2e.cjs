const assert = require('node:assert/strict');
const { chromium } = require('playwright');
const { baseUrl, createTestPage, rankingResult } = require('./ui-fixtures.cjs');

// Real Cesium entities with fixture route responses; no model calls or DB writes.
(async () => {
  const browser = await chromium.launch({ headless: true, channel: 'chrome',
    args: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'] });
  try {
    const page = await createTestPage(browser);
    const errors = [];
    let searches = 0;
    page.on('pageerror', error => errors.push(error.message));
    await page.route('**/api/agent/intent-preview/status', route => route.fulfill({ json: { enabled: false, configured: false, available: false } }));
    await page.route('**/api/places/resolve?**', route => {
      const name = new URL(route.request().url()).searchParams.get('name');
      const origin = name.includes('출발');
      return route.fulfill({ json: { name, latitude: origin ? 37.46 : 37.466,
        longitude: origin ? 126.68 : 126.683, source: 'ui-test' } });
    });
    await page.route('**/api/agent/execute', route => {
      searches++;
      return route.fulfill({ json: rankingResult() });
    });
    await page.goto(baseUrl, { waitUntil: 'domcontentloaded' });
    await page.getByRole('button', { name: '직접 설정', exact: true }).click();
    const origin = page.getByRole('textbox', { name: '출발지', exact: true });
    const destination = page.getByRole('textbox', { name: '도착지', exact: true });
    await origin.fill('출발 학교');
    await destination.fill('도착 병원');
    const search = page.getByRole('button', { name: '길찾기', exact: true });
    await search.waitFor();
    await page.waitForFunction(() => !document.querySelector('.search-button').disabled);
    await search.click();
    await page.locator('#route-results .route-card').nth(1).waitFor();
    // Inspect the existing Viewer ref through React's test-only fiber access.
    // This avoids adding a public/debug hook to application code.
    await page.evaluate(() => {
      const element = document.querySelector('.cesium-map');
      let fiber = element[Object.keys(element).find(key => key.startsWith('__reactFiber$'))];
      let viewer;
      for (; fiber && !viewer; fiber = fiber.return) {
        for (let hook = fiber.memoizedState; hook; hook = hook.next) {
          const current = hook.memoizedState?.current;
          if (current?.entities && current?.scene && current?.camera) { viewer = current; break; }
        }
      }
      if (!viewer) throw new Error('Cesium Viewer not found');
      const entities = viewer.entities;
      const trace = { entities, before: entities.values.filter(entity => entity.id.startsWith('recommended-route-')),
        removed: 0, added: 0 };
      const remove = entities.removeById.bind(entities);
      const add = entities.add.bind(entities);
      entities.removeById = id => { if (id.startsWith('recommended-route-')) trace.removed++; return remove(id); };
      entities.add = options => { if (options.id?.startsWith('recommended-route-')) trace.added++; return add(options); };
      window.__routeStabilityTrace = trace;
    });
    for (const input of [origin, destination]) {
      await input.fill('');
      await input.pressSequentially('새로운 장소', { delay: 90 });
    }
    const stability = await page.evaluate(() => {
      const trace = window.__routeStabilityTrace;
      return { beforeCount: trace.before.length, added: trace.added, removed: trace.removed,
        sameEntities: trace.before.every(entity => trace.entities.getById(entity.id) === entity) };
    });
    assert.equal(stability.beforeCount, 4, 'Both routes and their casings must exist');
    assert.equal(stability.added, 0, 'Typing must not rebuild route entities');
    assert.equal(stability.removed, 0, 'Typing must not remove route entities');
    assert(stability.sameEntities, 'Displayed routes retain the same Cesium entities');
    assert.equal(searches, 1, 'Typing does not submit another route');
    // A new completed search and candidate selection still refresh the route.
    await origin.fill('출발 공원');
    await destination.fill('도착 학교');
    await search.click();
    await page.waitForFunction(() => window.__routeStabilityTrace.added >= 4);
    await page.locator('#route-results .route-card').nth(1).click();
    await page.waitForFunction(() => window.__routeStabilityTrace.added >= 8);
    assert.equal(searches, 2);
    assert.deepEqual(errors, [], 'No browser runtime errors');
    console.log(JSON.stringify({ stability, searches, browserErrors: errors, result: 'passed' }));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
