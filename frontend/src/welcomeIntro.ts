export const WELCOME_DISMISSED_KEY = "safealley.welcome.dismissed.v1";
export const WELCOME_DURATION_MS = 8000;

type SessionStore = Pick<Storage, "getItem" | "setItem">;
export function hasDismissedWelcome(storage: SessionStore | null): boolean {
  try { return storage?.getItem(WELCOME_DISMISSED_KEY) === "1"; } catch { return false; }
}
export function rememberWelcomeDismissed(storage: SessionStore | null): void {
  try { storage?.setItem(WELCOME_DISMISSED_KEY, "1"); } catch { /* Privacy mode must not block closing. */ }
}

export function createWelcomeCountdown(options: {
  onTick: (seconds: number) => void;
  onElapsed: () => void;
  now?: () => number;
  schedule?: (callback: () => void, delay: number) => number;
  cancel?: (timer: number) => void;
}) {
  const now = options.now ?? Date.now;
  const schedule = options.schedule ?? ((callback, delay) => window.setTimeout(callback, delay));
  const cancel = options.cancel ?? ((timer) => window.clearTimeout(timer));
  let remainingMs = WELCOME_DURATION_MS, startedAt: number | null = null;
  let timer: number | undefined, finished = false, disposed = false;
  const stopTimer = () => { if (timer !== undefined) cancel(timer); timer = undefined; };
  const remaining = () => Math.max(0, remainingMs - (startedAt === null ? 0 : now() - startedAt));
  function tick() {
    timer = undefined;
    if (disposed || finished || startedAt === null) return;
    const value = remaining();
    options.onTick(Math.ceil(value / 1000));
    if (value <= 0) { finished = true; startedAt = null; remainingMs = 0; options.onElapsed(); }
    else timer = schedule(tick, Math.min(250, value));
  }
  return {
    resume() { if (disposed || finished || startedAt !== null) return; startedAt = now(); tick(); },
    pause() { if (disposed || finished) return; remainingMs = remaining(); startedAt = null; stopTimer(); options.onTick(Math.ceil(remainingMs / 1000)); },
    dispose() { disposed = true; stopTimer(); startedAt = null; },
  };
}
