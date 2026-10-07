import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const component = readFileSync(new URL("./components/RouteProgressPanel.tsx", import.meta.url), "utf8");
const css = readFileSync(new URL("./searchPanel.css", import.meta.url), "utf8");

test("pending messages use a thinking robot without changing stage or workflow contracts", () => {
  assert.match(component, /route-progress-robot-head/);
  assert.match(component, /route-progress-robot-eyes/);
  assert.match(component, /\[30, 34, 38\]/);
  assert.match(component, /message.pending \? \(/);
  assert.doesNotMatch(component, /route-progress-lips|route-progress-mouth|checking|confirming/);
});

test("completed messages use blue checks while failure remains a warning", () => {
  assert.match(css, /\.route-progress-avatar--complete \{ color: #1769df; background: #dceaff; \}/);
  assert.match(component, /stage === "failed" \? "route-progress-waiting" : "route-progress-check"/);
  assert.match(css, /route-progress-avatar--waiting/);
});

test("robot motion respects reduced-motion accessibility preferences", () => {
  assert.match(css, /@keyframes route-progress-robot-blink/);
  assert.match(css, /@keyframes route-progress-robot-think/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\) \{[^}]*route-progress-robot-eyes[^}]*animation: none;/);
});

test("robot fits inside its blue circular background including the thought bubble", () => {
  assert.match(css, /\.route-progress-avatar \{[^}]*width: 29px; height: 29px;[^}]*overflow: hidden;/);
  assert.match(css, /\.route-progress-robot \{ width: 22px; height: 20px; overflow: hidden; \}/);
});
