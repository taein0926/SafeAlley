import { recommendationBadges, type RecommendationFactor } from "../recommendationBadges";

type Factor = RecommendationFactor;
const labels: Record<Factor, string> = {
  distance: "최단 거리", safety: "안전시설", stairs: "계단 회피", crossing: "건널목 회피",
};

export function RecommendationIcons({ factors }: { factors: Factor[] }) {
  return <span className="recommendation-icons" role="list" aria-label="추천 조건 적용 여부">
    {recommendationBadges(factors).map(({ factor, applied }) => <span role="listitem" className="recommendation-badge"
      key={factor}
      data-applied={applied}
      aria-label={`${labels[factor]}: ${applied ? "적용" : "미적용"}`}
      title={applied ? "이번 추천의 평가 조건에 반영되었습니다" : "이번 추천의 평가 조건에 반영되지 않았습니다"}
    >
      <svg viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
        {factor === "distance" && <><path d="M6 11v19m28-19v19M7 20h26M13 15l-6 5 6 5m14-10 6 5-6 5"/><path d="M17 9h6" strokeWidth="4"/></>}
        {factor === "safety" && <><path d="M20 4 33 9v11c0 8-13 16-13 16S7 28 7 20V9Z" fill="currentColor" fillOpacity=".13"/><path d="m13 19 5 5 10-11"/></>}
        {factor === "stairs" && <path d="M5 33h8v-8h8v-8h8V9h7"/>}
        {factor === "crossing" && <><path d="M5 9h30M5 33h30"/>{[7, 15, 23, 31].map((x) => <path key={x} d={`M${x} 14v14`} strokeWidth="4"/>)}</>}
        {(factor === "stairs" || factor === "crossing") && <><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke="var(--badge-cutout)" strokeWidth="6"/><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke={applied ? "#ff8585" : "currentColor"} strokeWidth="3"/></>}
      </svg>
      <span>{labels[factor]}</span>
      <small className="recommendation-badge-status"><b aria-hidden="true">{applied ? "✓" : "—"}</b> {applied ? "적용" : "미적용"}</small>
    </span>)}
  </span>;
}
