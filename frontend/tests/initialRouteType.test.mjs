import assert from "node:assert/strict";
import test from "node:test";

import { initialRouteType } from "../src/initialRouteType.ts";

test("balanced route is displayed first when all three candidates exist", () => {
  assert.equal(initialRouteType([
    { route_type: "shortest" },
    { route_type: "balanced" },
    { route_type: "safe" },
  ]), "balanced");
});

test("available route is displayed when balanced does not exist", () => {
  assert.equal(initialRouteType([{ route_type: "shortest" }]), "shortest");
  assert.equal(initialRouteType([]), null);
});
