import assert from "node:assert/strict";
import test from "node:test";
import {setImmediate as tick} from "node:timers/promises";
import {createPreviewStatusMonitor, type PreviewStatus} from "./liveIntentPreview.ts";

const ready: PreviewStatus = {enabled: true, configured: true, available: true};

test("모델이 늦게 준비되어도 자동 재확인하고 한 번만 복구를 알린다", async (t) => {
  t.mock.timers.enable({apis: ["setTimeout"]});
  let requests = 0, recoveries = 0;
  const statuses: (PreviewStatus | null)[] = [];
  const monitor = createPreviewStatusMonitor({
    request: async () => (++requests === 1 ? {...ready, available: false} : ready),
    onStatus: status => statuses.push(status), onAvailable: () => recoveries++,
  });
  await monitor.refresh();
  assert.equal(recoveries, 0);
  t.mock.timers.tick(5000); await tick();
  assert.equal(statuses.at(-1)?.available, true);
  assert.equal(recoveries, 1);
  t.mock.timers.tick(30000); await tick();
  assert.equal(requests, 2);
  await monitor.refresh();
  assert.equal(recoveries, 1);
  monitor.dispose();
});

test("초기 네트워크 오류 뒤에도 상태 확인을 다시 시도한다", async (t) => {
  t.mock.timers.enable({apis: ["setTimeout"]});
  let requests = 0, recoveries = 0;
  const monitor = createPreviewStatusMonitor({
    request: async () => { if (++requests === 1) throw new Error("offline"); return ready; },
    onStatus: () => {}, onAvailable: () => recoveries++,
  });
  await assert.rejects(monitor.refresh());
  t.mock.timers.tick(5000); await tick();
  assert.equal(recoveries, 1);
  monitor.dispose();
});

test("중복 상태 요청을 합치고 화면 종료 뒤 응답은 무시한다", async () => {
  let finish!: (status: PreviewStatus) => void;
  let requests = 0, callbacks = 0;
  const monitor = createPreviewStatusMonitor({
    request: () => { requests++; return new Promise(resolve => { finish = resolve; }); },
    onStatus: () => callbacks++, onAvailable: () => callbacks++,
  });
  const first = monitor.refresh(), second = monitor.refresh();
  assert.equal(requests, 1);
  monitor.dispose(); finish(ready);
  await Promise.all([first, second]);
  assert.equal(callbacks, 0);
});

test("재시도 대기 중 화면을 닫으면 요청을 멈춘다", async (t) => {
  t.mock.timers.enable({apis: ["setTimeout"]});
  let requests = 0;
  const monitor = createPreviewStatusMonitor({
    request: async () => { requests++; return {...ready, available: false}; },
    onStatus: () => {}, onAvailable: () => {},
  });
  await monitor.refresh();
  monitor.dispose();
  t.mock.timers.tick(30000); await tick();
  assert.equal(requests, 1);
  await assert.rejects(monitor.refresh());
});

test("준비 상태 뒤 연결이 끊어져도 다시 준비되면 복구를 알린다", async (t) => {
  t.mock.timers.enable({apis: ["setTimeout"]});
  let requests = 0, recoveries = 0;
  const monitor = createPreviewStatusMonitor({
    request: async () => {
      requests++;
      if (requests === 2) throw new Error("offline");
      return ready;
    },
    onStatus: () => {}, onAvailable: () => recoveries++,
  });
  await monitor.refresh();
  await assert.rejects(monitor.refresh());
  t.mock.timers.tick(5000); await tick();
  assert.equal(requests, 3);
  assert.equal(recoveries, 2);
  monitor.dispose();
});
