import assert from "node:assert/strict";
import test from "node:test";

import { isNightDepartureTime } from "../src/nightMode.ts";

test("night mode follows the route policy at 20:00 through 05:59", () => {
  assert.equal(isNightDepartureTime("19:59:59"), false);
  assert.equal(isNightDepartureTime("20:00:00"), true);
  assert.equal(isNightDepartureTime("00:00:00"), true);
  assert.equal(isNightDepartureTime("05:59:59"), true);
  assert.equal(isNightDepartureTime("06:00:00"), false);
});

test("missing or invalid structured times do not dim the map", () => {
  assert.equal(isNightDepartureTime(null), false);
  assert.equal(isNightDepartureTime("밤 10시"), false);
  assert.equal(isNightDepartureTime("24:00:00"), false);
  assert.equal(isNightDepartureTime("20:60:00"), false);
});
