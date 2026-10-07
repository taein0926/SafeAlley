import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const app = readFileSync(new URL("./App.tsx", import.meta.url), "utf8");
const map = readFileSync(new URL("./components/CesiumRoadMap.tsx", import.meta.url), "utf8");
const weather = readFileSync(new URL("./components/WeatherHud.tsx", import.meta.url), "utf8");

test("day panel palette is independent of night map lighting", () => {
  assert.match(app, /data-theme="day"/);
  assert.match(app, /nightMode=\{nightMode\}/);
  assert.match(map, /mapLighting\(nightMode\)/);
});

test("weather uses readable condition and emphasized forecast time, not an icon", () => {
  assert.match(weather, /className="weather-condition">\{symbol.label\}/);
  assert.match(weather, /<strong className="weather-time">/);
  assert.match(weather, /<strong className="weather-time">\{date.slice\(5\)/);
  assert.doesNotMatch(weather, /symbol.icon|role="img"/);
});

test("only map controls change camera mode without a card detail button or selection reset", () => {
  assert.match(app, /aria-label="지도 시점"/);
  assert.match(app, />탑뷰<\/button>/);
  assert.match(app, />사이드뷰<\/button>/);
  assert.doesNotMatch(app, /className="route-detail-button"/);
  const select = app.slice(app.indexOf("const selectRoute ="), app.indexOf("const handleMapInfoChange ="));
  assert.doesNotMatch(select, /setRouteDetailOpen/);
  const begin = app.slice(app.indexOf("function beginSearch"), app.indexOf("function failSearch"));
  assert.match(begin, /setRouteDetailOpen\(false\)/);
  assert.match(map, /if \(routeDetailOpen === lastRouteDetailOpenRef.current\) return;/);
  assert.match(map, /signature !== lastRouteSignatureRef.current/);
});

test("side view includes all candidate paths and supports the map before search", () => {
  assert.match(map, /const frameCoordinates = \[\.\.\.routeCandidates.flatMap/);
  assert.match(map, /viewer.camera.pickEllipsoid/);
});
