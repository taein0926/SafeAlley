import type { AgentExecutionResponse } from "../types";

type Factor = NonNullable<AgentExecutionResponse["recommendation_factors"]>[number];
const labels: Record<Factor, string> = {
  distance: "거리 우선", safety: "안전시설 고려", stairs: "계단 회피", intersection: "교차로 회피",
};

export function RecommendationIcons({ factors }: { factors: Factor[] }) {
  if (!factors.length) return null;
  return <ul className="recommendation-icons" aria-label="추천에 반영된 조건">
    {factors.map((factor) => <li key={factor}>
      <svg viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        {factor === "distance" && <><path d="M6 11v19m28-19v19M7 20h26M13 15l-6 5 6 5m14-10 6 5-6 5"/><path d="M17 9h6" strokeWidth="4"/></>}
        {factor === "safety" && <><path d="M20 4 33 9v11c0 8-13 16-13 16S7 28 7 20V9Z" fill="currentColor" fillOpacity=".13"/><path d="m13 19 5 5 10-11"/></>}
        {factor === "stairs" && <path d="M5 33h8v-8h8v-8h8V9h7"/>}
        {factor === "intersection" && <><path d="M5 9h30M5 33h30"/>{[7, 15, 23, 31].map((x) => <path key={x} d={`M${x} 14v14`} strokeWidth="4"/>)}</>}
        {(factor === "stairs" || factor === "intersection") && <><path d="m23 3 13 13m0-13L23 16" stroke="#102535" strokeWidth="6"/><path d="m23 3 13 13m0-13L23 16" stroke="#ff8585" strokeWidth="3"/></>}
      </svg>
      <span>{labels[factor]}</span>
    </li>)}
  </ul>;
}
