import type { RouteQueryResponse } from "../types";
import { progressMessages, requestedMetricRows } from "../routeProgress";
import type { RouteWorkUpdate } from "../routeProgress";

type Props = {
  stage: "interpreting" | "resolving" | "routing" | "done" | "failed";
  interpretation: RouteQueryResponse["interpretation"] | null;
  originName: string | null;
  destinationName: string | null;
  result: RouteQueryResponse["result"] | null;
  workUpdates: RouteWorkUpdate[];
};

export function RouteProgressPanel({ stage, interpretation, originName, destinationName, result, workUpdates }: Props) {
  const selected = result?.selected_route_type
    ? result.candidates.find((candidate) => candidate.route_type === result.selected_route_type)
    : undefined;
  const compared = result?.compared_route_type
    ? result.candidates.find((candidate) => candidate.route_type === result.compared_route_type)
    : undefined;
  const excludedFactors = new Set(result?.unsupported_preferences.map((item) => item.factor) ?? []);
  const rows = selected
    ? requestedMetricRows(interpretation, selected, compared).filter((row) => !excludedFactors.has(row.factor))
    : [];
  const messages = progressMessages(stage, interpretation, originName, destinationName, result, workUpdates);
  const hasLocationIndicator = rows.some((row) => row.factor === "streetlight_score" || row.factor === "cctv_score");

  return (
    <section className="route-progress" aria-label="경로 검색 처리 과정">
      <h2>{stage === "done" ? "이렇게 길을 찾았어요" : stage === "failed" ? "경로 검색을 마치지 못했어요" : "길을 찾고 있어요"}</h2>
      <div className="route-progress-log" role="log" aria-live="polite" aria-relevant="additions text">
        {messages.map((message) => (
          <p key={message.id} className={`route-progress-message${message.pending ? " route-progress-message--pending" : ""}`}>
            <span className="route-progress-avatar" aria-hidden="true">↗</span>
            <span>{message.text}{message.pending && <span className="route-progress-dots" aria-hidden="true">···</span>}</span>
          </p>
        ))}
      </div>
      {stage === "done" && selected && rows.length > 0 && (
        <details className="route-progress-comparison">
          <summary>계산값 자세히 보기</summary>
          <table>
            <thead><tr><th scope="col">기준</th><th scope="col">추천</th><th scope="col">비교</th></tr></thead>
            <tbody>{rows.map((row) => (
              <tr key={row.factor}><th scope="row">{row.label}</th><td>{row.selected}</td><td>{row.shortest ?? "비교 없음"}</td></tr>
            ))}</tbody>
          </table>
          {hasLocationIndicator && (
            <p className="route-progress-note">위치 지표는 시설 개수나 실제 밝기·안전도를 뜻하지 않습니다.</p>
          )}
        </details>
      )}
      {stage === "done" && hasLocationIndicator && (
        <p className="route-progress-note">가로등·CCTV는 등록 위치 기반 지표이며 실제 밝기·안전도를 뜻하지 않습니다.</p>
      )}
    </section>
  );
}
