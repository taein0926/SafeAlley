// Display-only debounce. This never schedules or changes Jev inference calls.
export const PREVIEW_COMPLETION_DELAY_MS = 2000;

export function createPreviewCompletion(options: {
  onChange: (completed: boolean) => void;
  schedule?: (callback: () => void, delay: number) => number;
  cancel?: (timer: number) => void;
}) {
  const schedule = options.schedule ?? ((callback, delay) => window.setTimeout(callback, delay));
  const cancel = options.cancel ?? ((timer) => window.clearTimeout(timer));
  let current = "", analyzed = "", quiet = false;
  let timer: number | undefined;
  const cancelTimer = () => { if (timer !== undefined) cancel(timer); timer = undefined; };
  const publish = () => options.onChange(quiet && !!current && current === analyzed);
  return {
    edit(text: string) {
      cancelTimer(); current = text.trim(); quiet = false; options.onChange(false);
      if (!current) { analyzed = ""; return; }
      timer = schedule(() => { timer = undefined; quiet = true; publish(); }, PREVIEW_COMPLETION_DELAY_MS);
    },
    pending() { analyzed = ""; options.onChange(false); },
    accept(text: string) { analyzed = text.trim(); publish(); },
    reset() { cancelTimer(); current = analyzed = ""; quiet = false; options.onChange(false); },
    dispose() { cancelTimer(); current = analyzed = ""; quiet = false; },
  };
}
