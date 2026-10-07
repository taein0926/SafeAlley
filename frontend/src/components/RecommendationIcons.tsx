import { type RecommendationFactor } from "../recommendationBadges";
import { CARD_STATE_LABELS, CONDITION_LABELS, conditionCards, type ConditionCard } from "../conditionCards";

export function RecommendationIcons({ factors, conditions, preview = false }: {
  factors: RecommendationFactor[]; conditions?: ConditionCard[]; preview?: boolean;
}) {
  return <span className="recommendation-icons" role="list" aria-label={preview ? "실시간 분석" : "추천 조건 적용 여부"}>
    {conditionCards(factors, conditions).map(({ factor, state, period }) => {
      const applied = state === "applied";
      const status = CARD_STATE_LABELS[state];
      return <span role="listitem" className="recommendation-badge" key={factor}
        data-applied={applied} data-state={state}
        aria-label={`${CONDITION_LABELS[factor]}: ${status}`}
        title={state === "analyzing" ? "문장을 읽거나 이어지는 내용을 기다리고 있습니다"
          : preview ? "입력 중 해석한 요청입니다. 실제 경로 반영은 검색 후 확정됩니다"
          : factor === "time" && applied ? `${period === "night" ? "야간" : "주간"} 시간대 정책을 사용했습니다`
          : applied ? "이번 추천의 평가 조건에 반영되었습니다" : "이번 추천의 평가 조건에 반영되지 않았습니다"}>
        <svg viewBox="0 0 40 40" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          {factor === "distance" && <><path d="M6 11v19m28-19v19M7 20h26M13 15l-6 5 6 5m14-10 6 5-6 5"/><path d="M17 9h6" strokeWidth="4"/></>}
          {factor === "safety" && <><path d="M20 4 33 9v11c0 8-13 16-13 16S7 28 7 20V9Z" fill="currentColor" fillOpacity=".13"/><path d="m13 19 5 5 10-11"/></>}
          {factor === "streetlight" && <><path d="M14 35V11c0-5 6-7 10-4l5 4M24 11h10l-2 6h-6Z"/><path d="m25 23-3 4m7-5v7m5-6 3 4M8 35h12"/></>}
          {factor === "cctv" && <><path d="m6 12 22-6 5 12-22 6ZM15 24v6h13M28 30v5"/><path d="m29 12 6-2 3 7-5 2"/></>}
          {factor === "stairs" && <path d="M5 33h8v-8h8v-8h8V9h7"/>}
          {factor === "crossing" && <><path d="M5 9h30M5 33h30"/>{[7, 15, 23, 31].map((x) => <path key={x} d={`M${x} 14v14`} strokeWidth="4"/>)}</>}
          {factor === "time" && <><circle cx="20" cy="20" r="14"/><path d="M20 11v10l6 4"/></>}
          {(factor === "stairs" || factor === "crossing") && <><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke="var(--badge-cutout)" strokeWidth="6"/><path d="M13.5 13.5 26.5 26.5M26.5 13.5 13.5 26.5" stroke={applied ? "#ff8585" : "currentColor"} strokeWidth="3"/></>}
        </svg>
        <span>{CONDITION_LABELS[factor]}</span>
        <small className="recommendation-badge-status"><b aria-hidden="true">{state === "analyzing" ? "···" : applied ? "✓" : "—"}</b> {status}</small>
      </span>;
    })}
  </span>;
}
