import assert from "node:assert/strict";
import test from "node:test";
import { koreaDate, koreaTime, matchingWeather, weatherRefreshDelay, weatherSymbol, type WeatherData } from "./weather.ts";
import { isNightDepartureTime } from "./nightMode.ts";

test("unavailable weather retries sooner and returns to normal polling after recovery", () => {
  assert.equal(weatherRefreshDelay(null), 60_000);
  assert.equal(weatherRefreshDelay({ forecast_status: "stale" } as WeatherData), 60_000);
  assert.equal(weatherRefreshDelay({ forecast_status: "unavailable" } as WeatherData), 60_000);
  assert.equal(weatherRefreshDelay({ forecast_status: "available", solar: null } as WeatherData), 60_000);
  assert.equal(weatherRefreshDelay({ forecast_status: "available", solar: {} } as WeatherData), 15 * 60_000);
});

test("Korea date/time use KST even when browser timezone is elsewhere", () => {
  const date = new Date("2026-09-22T15:05:00Z");
  assert.equal(koreaDate(date), "2026-09-23");
  assert.equal(koreaTime(date), "00:05");
});
test("solar boundaries are exact and do not depend on fixed 20:00 night start", () => {
  const solar = { sunrise: "06:20:00", sunset: "18:30:00" };
  assert.equal(isNightDepartureTime("06:19", solar), true);
  assert.equal(isNightDepartureTime("06:20", solar), false);
  assert.equal(isNightDepartureTime("18:29", solar), false);
  assert.equal(isNightDepartureTime("18:30", solar), true);
  assert.equal(isNightDepartureTime("19:00", null), false);
});
test("rain, snow, clear and unknown remain distinct", () => {
  const sample = (pty: number | null, sky: number | null) => ({ precipitation_type: pty, sky }) as NonNullable<WeatherData["forecast"]>;
  assert.equal(weatherSymbol(sample(1, 1)).label, "비 예보");
  assert.equal(weatherSymbol(sample(2, 4)).label, "비·눈 예보");
  assert.equal(weatherSymbol(sample(3, 4)).label, "눈 예보");
  assert.equal(weatherSymbol(sample(0, 1)).label, "맑음");
  assert.equal(weatherSymbol(sample(0, 3)).label, "구름 많음");
  assert.equal(weatherSymbol(sample(null, 1)).label, "날씨 정보 부족");
  assert.equal(weatherSymbol(null).label, "예보 없음");
});
test("previous search time or yesterday's forecast is hidden while fetching", () => {
  const data = { date: "2026-09-23", departure_time: "18:30:00" } as WeatherData;
  assert.equal(matchingWeather(data, "2026-09-23", "18:30"), data);
  assert.equal(matchingWeather(data, "2026-09-23", "19:30"), null);
  assert.equal(matchingWeather(data, "2026-09-24", "18:30"), null);
});
