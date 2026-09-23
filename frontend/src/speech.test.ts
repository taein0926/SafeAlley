import assert from "node:assert/strict";
import test from "node:test";
import { SpeechCapture, type SpeechEnvironment, type SpeechState } from "./speech.ts";

function setup(overrides: Partial<SpeechEnvironment> = {}) {
  let released = 0;
  let calls = 0;
  const results: Array<[string, number]> = [];
  const states: Array<[SpeechState, string]> = [];
  const stream = { getTracks: () => [{ stop: () => released++ }] } as unknown as MediaStream;
  const recorder = {
    state: "inactive", onstop: null as null | (() => Promise<void>),
    onerror: null as null | (() => void),
    ondataavailable: null as null | ((e: { data: Blob }) => void),
    start() { this.state = "recording"; },
    stop() { this.state = "inactive"; void this.onstop?.(); },
  };
  const capture = new SpeechCapture({
    getUserMedia: async () => stream,
    supports: () => true,
    recorder: () => recorder as unknown as MediaRecorder,
    transcribe: async () => { calls++; return "주안역에서 인천사랑병원까지"; },
    ...overrides,
  }, (state, message) => states.push([state, message]), (text, revision) => results.push([text, revision]));
  return { capture, recorder, stream, results, states, released: () => released, calls: () => calls };
}

test("recording releases microphone and returns text with original input revision, never searches", async () => {
  const f = setup();
  await f.capture.start(7);
  f.recorder.ondataavailable?.({ data: new Blob(["audio"]) });
  await f.recorder.onstop?.();
  assert.equal(f.released(), 1);
  assert.equal(f.calls(), 1);
  assert.deepEqual(f.results, [["주안역에서 인천사랑병원까지", 7]]);
  assert.equal(f.states.at(-1)?.[0], "idle");
  f.capture.cancel(false);
});

test("permission denial restores idle state without uploading", async () => {
  const f = setup({ getUserMedia: async () => { throw new DOMException("denied", "NotAllowedError"); } });
  await f.capture.start(0);
  assert.equal(f.states.at(-1)?.[0], "idle");
  assert.match(f.states.at(-1)![1], /권한/);
  assert.equal(f.calls(), 0);
});

test("stopping a recording transcribes once and returns to idle", async () => {
  const f = setup();
  await f.capture.start(3);
  f.recorder.ondataavailable?.({ data: new Blob(["audio"]) });
  f.capture.stop();
  f.capture.stop();
  await Promise.resolve();
  assert.equal(f.calls(), 1);
  assert.equal(f.released(), 1);
  assert.equal(f.states.at(-1)?.[0], "idle");
  assert.equal(f.results[0][1], 3);
  f.capture.cancel(false);
});

test("cancel during permission prompt releases late microphone stream", async () => {
  let grant!: (value: MediaStream) => void;
  const f = setup({ getUserMedia: () => new Promise((resolve) => { grant = resolve; }) });
  const pending = f.capture.start(0);
  f.capture.cancel();
  grant(f.stream);
  await pending;
  assert.equal(f.released(), 1);
  assert.equal(f.calls(), 0);
  assert.equal(f.recorder.state, "inactive");
});

test("cancel recording releases tracks without sending audio", async () => {
  const f = setup();
  await f.capture.start(0);
  f.recorder.ondataavailable?.({ data: new Blob(["audio"]) });
  f.capture.cancel();
  assert.equal(f.released(), 1);
  assert.equal(f.calls(), 0);
});

test("canceled transcription cannot overwrite the query even if server finishes", async () => {
  let finish!: (value: string) => void;
  let signal!: AbortSignal;
  const f = setup({ transcribe: (_, requestSignal) => {
    signal = requestSignal;
    return new Promise((resolve) => { finish = resolve; });
  } });
  await f.capture.start(2);
  f.recorder.ondataavailable?.({ data: new Blob(["audio"]) });
  const pending = f.recorder.onstop?.();
  f.capture.cancel();
  finish("오래된 결과");
  await pending;
  assert.equal(signal.aborted, true);
  assert.deepEqual(f.results, []);
});

test("recording errors and oversized recordings do not upload", async () => {
  for (const cause of ["error", "size"]) {
    const f = setup();
    await f.capture.start(0);
    if (cause === "error") f.recorder.onerror?.();
    else f.recorder.ondataavailable?.({ data: new Blob([new Uint8Array(8 * 1024 * 1024 + 1)]) });
    assert.equal(f.released(), 1);
    assert.equal(f.calls(), 0);
    assert.equal(f.states.at(-1)?.[0], "idle");
  }
});

test("empty recording restores idle without a transcription request", async () => {
  const f = setup();
  await f.capture.start(0);
  await f.recorder.onstop?.();
  assert.equal(f.calls(), 0);
  assert.equal(f.released(), 1);
  assert.match(f.states.at(-1)![1], /녹음 내용/);
  f.capture.cancel(false);
});
