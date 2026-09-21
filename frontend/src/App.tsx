import { useCallback, useEffect, useMemo, useState } from "react";

import {
  CesiumRoadMap,
  type RoadMapStatus,
} from "./components/CesiumRoadMap";
import type { RouteCandidate, RouteQueryResponse, RouteType } from "./types";

type HealthResponse = {
  status: string;
  service: string;
  database: {
    status: string;
    name?: string;
    postgis_version?: string;
    message?: string;
  };
};

type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; data: HealthResponse }
  | { kind: "error"; message: string };

type RouteSearchState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; data: RouteQueryResponse }
  | { kind: "error"; message: string };

const routeLabels: Record<RouteType, { title: string; summary: string }> = {
  shortest: { title: "빠른 길", summary: "이동 거리를 가장 짧게" },
  balanced: { title: "균형 길", summary: "거리와 안전도를 함께 고려" },
  safe: { title: "안전지표 우선", summary: "CCTV·도움시설 접근성을 우선" },
};

function anonymousUserId(): string {
  const storageKey = "safealley-user-id";
  const saved = window.localStorage.getItem(storageKey);
  if (saved) return saved;
  const created = window.crypto.randomUUID();
  window.localStorage.setItem(storageKey, created);
  return created;
}

function formatDistance(value: number): string {
  return value >= 1000 ? `${(value / 1000).toFixed(2)} km` : `${Math.round(value)} m`;
}

function metric(candidate: RouteCandidate, key: string): number | null {
  const value = candidate.metrics[key];
  return typeof value === "number" ? value : null;
}

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [roads, setRoads] = useState<RoadMapStatus>({ kind: "loading" });
  const [query, setQuery] = useState("밤 10시에 주안역에서 인천사랑병원까지 CCTV와 도움시설 접근성이 좋은 길로 안내해줘");
  const [routeSearch, setRouteSearch] = useState<RouteSearchState>({ kind: "idle" });
  const [selectedRouteType, setSelectedRouteType] = useState<RouteType | null>(null);
  const [selectionMessage, setSelectionMessage] = useState("");

  useEffect(() => {
    const controller = new AbortController();

    async function loadHealth() {
      try {
        const response = await fetch("/api/health", {
          signal: controller.signal,
          headers: { Accept: "application/json" },
        });
        const data = (await response.json()) as HealthResponse;
        if (!response.ok) throw new Error(data.database.message ?? `HTTP ${response.status}`);
        setHealth({ kind: "ready", data });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        const message = error instanceof Error ? error.message : "Unknown error";
        setHealth({ kind: "error", message });
      }
    }

    void loadHealth();
    return () => controller.abort();
  }, []);

  const handleRoadStatus = useCallback((status: RoadMapStatus) => {
    setRoads(status);
  }, []);

  const systemReady = health.kind === "ready" && roads.kind === "ready";
  const componentDataReady =
    roads.kind === "ready" && roads.cctvCount > 0 && roads.helpPointCount > 0;
  const routeCandidates = routeSearch.kind === "ready" ? routeSearch.data.result.candidates : [];
  const selectedCandidate = routeCandidates.find(
    (candidate) => candidate.route_type === selectedRouteType,
  );
  const userId = useMemo(anonymousUserId, []);

  async function searchRoutes(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setRouteSearch({ kind: "loading" });
    setSelectionMessage("");

    try {
      const response = await fetch("/api/agent/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          query: query.trim(),
          source: "osm",
          user_id: userId,
        }),
      });
      const data = (await response.json()) as RouteQueryResponse | { detail?: string };
      if (!response.ok) {
        throw new Error("detail" in data && data.detail ? data.detail : `HTTP ${response.status}`);
      }
      const result = data as RouteQueryResponse;
      setRouteSearch({ kind: "ready", data: result });
      setSelectedRouteType(result.result.selected_route_type);
    } catch (error) {
      setRouteSearch({
        kind: "error",
        message: error instanceof Error ? error.message : "경로 검색에 실패했습니다.",
      });
    }
  }

  async function selectRoute(routeType: RouteType) {
    setSelectedRouteType(routeType);
    setSelectionMessage("");
    if (routeSearch.kind !== "ready" || !routeSearch.data.result.recommendation_id) return;

    try {
      const response = await fetch("/api/agent/route-selections", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          recommendation_id: routeSearch.data.result.recommendation_id,
          user_id: userId,
          selected_route_type: routeType,
        }),
      });
      const data = (await response.json()) as { detail?: string };
      if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
      setSelectionMessage(`${routeLabels[routeType].title} 선택을 저장했습니다.`);
    } catch (error) {
      setSelectionMessage(error instanceof Error ? `선택 저장 실패: ${error.message}` : "선택 저장 실패");
    }
  }

  return (
    <main className="app-shell">
      <CesiumRoadMap
        onStatusChange={handleRoadStatus}
        routeCandidates={routeCandidates}
        selectedRouteType={selectedRouteType}
      />

      <aside className="map-panel">
        <p className="eyebrow">MICHUHOL-GU · AI SAFETY ROUTING</p>
        <h1>SafeAlley</h1>
        <p className="description">원하는 이동 조건을 말하면 세 가지 경로를 비교해 보여줍니다.</p>

        <form className="route-form" onSubmit={searchRoutes}>
          <label htmlFor="route-query">어떤 길을 원하세요?</label>
          <textarea
            id="route-query"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            rows={4}
            required
          />
          <button className="search-button" type="submit" disabled={routeSearch.kind === "loading"}>
            {routeSearch.kind === "loading" ? "AI가 경로를 분석하는 중…" : "3개 경로 찾기"}
          </button>
        </form>

        {routeSearch.kind === "error" && <p className="route-error" role="alert">{routeSearch.message}</p>}

        {routeCandidates.length > 0 && (
          <section className="route-results" aria-label="경로 후보">
            <div className="result-heading">
              <h2>경로 후보 {routeCandidates.length}개</h2>
              <span>{routeSearch.kind === "ready" ? routeSearch.data.model : ""}</span>
            </div>
            {routeSearch.kind === "ready" && routeSearch.data.result.recommendation_status === "field_review_required" && (
              <p className="route-review-warning" role="status">
                모든 후보에 현장 확인이 필요한 대로 구간이 있어 최종 추천을 보류했습니다.
                후보를 눌러 검토용 경로를 볼 수 있습니다.
              </p>
            )}
            {routeSearch.kind === "ready" && routeSearch.data.resolved_origin && routeSearch.data.resolved_destination && (
              <p className="resolved-places">
                {routeSearch.data.resolved_origin.name} → {routeSearch.data.resolved_destination.name}
              </p>
            )}
            <div className="route-cards">
              {routeCandidates.map((candidate) => {
                const active = candidate.route_type === selectedRouteType;
                const safety = metric(candidate, "safety_score") ?? candidate.route.properties.average_safety_score;
                return (
                  <button
                    key={candidate.route_type}
                    type="button"
                    className={`route-card route-card--${candidate.route_type} ${active ? "route-card--active" : ""}`}
                    onClick={() => void selectRoute(candidate.route_type)}
                    aria-pressed={active}
                  >
                    <strong>{routeLabels[candidate.route_type].title}</strong>
                    <small>{routeLabels[candidate.route_type].summary}</small>
                    <small className="route-review-label">
                      {candidate.route.properties.unverified_major_road_count > 0
                        ? `현장 확인 필요 · ${candidate.route.properties.unverified_major_road_count}구간`
                        : "지도 자료 기반 · 현장 미검증"}
                    </small>
                    <dl>
                      <div><dt>거리</dt><dd>{formatDistance(candidate.route.properties.total_distance_m)}</dd></div>
                      <div><dt>안전도</dt><dd>{safety == null ? "-" : safety.toFixed(1)}</dd></div>
                      <div><dt>CCTV</dt><dd>{metric(candidate, "cctv_score")?.toFixed(1) ?? "-"}</dd></div>
                    </dl>
                  </button>
                );
              })}
            </div>
            {selectedCandidate && (
              <>
              {selectedCandidate.route.properties.unverified_major_road_count > 0 && (
                <p className="route-review-warning" role="status">
                  이 후보에는 보행 가능 여부가 확인되지 않은 대로 구간이
                  {selectedCandidate.route.properties.unverified_major_road_count}개 있습니다.
                  합법적인 횡단과 보도 연결을 확인하기 전에는 안전한 경로로 안내할 수 없습니다.
                </p>
              )}
              <dl className="walking-metrics" aria-label="선택 경로 보행 지표">
                <div><dt>횡단보도</dt><dd>{selectedCandidate.route.properties.total_crosswalk_count}개</dd></div>
                <div><dt>계단</dt><dd>{Math.round(selectedCandidate.route.properties.stairs_distance_m)}m</dd></div>
                <div><dt>확인 보행공간</dt><dd>{selectedCandidate.route.properties.sidewalk_coverage_percent.toFixed(0)}%</dd></div>
                <div><dt>최대 경사</dt><dd>{selectedCandidate.route.properties.max_slope_percent == null ? "데이터 부족" : `${selectedCandidate.route.properties.max_slope_percent.toFixed(1)}%`}</dd></div>
              </dl>
              </>
            )}
            {selectionMessage && <p className="selection-message" aria-live="polite">{selectionMessage}</p>}
          </section>
        )}

        <div className="status-row">
          <span className={`indicator ${systemReady ? "indicator--ready" : ""}`} />
          <span>
            {systemReady
              ? componentDataReady
                ? "종합 안전도 데이터 흐름 정상"
                : "기존 레이어 정상 · 신규 원천 적재 대기"
              : "데이터 흐름 확인 중"}
          </span>
        </div>

        <details className="data-details">
          <summary>지도 데이터 상태</summary>
        <dl className="service-list">
          <div>
            <dt>Backend / PostGIS</dt>
            <dd>
              {health.kind === "ready" && `${health.data.database.name} · 연결됨`}
              {health.kind === "loading" && "확인 중"}
              {health.kind === "error" && health.message}
            </dd>
          </div>
          <div>
            <dt>Road GeoJSON</dt>
            <dd>
              {roads.kind === "ready" && `${roads.roadCount}개 segment · EPSG:4326`}
              {roads.kind === "loading" && "불러오는 중"}
              {roads.kind === "error" && roads.message}
            </dd>
          </div>
          <div>
            <dt>Streetlight GeoJSON</dt>
            <dd>
              {roads.kind === "ready" && `${roads.streetlightCount}개 point · EPSG:4326`}
              {roads.kind === "loading" && "불러오는 중"}
              {roads.kind === "error" && roads.message}
            </dd>
          </div>
          <div>
            <dt>Building GeoJSON</dt>
            <dd>
              {roads.kind === "ready" && `${roads.buildingCount}개 building · EPSG:4326`}
              {roads.kind === "loading" && "불러오는 중"}
              {roads.kind === "error" && roads.message}
            </dd>
          </div>
          <div>
            <dt>Safety CCTV GeoJSON</dt>
            <dd>
              {roads.kind === "ready" &&
                `${roads.cctvRecordCount}건 → ${roads.cctvCount}개 위치 셀 · 저정밀 좌표`}
              {roads.kind === "loading" && "불러오는 중"}
              {roads.kind === "error" && roads.message}
            </dd>
          </div>
          <div>
            <dt>Help Point GeoJSON</dt>
            <dd>
              {roads.kind === "ready" && `${roads.helpPointCount}개 point · EPSG:4326`}
              {roads.kind === "loading" && "불러오는 중"}
              {roads.kind === "error" && roads.message}
            </dd>
          </div>
        </dl>

        <div className="legend" aria-label="가로등 접근 안전도 범례">
          <span><i className="legend-vhigh" />80–100</span>
          <span><i className="legend-high" />60–79</span>
          <span><i className="legend-mid" />40–59</span>
          <span><i className="legend-low" />20–39</span>
          <span><i className="legend-vlow" />0–19</span>
        </div>
        </details>

        <div className="facility-legend" aria-label="시설 레이어 범례">
          <span><i className="facility-streetlight" />가로등</span>
          <span><i className="facility-cctv" />CCTV 위치 셀(저정밀)</span>
          <span><i className="facility-police" />경찰</span>
          <span><i className="facility-fire" />소방</span>
          <span><i className="facility-medical" />응급의료</span>
        </div>

        <p className="disclaimer">
          CCTV는 원본의 반올림 좌표를 같은 위치 셀로 묶어 사용합니다. 이 점수는 가로등·CCTV·안전시설 거리와 밀도의 상대 순위를 합산한 분석지표이며,
          범죄 위험이나 공식 안전등급을 의미하지 않습니다. OSM 데이터 ©{" "}
          <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">
            OpenStreetMap contributors
          </a>
          .
        </p>
      </aside>
    </main>
  );
}

export default App;
