import { CONDITION_ORDER, type ConditionCard } from "./conditionCards.ts";

export type PreviewResponse = { query: string; model: string; conditions: ConditionCard[]; cached?: boolean };
export type PreviewStatus = { enabled: boolean; configured: boolean; available: boolean };

export function previewUnavailableMessage(status: PreviewStatus | null): string {
  return status?.enabled === false
    ? "실시간 조건 분석이 꺼져 있습니다. 새 입력은 분석되지 않습니다. 경로 검색은 계속 사용할 수 있어요."
    : "실시간 조건 분석에 연결되지 않았습니다. 새 입력은 분석되지 않습니다. 경로 검색은 계속 사용할 수 있어요.";
}

export async function requestIntentPreview(query: string): Promise<PreviewResponse> {
  const response = await fetch("/api/agent/intent-preview", {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ query }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "실시간 조건 분석을 완료하지 못했습니다.");
  if (data.query !== query || !Array.isArray(data.conditions) || data.conditions.length !== CONDITION_ORDER.length) {
    throw new Error("실시간 조건 분석 응답이 올바르지 않습니다.");
  }
  const factors = new Set(data.conditions.map((card: ConditionCard) => card.factor));
  if (factors.size !== CONDITION_ORDER.length || !CONDITION_ORDER.every((factor) => factors.has(factor))
    || data.conditions.some((card: ConditionCard) => !["analyzing", "applied", "not_applied"].includes(card.state))) {
    throw new Error("실시간 조건 카드의 상태를 확인할 수 없습니다.");
  }
  return data as PreviewResponse;
}

type Options = {
  request: (query: string) => Promise<PreviewResponse>;
  onPending: () => void; onResult: (result: PreviewResponse) => void; onError: (error: Error) => void;
  onEmpty: () => void; boundaryDelayMs?: number; idleDelayMs?: number; minimumIntervalMs?: number;
};

export function createPreviewScheduler(options: Options) {
  let version = 0;
  let current = "";
  let lastSnapshot = "";
  let queued: { query: string; version: number; readyAt: number } | null = null;
  let inFlight = false;
  let lastStarted = -Infinity;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let idleTimer: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  let failed = false;
  const minimumInterval = options.minimumIntervalMs ?? 800;

  function isCurrentPrefix(task: { query: string; version: number }) {
    return !disposed && task.version === version && current.startsWith(task.query)
      && (current === task.query || /^\s/u.test(current.slice(task.query.length)));
  }

  function enqueue(query: string, delay: number) {
    if (query === lastSnapshot && !failed) return;
    lastSnapshot = query;
    options.onPending();
    queued = { query, version, readyAt: Date.now() + delay };
    schedule();
  }

  function schedule() {
    if (timer) clearTimeout(timer);
    if (!queued || inFlight || disposed) return;
    const delay = Math.max(0, queued.readyAt - Date.now(), lastStarted + minimumInterval - Date.now());
    timer = setTimeout(() => { void run(); }, delay);
  }

  async function run() {
    timer = undefined;
    if (!queued || inFlight || disposed) return;
    const task = queued;
    queued = null;
    // An idle snapshot can become an incomplete word when typing resumes.
    if (!isCurrentPrefix(task)) return;
    inFlight = true;
    lastStarted = Date.now();
    try {
      const result = await options.request(task.query);
      // Appending the next word must not discard an already completed prefix.
      // A rewrite, deletion, clear or pause invalidates the previous generation.
      if (isCurrentPrefix(task)) {
        failed = false; options.onResult(result);
        if (queued) options.onPending();
      }
    } catch (error) {
      if (isCurrentPrefix(task)) {
        failed = true;
        options.onError(error instanceof Error ? error : new Error("실시간 분석 오류"));
      }
    } finally {
      inFlight = false;
      schedule();
    }
  }

  function pause() {
    version++;
    queued = null;
    current = "";
    lastSnapshot = "";
    if (timer) clearTimeout(timer);
    if (idleTimer) clearTimeout(idleTimer);
    timer = undefined;
    idleTimer = undefined;
  }

  return {
    update(text: string) {
      if (disposed) return;
      const query = text.trim();
      const boundary = /[\s.!?,;。！？]$/u.test(text);
      // Adding a space leaves trim() unchanged, but is a new analysis trigger.
      if (query === current && !failed && !boundary) return;
      if (!query.startsWith(current)) {
        version++;
        queued = null;
        lastSnapshot = "";
        if (timer) clearTimeout(timer);
        timer = undefined;
      }
      current = query;
      if (!query) { pause(); options.onEmpty(); return; }
      // Retain the original idle delay for the last word, but keep this timer
      // separate so a new letter never postpones the completed-word snapshot.
      if (idleTimer) clearTimeout(idleTimer);
      const inputVersion = version;
      idleTimer = setTimeout(() => {
        idleTimer = undefined;
        if (!disposed && version === inputVersion) enqueue(current, 0);
      }, options.idleDelayMs ?? 800);
      if (boundary) enqueue(query, options.boundaryDelayMs ?? 350);
    },
    pause,
    dispose() { pause(); disposed = true; },
  };
}
