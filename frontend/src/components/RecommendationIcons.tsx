import { type RecommendationFactor } from "../recommendationBadges";
import { CARD_STATE_LABELS, CONDITION_LABELS, conditionCards, type ConditionCard } from "../conditionCards";
import { ConditionIcon } from "./ConditionIcon";

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
          : factor === "bridge" ? "육교 선호는 현재 경로 비용에 독립적으로 반영되지 않습니다"
          : factor === "time" && applied ? `${period === "night" ? "야간" : "주간"} 시간대 정책을 사용했습니다`
          : applied ? "이번 추천의 평가 조건에 반영되었습니다" : "이번 추천의 평가 조건에 반영되지 않았습니다"}>
        <ConditionIcon factor={factor} applied={applied} />
        <span>{CONDITION_LABELS[factor]}</span>
      </span>;
    })}
  </span>;
}
