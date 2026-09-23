import { useEffect, useRef, useState } from "react";
import { browserSpeechEnvironment, SpeechCapture, type SpeechState } from "../speech";

export function SpeechInput({ value, onText, disabled }: {
  value: string; onText: (text: string) => void; disabled: boolean;
}) {
  const [state, setState] = useState<SpeechState>("idle");
  const [pendingText, setPendingText] = useState("");
  const current = useRef({ value, revision: 0, onText });
  if (current.current.value !== value) current.current.revision++;
  current.current.value = value;
  current.current.onText = onText;
  const capture = useRef<SpeechCapture | null>(null);
  const supported = typeof window !== "undefined" && window.isSecureContext
    && !!navigator.mediaDevices?.getUserMedia && typeof MediaRecorder !== "undefined";

  useEffect(() => {
    if (!supported) return;
    const session = new SpeechCapture(browserSpeechEnvironment(), setState, (text, revision) => {
      if (revision !== current.current.revision) {
        setPendingText(text);
      } else current.current.onText(text);
    });
    capture.current = session;
    const leave = () => session.cancel();
    window.addEventListener("pagehide", leave);
    return () => {
      window.removeEventListener("pagehide", leave);
      session.cancel(false);
      capture.current = null;
    };
  }, [supported]);

  useEffect(() => { if (disabled) capture.current?.cancel(); }, [disabled]);

  return <div className="speech-input">
    <div className="speech-actions">
      <button type="button" disabled={!supported || disabled || state === "permission" || state === "transcribing"}
        aria-pressed={state === "recording"}
        onClick={() => {
          if (state === "recording") capture.current?.stop();
          else { setPendingText(""); void capture.current?.start(current.current.revision); }
        }}>
        <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
          {state === "recording" ? <rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor" />
            : <><rect x="9" y="2" width="6" height="12" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2M12 19v3M8 22h8" /></>}
        </svg>
        {state === "recording" ? "녹음 중지" : state === "transcribing" ? "변환 중…" : state === "permission" ? "권한 확인 중…" : "음성 입력"}
      </button>
    </div>
    {pendingText && <div className="speech-preview"><p>{pendingText}</p><button type="button" disabled={disabled} onClick={() => {
      onText(pendingText); setPendingText("");
    }}>인식 내용으로 바꾸기</button></div>}
  </div>;
}
