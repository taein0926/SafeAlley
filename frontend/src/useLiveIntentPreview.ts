import { useCallback, useEffect, useRef, useState } from "react";
import { emptyConditionCards, type ConditionCard } from "./conditionCards";
import { createPreviewScheduler, previewUnavailableMessage, requestIntentPreview, type PreviewStatus } from "./liveIntentPreview";
import { createPreviewCompletion } from "./previewCompletion";

export function useLiveIntentPreview() {
  const [active, setActive] = useState(false);
  const [cards, setCards] = useState<ConditionCard[]>(() => emptyConditionCards("not_applied"));
  const [notice, setNotice] = useState<string | null>(null);
  const [blocked, setBlocked] = useState(false);
  const [updating, setUpdating] = useState(false);
  const [completed, setCompleted] = useState(false);
  const completion = useRef<ReturnType<typeof createPreviewCompletion> | null>(null);
  const status = useRef<PreviewStatus | null>(null);
  const latestText = useRef("");
  const analyzedText = useRef("");
  const scheduler = useRef<ReturnType<typeof createPreviewScheduler> | null>(null);

  useEffect(() => {
    let stopped = false;
    const controller = new AbortController();
    const completionGate = createPreviewCompletion({ onChange: setCompleted });
    completion.current = completionGate;
    const refreshStatus = () => fetch("/api/agent/intent-preview/status", { signal: controller.signal })
      .then(async (response) => { if (!response.ok) throw new Error(); return response.json() as Promise<PreviewStatus>; })
      .then((data) => {
        if (!stopped) status.current = data;
        return data;
      });
    const localScheduler = createPreviewScheduler({
      request: requestIntentPreview,
      // Keep the last accepted judgment visible while the revised input is evaluated.
      onPending: () => { completionGate.pending(); setActive(true); setBlocked(false); setUpdating(true); setNotice(null); },
      onResult: (result) => {
        analyzedText.current = result.query;
        setCards(result.conditions); setBlocked(false);
        setUpdating(result.query !== latestText.current.trim()); setNotice(null);
        completionGate.accept(result.query);
        void refreshStatus().catch(() => {}); // Free local status request; no additional Jev inference.
      },
      onError: (error) => {
        completionGate.reset();
        localScheduler.pause(); // Do not leave another paid request queued after a failure.
        setBlocked(true);
        setUpdating(false);
        setNotice(error.message);
        void refreshStatus()
          .then((data) => { if (!stopped && !data.available) setNotice(previewUnavailableMessage(data)); })
          .catch(() => {});
      },
      onEmpty: () => { completionGate.reset(); analyzedText.current = ""; setActive(false); setCards(emptyConditionCards("not_applied")); setBlocked(false); setUpdating(false); setNotice(null); },
    });
    scheduler.current = localScheduler;
    void refreshStatus()
      .then((data) => {
        if (!stopped) {
          status.current = data;
          if (latestText.current.trim()) {
            if (data.available) { completionGate.edit(latestText.current); localScheduler.update(latestText.current); }
            else { setBlocked(true); setNotice(previewUnavailableMessage(data)); }
          }
        }
      })
      .catch(() => { if (!stopped) status.current = null; });
    return () => { stopped = true; controller.abort(); localScheduler.dispose(); scheduler.current = null; completionGate.dispose(); completion.current = null; };
  }, []);

  const update = useCallback((text: string) => {
    const wasEmpty = !latestText.current.trim();
    completion.current?.edit(text);
    latestText.current = text;
    if (!text.trim()) { analyzedText.current = ""; scheduler.current?.pause(); setActive(false); setCards(emptyConditionCards("not_applied")); setBlocked(false); setUpdating(false); setNotice(null); return; }
    // Show the input panel immediately; keep inference on the existing word/idle schedule.
    setActive(true);
    if (!status.current?.available) {
      completion.current?.reset();
      scheduler.current?.pause();
      setActive(true);
      setBlocked(true);
      setUpdating(false);
      setNotice(previewUnavailableMessage(status.current));
      return;
    }
    setBlocked(false);
    setNotice(null);
    if (wasEmpty && !analyzedText.current) setCards(emptyConditionCards());
    setUpdating(text.trim() !== analyzedText.current);
    scheduler.current?.update(text);
  }, []);
  const pause = useCallback(() => {
    const latestAccepted = !!latestText.current.trim() && analyzedText.current === latestText.current.trim();
    completion.current?.reset(); latestText.current = ""; scheduler.current?.pause(); setUpdating(false);
    setCompleted(latestAccepted);
  }, []);
  const clear = useCallback(() => { completion.current?.reset(); latestText.current = ""; analyzedText.current = ""; scheduler.current?.pause(); setActive(false); setCards(emptyConditionCards("not_applied")); setBlocked(false); setUpdating(false); setNotice(null); }, []);
  return { active, cards, notice, blocked, updating, completed, update, pause, clear };
}
