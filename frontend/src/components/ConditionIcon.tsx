import type { CardFactor } from "../conditionCards";

// One icon family for request conditions and map-layer controls.
export function ConditionIcon({ factor, applied = false, size = 16, showAvoidance = true }: {
  factor: CardFactor; applied?: boolean; size?: number; showAvoidance?: boolean;
}) {
  return <svg width={size} height={size} viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
    <g transform={factor === "streetlight" ? "translate(40 0) scale(-1 1)" : undefined}>
    {factor === "distance" && <><path d="M6 11v19m28-19v19M7 20h26M13 15l-6 5 6 5m14-10 6 5-6 5"/><path d="M17 9h6" strokeWidth="4"/></>}
    {factor === "safety" && <><path d="M20 4 33 9v11c0 8-13 16-13 16S7 28 7 20V9Z"/><path d="m13 19 5 5 10-11"/></>}
    {factor === "streetlight" && <><path d="M14 35V11c0-5 6-7 10-4l5 4M24 11h10l-2 6h-6Z"/><path d="m25 23-3 4m7-5v7m5-6 3 4M8 35h12"/></>}
    {factor === "cctv" && <g transform="scale(0.9090909)">
      <g transform="rotate(-25 22 22)">
        <path d="M11 14h21v11H11zM7 17h4v6H7zM9 12h25v3H9z"/>
        <path d="M23 26v6h10v-6" strokeWidth="3"/>
      </g>
    </g>}
    {factor === "stairs" && <path d="M5 33h8v-8h8v-8h8V9h7"/>}
    {factor === "crossing" && <><path d="M5 9h30M5 33h30"/>{[7, 15, 23, 31].map((x) => <path key={x} d={`M${x} 14v14`} strokeWidth="4"/>)}</>}
    {factor === "bridge" && <g transform="scale(0.9090909)"><path d="M5 33h5v-6h5v-6h14v6h5v6h5"/><path d="M15 21V12h14v9M22 12v9M17 22v12m10-12v12"/></g>}
    {factor === "time" && <><circle cx="20" cy="20" r="14"/><path d="M20 11v10l6 4"/></>}
    {showAvoidance && (factor === "stairs" || factor === "crossing") && <><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke="var(--badge-cutout)" strokeWidth="6"/><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke={applied ? "#ff8585" : "currentColor"} strokeWidth="3"/></>}
    </g>
  </svg>;
}
