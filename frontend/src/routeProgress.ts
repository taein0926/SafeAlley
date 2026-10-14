import type { RouteQueryResponse, RouteCandidate } from "./types";
import { errorFromApiDetail } from "./placeSelection.ts";
import type { SelectedPlaces } from "./placeSelection.ts";

export type RouteWorkUpdate = { id: string; message: string; state: "working" | "completed" | "unavailable" };

export function mergeWorkUpdate(updates: RouteWorkUpdate[], incoming: RouteWorkUpdate): RouteWorkUpdate[] {
  return updates.some((item) => item.id === incoming.id)
    ? updates.map((item) => item.id === incoming.id ? incoming : item)
    : [...updates, incoming];
}

export type RouteProgressEvent =
  | { type: "stage"; stage: "interpreting" | "resolving" | "routing" }
  | { type: "interpreted"; data: RouteQueryResponse["interpretation"] }
  | { type: "route_progress"; data: RouteWorkUpdate }
  | { type: "resolved"; origin: RouteQueryResponse["resolved_origin"]; destination: RouteQueryResponse["resolved_destination"] }
  | { type: "result"; data: RouteQueryResponse }
  | { type: "error"; detail: unknown };

export async function queryRouteWithProgress(
  query: string,
  userId: string,
  onEvent: (event: RouteProgressEvent) => void,
  places?: SelectedPlaces,
): Promise<RouteQueryResponse> {
  const response = await fetch("/api/agent/query/stream", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "application/x-ndjson" },
    body: JSON.stringify({ query, source: "osm", user_id: userId,
      ...(places?.origin && places.destination ? {
        origin: { latitude: places.origin.latitude, longitude: places.origin.longitude },
        destination: { latitude: places.destination.latitude, longitude: places.destination.longitude },
      } : {}),
    }),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => ({})) as { detail?: unknown };
    throw errorFromApiDetail(payload.detail, `HTTP ${response.status}`);
  }
  if (!response.body) throw new Error("진행 상태를 받을 수 없습니다.");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: RouteQueryResponse | null = null;

  function processLine(line: string) {
    if (!line.trim()) return;
    const event = JSON.parse(line) as RouteProgressEvent;
    if (event.type === "error") throw errorFromApiDetail(event.detail, "경로 검색에 실패했습니다.");
    if (event.type === "result") result = event.data;
    onEvent(event);
  }

  try {
    while (true) {
      const { value, done } = await reader.read();
      buffer += decoder.decode(value, { stream: !done });
      let lineEnd = buffer.indexOf("\n");
      while (lineEnd >= 0) {
        processLine(buffer.slice(0, lineEnd));
        buffer = buffer.slice(lineEnd + 1);
        lineEnd = buffer.indexOf("\n");
      }
      if (done) break;
    }
    processLine(buffer);
  } finally {
    reader.releaseLock();
  }
  if (!result) throw new Error("경로 검색 결과를 받지 못했습니다.");
  return result;
}

export const FACTOR_LABELS: Record<string, string> = {
  distance_m: "거리",
  streetlight_score: "가로등 위치 지표",
  cctv_score: "CCTV 위치 지표",
  crosswalk_count: "등록된 횡단보도",
  stairs_distance_m: "계단 구간",
  safety_score: "복합 안전 지표",
  sidewalk_coverage_percent: "보도 구간 비율",
  max_slope_percent: "경사",
  police_accessibility: "경찰서 접근성",
  elevator_accessibility: "승강기 접근성",
  wheelchair_accessibility: "휠체어 접근성",
  stroller_accessibility: "유모차 접근성",
  crowd_density: "혼잡도",
  noise_level: "소음",
  traffic_congestion: "교통 혼잡",
};

export type ConditionDecision = {
  factor: string;
  question: string;
  answer: "요청함" | "요청 없음";
  application: string | null;
  state: "requested" | "absent" | "applied" | "excluded" | "pending";
};

const CONDITION_QUESTIONS = [
  { factor: "stairs_distance_m", question: "계단을 피하고 싶은가?", directions: ["avoid", "minimize"] },
  { factor: "streetlight_score", question: "가로등이 많은 길을 원하는가?", directions: ["maximize"] },
  { factor: "cctv_score", question: "CCTV를 우선하는가?", directions: ["maximize"] },
  { factor: "crosswalk_count", question: "횡단보도를 적게 지나고 싶은가?", directions: ["avoid", "minimize"] },
] as const;

export function conditionDecisions(
  interpretation: RouteQueryResponse["interpretation"],
  result: RouteQueryResponse["result"] | null,
): ConditionDecision[] {
  const rows: ConditionDecision[] = [];
  const covered = new Set<string>();
  const unsupported = new Map(result?.unsupported_preferences.map((item) => [item.factor, item.reason]) ?? []);

  function application(factor: string): Pick<ConditionDecision, "application" | "state"> {
    if (!result) return { application: "경로 반영 여부 확인 중", state: "pending" };
    if (factor === "crosswalk_count" && result.recommendation_conditions?.some(card =>
      card.factor === "crossing" && card.state === "applied" && card.application_scope === "route_generation")) {
      return { application: "경로 탐색 비용에 반영 — 전체 건널목 비교는 별도", state: "applied" };
    }
    const reason = unsupported.get(factor);
    if (reason === "Excluded during daylight") return { application: "주간 경로에서 제외", state: "excluded" };
    if (reason?.includes("No generated route satisfies")) return { application: "조건을 만족하는 경로 없음", state: "excluded" };
    if (reason?.includes("data is unavailable")) return { application: "자료 부족으로 반영 못함", state: "excluded" };
    if (reason) return { application: "지원되지 않아 반영 못함", state: "excluded" };
    if (result.recommendation_status !== "ready") return { application: "추천 보류 — 적용 여부 미확정", state: "pending" };
    return { application: "경로 계산에 반영", state: "applied" };
  }

  for (const item of CONDITION_QUESTIONS) {
    const preference = interpretation.preferences.find((candidate) => candidate.factor === item.factor);
    const requested = preference !== undefined && (item.directions as readonly string[]).includes(preference.direction);
    if (requested) covered.add(item.factor);
    rows.push({
      factor: item.factor,
      question: item.question,
      answer: requested ? "요청함" : "요청 없음",
      ...(requested ? application(item.factor) : { application: null, state: "absent" as const }),
    });
  }
  for (const preference of interpretation.preferences) {
    if (covered.has(preference.factor)) continue;
    const label = FACTOR_LABELS[preference.factor] ?? preference.factor;
    rows.push({
      factor: preference.factor,
      question: `‘${label}’ 조건을 요청했는가?`,
      answer: "요청함",
      ...application(preference.factor),
    });
  }
  return rows;
}

export type ProgressMessage = {
  id: string;
  text: string;
  pending: boolean;
};

type ProgressStage = "interpreting" | "resolving" | "routing" | "done" | "failed";

function intentDescription(interpretation: RouteQueryResponse["interpretation"]): string {
  const labels = interpretation.preferences.map(({ factor, direction }) => {
    if (factor === "stairs_distance_m") return direction === "avoid" ? "계단 회피" : "계단 구간 줄이기";
    if (factor === "streetlight_score") return "가로등 위치 우선";
    if (factor === "cctv_score") return "CCTV 위치 우선";
    if (factor === "crosswalk_count") return "횡단보도 적게 지나기";
    if (factor === "distance_m") return "짧은 거리";
    if (factor === "safety_score") return "안전시설 지표 우선";
    if (factor === "sidewalk_coverage_percent") return "보도 구간 우선";
    return FACTOR_LABELS[factor] ?? "추가 경로 조건";
  });
  if (!labels.length) return "출발지와 도착지를 확인해 경로를 찾을게요.";
  return `말씀하신 조건을 ${labels.join(", ")}로 이해했어요.`;
}

function metric(candidate: RouteCandidate | undefined, factor: string): number | null {
  const value = candidate?.metrics[factor];
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function routeDescription(
  interpretation: RouteQueryResponse["interpretation"] | null,
  result: RouteQueryResponse["result"],
): string {
  const selected = result.candidates.find((candidate) => candidate.route_type === result.selected_route_type);
  if (!selected) {
    return result.recommendation_status === "field_review_required"
      ? "경로 후보는 찾았지만 현장 확인이 필요한 구간이 있어 자동 추천을 보류했어요."
      : "경로 후보는 찾았지만 이번에는 맞춤 경로를 확정하지 못했어요.";
  }
  const compared = result.candidates.find((candidate) => candidate.route_type === result.compared_route_type);
  const selectedDistance = metric(selected, "distance_m");
  const comparedDistance = metric(compared, "distance_m");
  const parts: string[] = [];
  if (selectedDistance !== null) {
    parts.push(comparedDistance !== null
      ? `맞춤 경로는 약 ${Math.round(selectedDistance)}m, 비교 길은 약 ${Math.round(comparedDistance)}m예요.`
      : `맞춤 경로는 약 ${Math.round(selectedDistance)}m예요.`);
  }
  const requested = new Set(interpretation?.preferences.map((item) => item.factor) ?? []);
  const excluded = new Set(result.unsupported_preferences.map((item) => item.factor));
  if (compared && requested.has("stairs_distance_m") && !excluded.has("stairs_distance_m")) {
    const chosen = metric(selected, "stairs_distance_m");
    const other = metric(compared, "stairs_distance_m");
    if (chosen !== null && other !== null) {
      parts.push(chosen === 0 && other > 0
        ? `기록된 계단 구간은 맞춤 경로에 없고, 비교 길에는 약 ${Math.round(other)}m 있어요.`
        : `기록된 계단 구간은 맞춤 경로 약 ${Math.round(chosen)}m, 비교 길 약 ${Math.round(other)}m예요.`);
    }
  }
  for (const [factor, label] of [
    ["streetlight_score", "가로등"],
    ["cctv_score", "CCTV"],
  ] as const) {
    if (!compared || !requested.has(factor) || excluded.has(factor)) continue;
    const chosen = metric(selected, factor);
    const other = metric(compared, factor);
    if (chosen === null || other === null) continue;
    const comparison = chosen === other ? "두 길이 같아요" : chosen > other ? "맞춤 경로가 더 높아요" : "비교 길이 더 높아요";
    parts.push(`${label} 위치 지표는 맞춤 경로 ${chosen.toFixed(1)}, 비교 길 ${other.toFixed(1)}로 ${comparison}.`);
  }
  if (compared && requested.has("crosswalk_count") && !excluded.has("crosswalk_count")) {
    const chosen = metric(selected, "crosswalk_count");
    const other = metric(compared, "crosswalk_count");
    if (chosen !== null && other !== null) {
      parts.push(`등록된 횡단보도는 맞춤 경로 ${Math.round(chosen)}개, 비교 길 ${Math.round(other)}개예요.`);
    }
  }
  return parts.join(" ") || "요청 조건에 맞는 맞춤 경로를 찾았어요. 아래에서 경로를 확인해 주세요.";
}

export function progressMessages(
  stage: ProgressStage,
  interpretation: RouteQueryResponse["interpretation"] | null,
  originName: string | null,
  destinationName: string | null,
  result: RouteQueryResponse["result"] | null,
  workUpdates: RouteWorkUpdate[] = [],
): ProgressMessage[] {
  if (!interpretation) return [{ id: "intent", text: stage === "failed" ? "질문 해석을 완료하지 못했어요." : "질문을 살펴보고 있어요", pending: stage !== "failed" }];
  const messages: ProgressMessage[] = [
    { id: "intent", text: intentDescription(interpretation), pending: false },
  ];
  if (stage === "resolving") {
    messages.push({ id: "places", text: "출발지와 도착지를 확인하고 있어요", pending: true });
  } else if (stage === "routing" || stage === "done" || stage === "failed") {
    const placeText = originName && destinationName
      ? `${originName}에서 ${destinationName}까지의 위치를 확인했어요.`
      : "출발지와 도착지 좌표를 확인했어요.";
    if (stage !== "failed" || (originName && destinationName)) messages.push({ id: "places", text: placeText, pending: false });
    messages.push(...workUpdates.map((item) => ({
      id: `work-${item.id}`, text: stage === "failed" && item.state === "working" ? `${item.message} 이 단계에서 검색이 중단됐어요.` : item.message,
      pending: item.state === "working" && stage !== "failed",
    })));
    if (stage === "routing" && workUpdates.length === 0) {
      messages.push({ id: "routes", text: "도로망에서 경로 후보를 만들고 비교하고 있어요", pending: true });
    } else if (stage === "done" && result) {
      messages.push({ id: "routes", text: routeDescription(interpretation, result), pending: false });
      const excluded = conditionDecisions(interpretation, result).filter((item) => item.state === "excluded");
      if (excluded.length) {
        const exclusionText = (item: ConditionDecision): string => {
          const label = FACTOR_LABELS[item.factor] ?? item.factor;
          if (item.application === "주간 경로에서 제외") return `${label} 조건은 낮 시간대라 계산에서 제외했어요.`;
          if (item.application === "자료 부족으로 반영 못함") return `${label} 조건은 자료가 부족해 반영하지 못했어요.`;
          if (item.application === "조건을 만족하는 경로 없음") return `${label} 조건을 만족하는 경로를 찾지 못했어요.`;
          return `${label} 조건은 이번 경로 계산에 반영하지 못했어요.`;
        };
        messages.push({
          id: "limits",
          text: excluded.map(exclusionText).join(" "),
          pending: false,
        });
      }
    }
  }
  return messages;
}
