import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";
import {conditionDecisions} from "./routeProgress.ts";
import type {RouteQueryResponse} from "./types.ts";

test("partial crossing cost is not called entirely unapplied in the progress log", () => {
  const interpretation = {origin_name: null, destination_name: null, departure_time: "23:00:00", profile: "pedestrian",
    preferences: [{factor: "crosswalk_count", direction: "minimize", weight: 1}]} as RouteQueryResponse["interpretation"];
  const result = {recommendation_status: "ready", unsupported_preferences: [{factor: "crosswalk_count", reason: "data is unavailable"}],
    recommendation_conditions: [{factor: "crossing", state: "applied", application_scope: "route_generation", data_quality: "partial"}]} as RouteQueryResponse["result"];
  const row = conditionDecisions(interpretation, result).find(r => r.factor === "crosswalk_count");
  assert.equal(row?.state, "applied");
  assert.match(row?.application ?? "", /전체 건널목 비교는 별도/);
});

test("mobile override targets the real ID-scoped result panel", () => {
  const css = readFileSync(new URL("./mapChrome.css", import.meta.url), "utf8");
  assert.match(css, /@media \(max-width: 600px\)[\s\S]*\.app-shell #route-results\.result-panel--floating/);
  assert.match(css, /bottom: 12px/);
});
