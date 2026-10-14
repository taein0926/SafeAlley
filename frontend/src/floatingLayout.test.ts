import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./styles.css", import.meta.url), "utf8");
const map = readFileSync(new URL("./components/CesiumRoadMap.tsx", import.meta.url), "utf8");

test("search panel uses 95vh and is vertically centered while building details keep their intrinsic 70vh cap", () => {
  assert.match(css, /\.map-stage \{ position: absolute; inset: 0; \}/);
  assert.match(css, /\.sidebar-primary \{[^}]*height: 95vh; max-height: 95vh;[^}]*overflow: hidden;/);
  assert.match(css, /\.search-panel-shell \{[^}]*top: 50%;[^}]*transform: translateY\(-50%\);/);
  assert.match(css, /--floating-panel-top: 2\.5vh;/);
  assert.match(css, /--sidebar-width: 328px;/);
  assert.match(css, /\.floating-secondary \{[^}]*top: var\(--floating-panel-top\);[^}]*max-height: 70vh;[^}]*overflow-y: auto;/);
  assert.match(css, /--route-card-width: clamp\(244px, 30%, 304px\);/);
  assert.match(css, /--detail-width: var\(--route-card-width\);/);
  assert.match(css, /\.floating-secondary \{[^}]*width: var\(--detail-width\);/);
  assert.doesNotMatch(css, /--dock-width|inset: 0 0 0 var\(--sidebar-width\)/);
});

test("map pins stay below the search panel without hiding the surrounding map", () => {
  const pinZ = Number(css.match(/\.route-pins \{[^}]*z-index: (\d+)/)?.[1]);
  const panelZ = Number(css.match(/\.search-panel-shell \{[^}]*z-index: (\d+)/)?.[1]);
  assert.ok(pinZ < panelZ);
});

test("collapse handle attaches to the floating card and stays reachable when closed", () => {
  assert.match(css, /\.search-panel-handle \{[^}]*left: 100%;[^}]*width: 28px;[^}]*height: 64px;/);
  assert.match(css, /\.search-panel-shell--collapsed \{ transform: translate\(calc\(-100% - var\(--panel-edge\)\), -50%\); \}/);
  assert.doesNotMatch(css, /\.search-panel-shell--collapsed \.search-panel-handle/);
});

test("candidate cards and object details share their top-left anchor and collapse hides the details", () => {
  assert.match(app, /className="result-panel result-panel--floating"/);
  assert.ok(app.indexOf('id="route-results"') < app.indexOf('id="map-sidebar-content"'));
  assert.equal(app.match(/id="route-results"/g)?.length, 1);
  assert.match(app, /id="route-candidate-cards"/);
  assert.doesNotMatch(app, /floating-results-header|resultPanelOpen|경로 후보 숨기기|경로 후보 보이기/);
  assert.match(app, /className="map-info-panel floating-secondary"/);
  assert.match(app, /searchPanelOpen && mapInfo &&/);
  assert.match(css, /\.floating-secondary \{[^}]*left: calc\(var\(--panel-edge\) \+ var\(--sidebar-width\) \+ var\(--route-panel-gap\)\);[^}]*z-index: 31;/);
  assert.match(app, /aria-label="지도 객체 정보 닫기" onClick=\{\(\) => setMapInfo\(null\)\}/);
  assert.match(css, /\.search-panel-shell--collapsed \.sidebar-content \{ visibility: hidden; \}/);
  assert.match(app, /inert=\{!searchPanelOpen\}/);
  const cards = readFileSync(new URL("./routeCards.css", import.meta.url), "utf8");
  assert.doesNotMatch(cards, /floating-results-header/);
  assert.match(cards, /width: var\(--route-card-width\);/);
  assert.match(cards, /top: var\(--floating-panel-top\);/);
  assert.match(cards, /--route-panel-gap: max\(calc\(var\(--panel-gap\) \* 0\.7 \+ 14px\), 36\.4px\);/);
  assert.match(cards, /left: calc\(var\(--panel-edge\) \+ var\(--sidebar-width\) \+ var\(--route-panel-gap\)\);/);
  assert.match(cards, /\.app-shell--sidebar-closed #route-results\.result-panel--floating \{ left: var\(--route-panel-gap\); \}/);
});

test("floating route backgrounds reveal the map with minimal blur without fading text", () => {
  const cards = readFileSync(new URL("./routeCards.css", import.meta.url), "utf8");
  assert.match(cards, /--result-surface: rgba\(255, 255, 255, \.5\);/);
  assert.match(cards, /--result-selected: rgba\(242, 247, 255, \.58\);/);
  assert.match(cards, /--result-inactive-badge: rgba\(242, 244, 247, \.7\);/);
  assert.match(cards, /\.recommendation-badge\[data-applied="false"\] \{[^}]*background: var\(--result-inactive-badge\);/);
  assert.match(cards, /backdrop-filter: blur\(1px\);/);
  assert.doesNotMatch(cards, /\bopacity\s*:/);
});

test("building, streetlight, CCTV, stairs and bridge details share thirty-percent-transparent surfaces", () => {
  const chrome = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  assert.match(app, /data-kind=\{mapInfo.kind\}/);
  const shared = chrome.match(/\.app-shell (\.map-info-panel:is\(([^)]+)\)) \{([^}]+)\}/);
  assert.ok(shared);
  assert.deepEqual(shared[2].match(/data-kind="([^"]+)"/g), [
    'data-kind="building"', 'data-kind="streetlight"', 'data-kind="cctv"', 'data-kind="stairs"', 'data-kind="bridge"',
  ]);
  const panel = shared[3];
  assert.match(panel, /--building-detail-surface: rgba\(255, 255, 255, \.7\);/);
  assert.match(panel, /--building-detail-accent: rgba\(23, 105, 223, \.7\);/);
  assert.match(panel, /backdrop-filter: blur\(1px\);/);
  assert.doesNotMatch(panel, /\bopacity\s*:/);
  assert.ok(chrome.includes(`${shared[1]} .panel-close { background: var(--building-detail-surface); }`));
  assert.ok(chrome.includes(`${shared[1]} .panel-close:hover { background: var(--building-detail-hover); }`));
  assert.match(chrome, /\[data-kind="building"\] \.building-location-actions button:last-child \{ color: #fff; background: var\(--building-detail-accent\); \}/);
});

test("streaming progress scrolls independently below the fixed search controls", () => {
  const search = readFileSync(new URL("./searchPanel.css", import.meta.url), "utf8");
  assert.match(search, /flex-shrink: 0;\s+max-height: calc\(95vh - 120px\);\s+overflow-y: auto;/);
  assert.match(app, /<\/section>\s+<div ref=\{processScrollRef\} className="sidebar-scroll"/);
  assert.match(app, /<RouteProgressPanel/);
  assert.match(app, /queryRouteWithProgress\(text.trim\(\), userId/);
});

test("progress keeps its messages but removes the comparison table and its notices from code", () => {
  const progress = readFileSync(new URL("./components/RouteProgressPanel.tsx", import.meta.url), "utf8");
  const search = readFileSync(new URL("./searchPanel.css", import.meta.url), "utf8");
  assert.match(progress, /AI가 길을 찾고 있어요/);
  assert.match(progress, /progressMessages\(/);
  assert.doesNotMatch(progress, /requestedMetricRows|<details|<table|계산값 자세히 보기|실제 밝기·안전도/);
  assert.doesNotMatch(search, /route-progress-comparison|route-progress-note/);
});

test("both camera modes reuse the fit and account for visible floating panels", () => {
  assert.match(map, /querySelectorAll\("\.sidebar-primary, \.floating-secondary, #route-results"\)/);
  assert.match(map, /!sidebarClosed \|\| panel.id === "route-results"/);
  assert.match(map, /classList.contains\("app-shell--sidebar-closed"\)/);
  assert.match(map, /flyToRouteFrame\(viewer, coordinates,\s+routeDetailOpen \? routeCameraHeading\(selected.route.geometry.coordinates\) : 0,\s+routeDetailOpen \? -CesiumMath.toRadians\(55\) : -CesiumMath.PI_OVER_TWO\)/);
  assert.match(map, /flyToRouteFrame\(viewer, frameCoordinates,/);
  assert.match(map, /if \(routeDetailOpen === lastRouteDetailOpenRef.current\) return;/);
});
