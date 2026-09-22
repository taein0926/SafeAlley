import { useCallback, useEffect, useMemo, useState } from "react";

import {
  CesiumRoadMap,
  type BuildingMapSelection,
  type BuildingSelectionMode,
  type DraftMapLocation,
  type FacilityVisibility,
  type MapInfoSelection,
  type RoadMapStatus,
} from "./components/CesiumRoadMap";
import {
  buildDirectRouteToolCall,
  resolveDirectLocation,
  selectDisplayedCandidates,
  type DirectLocationInput,
  type RouteSearchResult,
} from "./routeSearch";
import type {
  AgentExecutionResponse,
  ResolvedPlace,
  RouteCandidate,
  RouteQueryResponse,
  RouteType,
} from "./types";

type HealthResponse = {
  status: string;
  service: string;
  database: { status: string; name?: string; message?: string };
};

type HealthState =
  | { kind: "loading" }
  | { kind: "ready"; data: HealthResponse }
  | { kind: "error"; message: string };

type SearchMode = "direct" | "ai";
type RequestState = "idle" | "loading" | "error";
type MapSelectionNotice = { kind: "instruction" | "error" | "success"; text: string } | null;

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

async function responseJson<T>(response: Response): Promise<T> {
  const data = (await response.json()) as T & { detail?: string };
  if (!response.ok) throw new Error(data.detail ?? `HTTP ${response.status}`);
  return data;
}

async function resolvePlace(name: string): Promise<ResolvedPlace> {
  const response = await fetch(`/api/places/resolve?name=${encodeURIComponent(name.trim())}`, {
    headers: { Accept: "application/json" },
  });
  return responseJson<ResolvedPlace>(response);
}

async function reversePlace(latitude: number, longitude: number): Promise<ResolvedPlace> {
  const parameters = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
  });
  const response = await fetch(`/api/places/reverse?${parameters}`, {
    headers: { Accept: "application/json" },
  });
  return responseJson<ResolvedPlace>(response);
}

function emptyDirectLocation(): DirectLocationInput {
  return { displayName: "", source: "text" };
}

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [roads, setRoads] = useState<RoadMapStatus>({ kind: "loading" });
  const [mode, setMode] = useState<SearchMode>("direct");
  const [originLocation, setOriginLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [destinationLocation, setDestinationLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [buildingSelectionMode, setBuildingSelectionMode] = useState<BuildingSelectionMode>(null);
  const [mapSelectionNotice, setMapSelectionNotice] = useState<MapSelectionNotice>(null);
  const [facilityVisibility, setFacilityVisibility] = useState<FacilityVisibility>(() => ({
    streetlights: import.meta.env.VITE_SHOW_STREETLIGHTS !== "false",
    cctvs: import.meta.env.VITE_SHOW_CCTVS !== "false",
    helpPoints: import.meta.env.VITE_SHOW_HELP_POINTS !== "false",
  }));
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [safetyWeight, setSafetyWeight] = useState(0);
  const [stairsWeight, setStairsWeight] = useState(0);
  const [query, setQuery] = useState(
    "밤 10시에 주안역에서 인천사랑병원까지 CCTV가 많은 길로 안내해줘",
  );
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [searchResult, setSearchResult] = useState<RouteSearchResult | null>(null);
  const [selectedRouteType, setSelectedRouteType] = useState<RouteType | null>(null);
  const [selectionMessage, setSelectionMessage] = useState("");
  const [mapInfo, setMapInfo] = useState<MapInfoSelection | null>(null);
  const userId = useMemo(anonymousUserId, []);

  useEffect(() => {
    const controller = new AbortController();
    async function loadHealth() {
      try {
        const response = await fetch("/api/health", { signal: controller.signal });
        setHealth({ kind: "ready", data: await responseJson<HealthResponse>(response) });
      } catch (error) {
        if (error instanceof DOMException && error.name === "AbortError") return;
        setHealth({ kind: "error", message: error instanceof Error ? error.message : "연결 실패" });
      }
    }
    void loadHealth();
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (buildingSelectionMode === null) return;
    function cancelWithEscape(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      setBuildingSelectionMode(null);
      setMapSelectionNotice(null);
    }
    window.addEventListener("keydown", cancelWithEscape);
    return () => window.removeEventListener("keydown", cancelWithEscape);
  }, [buildingSelectionMode]);

  const handleRoadStatus = useCallback((status: RoadMapStatus) => setRoads(status), []);
  // Keep the empty collection stable so opening a map info panel does not
  // rerun the map's route cleanup effect before a search has been made.
  const routeCandidates = useMemo(
    () => searchResult?.result.candidates ?? [],
    [searchResult],
  );
  const selectedCandidate = routeCandidates.find(
    (candidate) => candidate.route_type === selectedRouteType,
  );
  const displayedCandidates = searchResult
    ? selectDisplayedCandidates(routeCandidates, searchResult.result.selected_route_type)
    : [];
  const systemReady = health.kind === "ready" && roads.kind === "ready";
  const draftLocations = useMemo<DraftMapLocation[]>(() => {
    const locations: DraftMapLocation[] = [];
    for (const [kind, location] of [
      ["origin", originLocation],
      ["destination", destinationLocation],
    ] as const) {
      if (
        location.source === "map" &&
        typeof location.latitude === "number" &&
        typeof location.longitude === "number"
      ) {
        locations.push({
          kind,
          latitude: location.latitude,
          longitude: location.longitude,
        });
      }
    }
    return locations;
  }, [destinationLocation, originLocation]);

  const handleBuildingSelect = useCallback(async (selection: BuildingMapSelection) => {
    const target = buildingSelectionMode;
    if (target === null) return;
    setMapSelectionNotice({ kind: "instruction", text: "건물 위치를 확인하고 있습니다..." });
    try {
      let displayName = selection.displayName ?? selection.address;
      if (!displayName) {
        const reversed = await reversePlace(selection.latitude, selection.longitude);
        displayName = reversed.address ?? reversed.name;
      }
      const location: DirectLocationInput = {
        displayName,
        latitude: selection.latitude,
        longitude: selection.longitude,
        source: "map",
      };
      if (target === "origin") setOriginLocation(location);
      else setDestinationLocation(location);
      setBuildingSelectionMode(null);
      setMapSelectionNotice({
        kind: "success",
        text: `${target === "origin" ? "출발지" : "도착지"} 건물을 선택했습니다.`,
      });
    } catch (error) {
      setMapSelectionNotice({
        kind: "error",
        text: error instanceof Error ? error.message : "건물 주소를 확인하지 못했습니다.",
      });
    }
  }, [buildingSelectionMode]);

  const handleInvalidBuildingSelect = useCallback(() => {
    setMapSelectionNotice({ kind: "error", text: "건물을 선택해주세요" });
  }, []);

  function toggleBuildingSelection(target: Exclude<BuildingSelectionMode, null>) {
    if (buildingSelectionMode === target) {
      setBuildingSelectionMode(null);
      setMapSelectionNotice(null);
      return;
    }
    setBuildingSelectionMode(target);
    setMapSelectionNotice({ kind: "instruction", text: "지도에서 건물을 선택하세요" });
  }

  function editLocation(
    target: "origin" | "destination",
    displayName: string,
  ) {
    const textLocation: DirectLocationInput = { displayName, source: "text" };
    if (target === "origin") setOriginLocation(textLocation);
    else setDestinationLocation(textLocation);
    if (buildingSelectionMode === target) setBuildingSelectionMode(null);
    setMapSelectionNotice(null);
  }

  function beginSearch() {
    setRequestState("loading");
    setErrorMessage("");
    setSelectionMessage("");
    setSearchResult(null);
    setSelectedRouteType(null);
    setBuildingSelectionMode(null);
    setMapSelectionNotice(null);
    setMapInfo(null);
  }

  function finishSearch(result: RouteSearchResult) {
    setSearchResult(result);
    setSelectedRouteType(
      result.result.selected_route_type ?? result.result.candidates[0]?.route_type ?? null,
    );
    setRequestState("idle");
  }

  function failSearch(error: unknown) {
    setRequestState("error");
    setErrorMessage(error instanceof Error ? error.message : "경로 검색에 실패했습니다.");
  }

  async function searchDirect(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (requestState === "loading") return;
    beginSearch();
    try {
      const [origin, destination] = await Promise.all([
        resolveDirectLocation(originLocation, resolvePlace),
        resolveDirectLocation(destinationLocation, resolvePlace),
      ]);
      const response = await fetch("/api/agent/execute", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(buildDirectRouteToolCall(
          origin,
          destination,
          { safety: safetyWeight, stairs: stairsWeight },
          userId,
        )),
      });
      finishSearch({
        mode: "direct",
        origin,
        destination,
        model: null,
        result: await responseJson<AgentExecutionResponse>(response),
      });
    } catch (error) {
      failSearch(error);
    }
  }

  async function searchWithAi(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (requestState === "loading") return;
    beginSearch();
    try {
      const response = await fetch("/api/agent/query", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ query: query.trim(), source: "osm", user_id: userId }),
      });
      const data = await responseJson<RouteQueryResponse>(response);
      finishSearch({
        mode: "ai",
        origin: data.resolved_origin,
        destination: data.resolved_destination,
        model: data.model,
        result: data.result,
      });
    } catch (error) {
      failSearch(error);
    }
  }

  async function selectRoute(routeType: RouteType) {
    setSelectedRouteType(routeType);
    setSelectionMessage("");
    setMapInfo(null);
    const recommendationId = searchResult?.result.recommendation_id;
    if (!recommendationId) return;
    try {
      const response = await fetch("/api/agent/route-selections", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          recommendation_id: recommendationId,
          user_id: userId,
          selected_route_type: routeType,
        }),
      });
      await responseJson(response);
      setSelectionMessage("선택한 경로를 저장했습니다.");
    } catch (error) {
      setSelectionMessage(
        error instanceof Error ? `선택 저장 실패: ${error.message}` : "선택 저장 실패",
      );
    }
  }

  return (
    <main className={`app-shell ${mapInfo ? "app-shell--map-info" : ""}`}>
      <CesiumRoadMap
        onStatusChange={handleRoadStatus}
        routeCandidates={routeCandidates}
        selectedRouteType={selectedRouteType}
        facilityVisibility={facilityVisibility}
        buildingSelectionMode={buildingSelectionMode}
        onBuildingSelect={(selection) => void handleBuildingSelect(selection)}
        onInvalidBuildingSelect={handleInvalidBuildingSelect}
        draftLocations={draftLocations}
        onMapInfoChange={setMapInfo}
      />

      <nav className="facility-controls" aria-label="시설 표시">
        <button
          type="button"
          aria-label="가로등 표시"
          aria-pressed={facilityVisibility.streetlights}
          title="가로등"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            streetlights: !current.streetlights,
          }))}
        ><span aria-hidden="true">💡</span></button>
        <button
          type="button"
          aria-label="CCTV 표시"
          aria-pressed={facilityVisibility.cctvs}
          title="CCTV"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            cctvs: !current.cctvs,
          }))}
        ><span aria-hidden="true">📹</span></button>
        <button
          type="button"
          aria-label="안전지원시설 표시"
          aria-pressed={facilityVisibility.helpPoints}
          title="안전지원시설"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            helpPoints: !current.helpPoints,
          }))}
        ><span aria-hidden="true">🏥</span></button>
      </nav>

      <header className="brand-chip" aria-label="SafeAlley">
        <strong>SafeAlley</strong>
        <span className={systemReady ? "system-dot system-dot--ready" : "system-dot"} />
      </header>

      <section className="search-panel" aria-label="경로 검색">
        <div className="segmented-control" role="tablist" aria-label="검색 방식">
          <button type="button" role="tab" aria-selected={mode === "direct"} onClick={() => setMode("direct")}>직접 검색</button>
          <button type="button" role="tab" aria-selected={mode === "ai"} onClick={() => { setMode("ai"); setBuildingSelectionMode(null); setMapSelectionNotice(null); }}>AI 검색</button>
        </div>

        {mode === "direct" ? (
          <form className="route-form" onSubmit={searchDirect}>
            <div className="place-inputs">
              <label><span>출발지</span><span className="location-input"><input value={originLocation.displayName} placeholder="주안역" onChange={(event) => editLocation("origin", event.target.value)} required /><button type="button" aria-label="출발지 지도 선택" aria-pressed={buildingSelectionMode === "origin"} title="지도에서 출발지 건물 선택" onClick={() => toggleBuildingSelection("origin")}>📍</button></span></label>
              <i aria-hidden="true" />
              <label><span>도착지</span><span className="location-input"><input value={destinationLocation.displayName} placeholder="인하대학교" onChange={(event) => editLocation("destination", event.target.value)} required /><button type="button" aria-label="도착지 지도 선택" aria-pressed={buildingSelectionMode === "destination"} title="지도에서 도착지 건물 선택" onClick={() => toggleBuildingSelection("destination")}>📍</button></span></label>
            </div>
            {mapSelectionNotice && <p className={`map-selection-notice map-selection-notice--${mapSelectionNotice.kind}`} role={mapSelectionNotice.kind === "error" ? "alert" : "status"}>{mapSelectionNotice.text}</p>}
            <button className="criteria-toggle" type="button" aria-expanded={criteriaOpen} onClick={() => setCriteriaOpen((open) => !open)}>
              경로 기준 <span>{criteriaOpen ? "▲" : "▼"}</span>
            </button>
            {criteriaOpen && (
              <div className="route-criteria">
                <label><span>안전도 <output>{safetyWeight}</output></span><input aria-label="안전도" type="range" min="0" max="100" value={safetyWeight} onChange={(event) => setSafetyWeight(Number(event.target.value))} /></label>
                <label><span>계단 회피 <output>{stairsWeight}</output></span><input aria-label="계단 회피" type="range" min="0" max="100" value={stairsWeight} onChange={(event) => setStairsWeight(Number(event.target.value))} /></label>
                <label className="disabled-criterion"><span>경사도 회피 <output>미지원</output></span><input aria-label="경사도 회피" type="range" min="0" max="100" value="0" disabled /><small>경사 데이터가 충분하지 않아 경로 비용에 적용하지 않습니다.</small></label>
              </div>
            )}
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        ) : (
          <form className="route-form" onSubmit={searchWithAi}>
            <label className="ai-query"><span>AI 경로 요청</span><textarea value={query} onChange={(event) => setQuery(event.target.value)} rows={3} required /></label>
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        )}
        {requestState === "error" && <p className="route-error" role="alert">{errorMessage}</p>}
      </section>

      {displayedCandidates.length > 0 && (
        <aside className="result-panel" aria-label="경로 검색 결과">
          <div className="result-heading">
            <div><span>경로 검색 결과</span><strong>{searchResult?.origin?.name ?? originLocation.displayName} → {searchResult?.destination?.name ?? destinationLocation.displayName}</strong></div>
            {searchResult?.model && <small>{searchResult.model}</small>}
          </div>
          <div className="route-cards">
            {displayedCandidates.map(({ candidate, label }) => {
              const active = candidate.route_type === selectedRouteType;
              const safety = metric(candidate, "safety_score") ?? candidate.route.properties.average_safety_score;
              return (
                <button key={candidate.route_type} type="button" className={`route-card ${active ? "route-card--active" : ""}`} onClick={() => void selectRoute(candidate.route_type)} aria-pressed={active}>
                  <span className="route-card-title"><strong>{label}</strong>{candidate.preference_score != null && <em>{candidate.preference_score.toFixed(0)}점</em>}</span>
                  <dl>
                    <div><dt>거리</dt><dd>{formatDistance(candidate.route.properties.total_distance_m)}</dd></div>
                    <div><dt>총 비용</dt><dd>{candidate.route.properties.total_cost.toFixed(1)}</dd></div>
                    <div><dt>안전도</dt><dd>{safety == null ? "데이터 없음" : safety.toFixed(1)}</dd></div>
                    <div><dt>계단 구간</dt><dd>{candidate.route.properties.stairs_segment_count}개</dd></div>
                  </dl>
                </button>
              );
            })}
          </div>
          {selectedCandidate?.route.properties.unverified_major_road_count ? (
            <p className="route-review-warning">현장 확인이 필요한 대로 구간 {selectedCandidate.route.properties.unverified_major_road_count}개가 포함됩니다.</p>
          ) : null}
          {selectionMessage && <p className="selection-message" aria-live="polite">{selectionMessage}</p>}
        </aside>
      )}

      {mapInfo && (
        <aside className="map-info-panel" aria-label="지도 객체 정보">
          <header>
            <div>
              <span>{mapInfo.kind === "route_segment" ? "경로 구간" : "지도 객체"}</span>
              <strong>{mapInfo.title}</strong>
            </div>
            <button type="button" aria-label="지도 객체 정보 닫기" onClick={() => setMapInfo(null)}>×</button>
          </header>
          <dl>
            {mapInfo.rows.map((row) => (
              <div key={`${row.label}-${row.value}`}><dt>{row.label}</dt><dd>{row.value}</dd></div>
            ))}
          </dl>
        </aside>
      )}

      <details className="map-status">
        <summary>데이터 상태</summary>
        <p>Backend: {health.kind === "ready" ? "연결됨" : health.kind === "error" ? health.message : "확인 중"}</p>
        <p>지도 레이어: {roads.kind === "ready" ? `도로 ${roads.roadCount.toLocaleString()}개 · EPSG:4326` : roads.kind === "error" ? roads.message : "불러오는 중"}</p>
        <p>전체 안전도 도로는 검색 전 자동 표시하지 않습니다.</p>
      </details>
    </main>
  );
}

export default App;
