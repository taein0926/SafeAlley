const baseUrl = process.env.E2E_BASE_URL || 'http://127.0.0.1:3000/';

// Ordinary UI tests start past the once-per-session introduction. Its own
// browser test exercises the real dialog instead of bypassing this behavior.
async function createTestPage(browser) {
  const page = await browser.newPage({ viewport: { width: 1440, height: 960 } });
  await page.addInitScript(() => sessionStorage.setItem('safealley.welcome.dismissed.v1', '1'));
  await page.route('**/api/weather?**', route => {
    const time = new URL(route.request().url()).searchParams.get('departure_time');
    const date = new Intl.DateTimeFormat('en-CA', {
      timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
    }).format(new Date());
    return route.fulfill({ json: {
      date, departure_time: time, forecast_status: 'available', solar: null,
      forecast: { temperature_c: 20, wind_speed_ms: 1.2, sky: 1, precipitation_type: 0 },
    } });
  });
  return page;
}

function candidate(type, middle) {
  return { route_type: type, preference_score: 80, metrics: {}, route: {
    type: 'Feature', geometry: { type: 'LineString', coordinates: [[126.68, 37.46], middle, [126.683, 37.466]] },
    properties: { route_type: type, total_distance_m: type === 'custom' ? 740 : 620,
      total_cost: 800, average_safety_score: 70, stairs_segment_count: 0, stairs_distance_m: 0,
      total_crosswalk_count: 2, pedestrian_bridge_count: 0, intersection_data_available: true,
      sidewalk_coverage_percent: 100, max_slope_percent: null, slope_coverage_percent: 0, road_segments: [] },
  } };
}

function rankingResult() {
  return { recommendation_id: null, selected_route_type: 'custom', recommendation_status: 'ready',
    recommendation_reason: null, recommendation_notes: [], recommendation_factors: ['safety'],
    compared_route_type: 'shortest', recommendation_criteria: [], unsupported_preferences: [],
    candidates: [candidate('custom', [126.685, 37.463]), candidate('shortest', [126.681, 37.463])],
  };
}

module.exports = { baseUrl, createTestPage, rankingResult };
