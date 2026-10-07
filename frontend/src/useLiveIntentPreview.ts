import { useCallback, useEffect, useRef, useState } from "react";
import { emptyConditionCards, type ConditionCard } from "./conditionCards";
import { createPreviewScheduler, previewUnavailableMessage, requestIntentPreview, type PreviewStatus } from "./liveIntentPreview";

export function useLiveIntentPreview() {
  const [active, setActive] = useState(false);
  const [cards, setCards] = useState<ConditionCard[]>(() => emptyConditionCards());
  const [notice, setNotice] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [updating, setUpdating] = useState(false);
  const status = useRef<PreviewStatus | null>(null);
  const latestText = useRef("");
  const scheduler = useRef<ReturnType<typeof createPreviewScheduler> | null>(null);

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    const refreshStatus = () => fetch("/api/agent/intent-preview/status", { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json() as Promise<PreviewStatus>; })
      .then((data) => {
        if (!stopped) status.current = data;
        return data;
      });
    const localScheduler = createPreviewScheduler({
      request: requestIntentPreview,
      // Keep the last accepted judgment visible while the revised input is evaluated.
      onPending: () => { setActive(true); setBlocked(false); setUpdating(true); setNotice(null); },
      onResult: (result) => {
        setCards(result.conditions); setBlocked(false); setUpdating(false); setNotice(null);
        void refreshStatus().catch(() => {}); // Free local status request; no additional Jev inference.
      },
      onError: (error) => {
        localScheduler.pause(); // Do not leave another paid request queued after a failure.
        setBlocked(true);
        setUpdating(false);
        setNotice(error.message);
        void refreshStatus()
          .then((data) => { if (!stopped && !data.available) setNotice(previewUnavailableMessage(data)); })
          .catch(() => {});
      },
      onEmpty: () => { setActive(false); setCards(emptyConditionCards()); setUpdating(false); setNotice(null); },
    });
    scheduler.current = localScheduler;
    void refreshStatus()
      .then((data) => {
        if (!stopped) {
          status.current = data;
          if (latestText.current.trim()) {
            if (data.available) localScheduler.update(latestText.current);
            else { setBlocked(true); setNotice(previewUnavailableMessage(data)); }
          }
        }
      })
      .catch(() => { if (!stopped) status.current = null; });
    return () => { stopped = true; controller.abort(); localScheduler.dispose(); scheduler.current = null; };
  }, []);

  const update = useCallback((text: string) => {
    latestText.current = text;
    if (!text.trim()) { scheduler.current?.pause(); setActive(false); setCards(emptyConditionCards()); setUpdating(false); setNotice(null); return; }
    // Show the input panel immediately; keep inference on the existing word/idle schedule.
    setActive(true);
    if (!status.current?.available) {
      scheduler.current?.pause();
      setActive(true);
      setBlocked(true);
      setUpdating(false);
      setNotice(previewUnavailableMessage(status.current));
      return;
    }
    scheduler.current?.update(text);
  }, []);
  const pause = useCallback(() => { latestText.current = ""; scheduler.current?.pause(); setUpdating(false); }, []);
  const clear = useCallback(() => { latestText.current = ""; scheduler.current?.pause(); setActive(false); setCards(emptyConditionCards()); setUpdating(false); setNotice(null); }, []);
  return { active, cards, notice, blocked, updating, update, pause, clear };
}
