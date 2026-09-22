import assert from "node:assert/strict";
import test from "node:test";
import { isNightDepartureTime } from "./nightMode.ts";

test("night theme includes 20:00 through 05:59, including seconds", () => {
  for (const time of ["20:00", "22:00", "23:59:59", "00:00", "05:59:59"]) {
    assert.equal(isNightDepartureTime(time), true, time);
  }
});

test("daytime, missing and invalid departure times use day theme", () => {
  for (const time of [null, "06:00", "12:00", "19:59:59", "", "밤 10시", "24:00", "20:60", "20:00:60"]) {
    assert.equal(isNightDepartureTime(time), false, String(time));
  }
});
