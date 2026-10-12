import { useEffect, useId, useRef, useState } from "react";

const LABELS = ["가로등 · 계단", "CCTV", "가로등 · 건널목", "CCTV · 건널목"] as const;

export function ExamplePicker({ examples, disabled, onSelect }: {
  examples: readonly string[];
  disabled: boolean;
  onSelect: (text: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const menuId = useId();

  useEffect(() => { if (disabled) setOpen(false); }, [disabled]);
  useEffect(() => {
    if (!open) return;
    function outside(event: PointerEvent) {
      if (!root.current?.contains(event.target as Node)) setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      event.preventDefault();
      setOpen(false);
      trigger.current?.focus();
    }
    document.addEventListener("pointerdown", outside);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", outside);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);

  return <div className="example-picker" ref={root}>
    <button ref={trigger} type="button" className="example-picker-trigger" aria-expanded={open} aria-controls={menuId} disabled={disabled} onClick={() => setOpen((value) => !value)}>
      예시 선택 <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true"><path d={open ? "m4 6 4 4 4-4" : "m4 10 4-4 4 4"} /></svg>
    </button>
    {open && <div id={menuId} className="search-examples" role="group" aria-label="예시 경로 검색">
      {examples.map((example, index) => <button key={example} type="button" disabled={disabled} onClick={() => { setOpen(false); onSelect(example); }}>
        <span className="search-example-label">{LABELS[index]}</span>
      </button>)}
    </div>}
  </div>;
}
