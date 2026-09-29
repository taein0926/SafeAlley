import assert from "node:assert/strict";
import test from "node:test";
import { createRouteSelectionSaver } from "./routeSelection.ts";

const selection = { recommendation_id: "test", user_id: "test", selected_route_type: "safe" as const };
const ok = () => new Response(JSON.stringify({ preferences: [] }));

test("network interruption retries the same payload and keeps the request alive", async () => {
  const calls: RequestInit[] = [];
  const delays: number[] = [];
  const save = createRouteSelectionSaver(async (url, options) => {
    assert.equal(url, "/api/agent/route-selections");
    calls.push(options!);
    if (calls.length === 1) throw new TypeError("Failed to fetch");
    return ok();
  }, async (ms) => { delays.push(ms); });
  await save(selection);
  assert.equal(calls.length, 2);
  assert.equal(calls[0].body, calls[1].body);
  assert.equal(calls[0].keepalive, true);
  assert.ok(calls[0].signal);
  assert.deepEqual(delays, [1000]);
});

test("temporary proxy errors recover; validation errors are not retried", async () => {
  let attempts = 0;
  const save = createRouteSelectionSaver(async () => {
    attempts++;
    return attempts < 3 ? new Response("unavailable", { status: 502 }) : ok();
  }, async () => {});
  await save(selection);
  assert.equal(attempts, 3);
  let invalidAttempts = 0;
  await assert.rejects(createRouteSelectionSaver(async () => {
    invalidAttempts++;
    return new Response("invalid", { status: 400 });
  }, async () => {})(selection), /HTTP 400/);
  assert.equal(invalidAttempts, 1);
});

test("retries are bounded and a later choice can still save", async () => {
  let attempts = 0;
  const save = createRouteSelectionSaver(async () => {
    if (++attempts <= 3) throw new TypeError("Failed to fetch");
    return ok();
  }, async () => {});
  await assert.rejects(save(selection), /Failed to fetch/);
  assert.equal(attempts, 3);
  await save({ ...selection, selected_route_type: "shortest" });
  assert.equal(attempts, 4);
});

test("a retried older choice finishes before the latest choice is sent", async () => {
  const sent: string[] = [];
  const save = createRouteSelectionSaver(async (_, options) => {
    sent.push(JSON.parse(options!.body as string).selected_route_type);
    if (sent.length === 1) throw new TypeError("Failed to fetch");
    return ok();
  }, async () => {});
  await Promise.all([save(selection), save({ ...selection, selected_route_type: "shortest" })]);
  assert.deepEqual(sent, ["safe", "safe", "shortest"]);
});

test("timeout and interrupted response body also retry", async () => {
  let attempts = 0;
  const save = createRouteSelectionSaver(async () => {
    attempts++;
    if (attempts === 1) throw new DOMException("timeout", "TimeoutError");
    if (attempts === 2) {
      const response = ok();
      response.json = async () => { throw new TypeError("connection closed"); };
      return response;
    }
    return ok();
  }, async () => {});
  await save(selection);
  assert.equal(attempts, 3);
});
