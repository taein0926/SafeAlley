import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { isNightDepartureTime } from "./nightMode";
import { PreferenceSlider } from "./components/PreferenceSlider";
import { RecommendationIcons } from "./components/RecommendationIcons";
import { SpeechInput } from "./components/SpeechInput";
import { useWeather, WeatherHud } from "./components/WeatherHud";

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
  currentLocalTime,
  criterionOutcomeLabel,
  estimatedWalkingMinutes,
  isValidDepartureTime,
  resolveBuildingLocation,
  resolveDirectLocation,
  selectDisplayedCandidates,
  type DirectLocationInput,
  type RouteSearchResult,
} from "./routeSearch";
import type {
  AgentExecutionResponse,
  ResolvedPlace,
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
  const [mode, setMode] = useState<SearchMode>("ai");
  const [originLocation, setOriginLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [destinationLocation, setDestinationLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [buildingSelectionMode, setBuildingSelectionMode] = useState<BuildingSelectionMode>(null);
  const [mapSelectionNotice, setMapSelectionNotice] = useState<MapSelectionNotice>(null);
  const buildingRequestSerial = useRef(0);
  const [buildingSelectionPending, setBuildingSelectionPending] = useState(false);
  const [facilityVisibility, setFacilityVisibility] = useState<FacilityVisibility>(() => ({
    streetlights: import.meta.env.VITE_SHOW_STREETLIGHTS !== "false",
    cctvs: import.meta.env.VITE_SHOW_CCTVS !== "false",
    helpPoints: import.meta.env.VITE_SHOW_HELP_POINTS !== "false",
  }));
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(true);
  const [facilityPanelOpen, setFacilityPanelOpen] = useState(true);
  const [weatherHudHeight, setWeatherHudHeight] = useState(142);
  const [safetyWeight, setSafetyWeight] = useState(50);
  const [stairsWeight, setStairsWeight] = useState(50);
  const [intersectionWeight, setIntersectionWeight] = useState(50);
  const [departureTime, setDepartureTime] = useState(() => currentLocalTime());
  const [appliedDepartureTime, setAppliedDepartureTime] = useState<string | null>(departureTime);
  const [query, setQuery] = useState(
    "밤 10시에 인천사랑병원에서 석암초등학교까지 밝은 길로 안내해줘. 다리 다쳐서 계단은 싫어.",
  );
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [searchResult, setSearchResult] = useState<RouteSearchResult | null>(null);
  const [resultPanelOpen, setResultPanelOpen] = useState(true);
  const [selectedRouteType, setSelectedRouteType] = useState<RouteType | null>(null);
  const [selectionMessage, setSelectionMessage] = useState("");
  const selectionRequestSerial = useRef(0);
  const [mapInfo, setMapInfo] = useState<MapInfoSelection | null>(null);
  const userId = useMemo(anonymousUserId, []);
  const weather = useWeather(appliedDepartureTime);
  const nightMode = isNightDepartureTime(weather.time, weather.solar);

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
      ++buildingRequestSerial.current;
      setBuildingSelectionPending(false);
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
  const displayedCandidates = useMemo(() => searchResult
    ? selectDisplayedCandidates(routeCandidates, searchResult.result.selected_route_type)
    : [], [routeCandidates, searchResult]);
  const mapCandidates = useMemo(() => displayedCandidates.map(({ candidate }) => candidate), [displayedCandidates]);
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

  const handleBuildingSelect = useCallback(async (
    selection: BuildingMapSelection,
    target: BuildingSelectionMode = buildingSelectionMode,
  ) => {
    if (target === null || requestState === "loading") return;
    const serial = ++buildingRequestSerial.current;
    setMode("direct");
    setSearchPanelOpen(true);
    setBuildingSelectionPending(true);
    setMapSelectionNotice({ kind: "instruction", text: "건물 위치를 확인하고 있습니다..." });
    try {
      const location = await resolveBuildingLocation(selection, reversePlace);
      if (serial !== buildingRequestSerial.current) return;
      if (target === "origin") setOriginLocation(location);
      else setDestinationLocation(location);
      setBuildingSelectionMode(null);
      setMapInfo(null);
      setMapSelectionNotice({
        kind: "success",
        text: `${target === "origin" ? "출발지" : "도착지"} 건물을 선택했습니다.`,
      });
    } catch (error) {
      if (serial !== buildingRequestSerial.current) return;
      setMapSelectionNotice({
        kind: "error",
        text: error instanceof Error ? error.message : "건물 주소를 확인하지 못했습니다.",
      });
    } finally {
      if (serial === buildingRequestSerial.current) setBuildingSelectionPending(false);
    }
  }, [buildingSelectionMode, requestState]);

  const handleInvalidBuildingSelect = useCallback((message?: string) => {
    setMapSelectionNotice({ kind: "error", text: message ?? "건물을 선택해주세요" });
  }, []);

  function selectMapInfoLocation(target: Exclude<BuildingSelectionMode, null>) {
    if (requestState === "loading" || buildingSelectionPending) return;
    if (mapInfo?.kind === "building" && mapInfo.buildingSelection) {
      void handleBuildingSelect(mapInfo.buildingSelection, target);
      return;
    }
    if (mapInfo?.kind !== "help_point" || !mapInfo.routeLocation) return;
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
    setMode("direct");
    setSearchPanelOpen(true);
    if (target === "origin") setOriginLocation(mapInfo.routeLocation);
    else setDestinationLocation(mapInfo.routeLocation);
    setBuildingSelectionMode(null);
    setMapInfo(null);
    setMapSelectionNotice({
      kind: "success",
      text: `${target === "origin" ? "출발지" : "도착지"} 시설을 선택했습니다.`,
    });
  }

  const mapInfoLocationAvailable = mapInfo?.kind === "building"
    ? Boolean(mapInfo.buildingSelection)
    : mapInfo?.kind === "help_point" && Boolean(mapInfo.routeLocation);

  function toggleBuildingSelection(target: Exclude<BuildingSelectionMode, null>) {
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
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
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
    const textLocation: DirectLocationInput = { displayName, source: "text" };
    if (target === "origin") setOriginLocation(textLocation);
    else setDestinationLocation(textLocation);
    if (buildingSelectionMode === target) setBuildingSelectionMode(null);
    setMapSelectionNotice(null);
  }

  function beginSearch() {
    ++selectionRequestSerial.current;
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
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
    setResultPanelOpen(true);
    setAppliedDepartureTime(result.departureTime ?? currentLocalTime());
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
    if (!isValidDepartureTime(departureTime)) {
      failSearch(new Error("출발 시간을 올바르게 설정해주세요."));
      return;
    }
    setAppliedDepartureTime(departureTime);
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
          { safety: safetyWeight, stairs: stairsWeight, intersection: intersectionWeight },
          userId,
          departureTime,
        )),
      });
      finishSearch({
        mode: "direct",
        origin,
        destination,
        model: null,
        departureTime,
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
        departureTime: data.interpretation.departure_time,
        result: data.result,
      });
    } catch (error) {
      failSearch(error);
    }
  }

  const selectRoute = useCallback(async (routeType: RouteType) => {
    setResultPanelOpen(true);
    setMapInfo(null);
    if (routeType === selectedRouteType) return;
    const serial = ++selectionRequestSerial.current;
    setSelectedRouteType(routeType);
    setSelectionMessage("");
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
    } catch (error) {
      if (serial !== selectionRequestSerial.current) return;
      setSelectionMessage(
        error instanceof Error ? `선택 저장 실패: ${error.message}` : "선택 저장 실패",
      );
    }
  }, [searchResult, selectedRouteType, userId]);

  const handleMapInfoChange = useCallback((selection: MapInfoSelection | null) => {
    if (selection?.kind === "route_segment" && selection.routeType) {
      void selectRoute(selection.routeType);
      return;
    }
    setMapInfo(selection);
  }, [selectRoute]);

  return (
    <main className={`app-shell ${mapInfo ? "app-shell--map-info" : ""}`} data-theme={nightMode ? "night" : "day"} style={{ "--weather-clearance": `${12 + weatherHudHeight + 16}px` } as CSSProperties}>
      <CesiumRoadMap
        onStatusChange={handleRoadStatus}
        routeCandidates={mapCandidates}
        selectedRouteType={selectedRouteType}
        facilityVisibility={facilityVisibility}
        buildingSelectionMode={buildingSelectionMode}
        onBuildingSelect={(selection) => void handleBuildingSelect(selection)}
        onInvalidBuildingSelect={handleInvalidBuildingSelect}
        draftLocations={draftLocations}
        onMapInfoChange={handleMapInfoChange}
        nightMode={nightMode}
      />
      <WeatherHud {...weather} onHeightChange={setWeatherHudHeight} />

      <div className={`facility-panel-shell ${facilityPanelOpen ? "" : "facility-panel-shell--collapsed"}`}>
      <nav id="facility-controls" className="facility-controls" aria-label="시설 표시" inert={!facilityPanelOpen} aria-hidden={!facilityPanelOpen}>
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
      <button className="facility-panel-handle" type="button" aria-label={facilityPanelOpen ? "시설 토글 접기" : "시설 토글 열기"} aria-controls="facility-controls" aria-expanded={facilityPanelOpen} onClick={() => setFacilityPanelOpen((open) => !open)}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <polyline points={facilityPanelOpen ? "9 5 15 12 9 19" : "15 5 9 12 15 19"} />
        </svg>
      </button>
      </div>

      <header className="brand-chip" aria-label="SafeAlley">
        <strong>SafeAlley</strong>
        <span className={systemReady ? "system-dot system-dot--ready" : "system-dot"} />
      </header>

      <div className={`search-panel-shell ${searchPanelOpen ? "" : "search-panel-shell--collapsed"}`}>
      <section id="route-search-panel" className="search-panel" aria-label="경로 검색" inert={!searchPanelOpen} aria-hidden={!searchPanelOpen}>
        <div className="segmented-control" role="tablist" aria-label="검색 방식">
          <button type="button" role="tab" aria-selected={mode === "ai"} onClick={() => { ++buildingRequestSerial.current; setBuildingSelectionPending(false); setMode("ai"); setBuildingSelectionMode(null); setMapSelectionNotice(null); }}>AI 검색</button>
          <button type="button" role="tab" aria-selected={mode === "direct"} onClick={() => setMode("direct")}>직접 검색</button>
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
                <label>
                  <span>출발 시간</span>
                  <span className="departure-time-control">
                    <input aria-label="출발 시간" type="time" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} required />
                    <button type="button" onClick={() => setDepartureTime(currentLocalTime())}>현재 시간</button>
                  </span>
                  <small>경로 검색을 누르면 선택한 시간의 지도 테마와 야간 추천 기준을 적용합니다.</small>
                </label>
                <PreferenceSlider label="안전 관련 시설" value={safetyWeight} onChange={setSafetyWeight} description="낮음은 거리 우선, 높음은 CCTV·도움시설 위치 지표를 더 반영합니다. 가로등은 밤에만 포함하며 실제 안전을 보증하지 않습니다." />
                <PreferenceSlider label="계단 회피" value={stairsWeight} onChange={setStairsWeight} description="높을수록 계단을 더 피하도록 반영합니다. 계단 없는 경로를 보장하지는 않습니다." />
                <PreferenceSlider label="교차로 회피" value={intersectionWeight} onChange={setIntersectionWeight} description="높을수록 교차로 주변 지상 구간을 피하고 연결된 육교를 우선 고려합니다. 추가 우회는 같은 안전·계단 설정의 기본 경로 대비 30%·300m 중 작은 값 이내이며, 계단 회피도 함께 적용합니다." />
              </div>
            )}
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        ) : (
          <form className="route-form" onSubmit={searchWithAi}>
            <div className="ai-query">
              <div className="ai-query-heading">
                <label htmlFor="ai-route-query">AI 경로 요청</label>
                <SpeechInput value={query} onText={setQuery} disabled={requestState === "loading" || !searchPanelOpen} />
              </div>
              <textarea id="ai-route-query" value={query} onChange={(event) => setQuery(event.target.value)} rows={3} required />
            </div>
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        )}
        {requestState === "error" && <p className="route-error" role="alert">{errorMessage}</p>}
      </section>
      <button className="search-panel-handle" type="button" aria-label={searchPanelOpen ? "검색창 접기" : "검색창 열기"} aria-controls="route-search-panel" aria-expanded={searchPanelOpen} onClick={() => setSearchPanelOpen((open) => !open)}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
          <polyline points={searchPanelOpen ? "15 5 9 12 15 19" : "9 5 15 12 9 19"} />
        </svg>
      </button>
      </div>

      {displayedCandidates.length > 0 && resultPanelOpen && (
        <aside className="result-panel" aria-label="경로 검색 결과">
          <div className="result-heading">
            <div><span>경로 검색 결과</span><strong>{searchResult?.origin?.name ?? originLocation.displayName} → {searchResult?.destination?.name ?? destinationLocation.displayName}</strong></div>
            <button className="panel-close" type="button" aria-label="경로 검색 결과 닫기" title="닫기 · 지도 경로를 누르면 다시 열립니다" onClick={() => { setResultPanelOpen(false); setMapInfo(null); }}>×</button>
          </div>
          {searchResult?.result.recommendation_reason && (
            <section className="route-explanation" role="status" aria-live="polite">
              <strong>{searchResult.result.recommendation_status === "ready" ? "왜 이 길을 추천했나요?" : "왜 추천하지 않았나요?"}</strong>
              <RecommendationIcons factors={searchResult.result.recommendation_factors ?? []} />
              <p>{searchResult.result.recommendation_reason}</p>
              {searchResult.result.recommendation_criteria.length > 0 && (
                <ul className="criterion-list" aria-label="요청 조건별 비교 결과">
                  {searchResult.result.recommendation_criteria.map((criterion) => (
                    <li key={criterion.factor} className={`criterion criterion--${criterion.outcome}`}>
                      <header>
                        <strong>{criterion.label}</strong>
                        <span>{criterionOutcomeLabel(criterion.outcome)}</span>
                      </header>
                      <p>{criterion.summary}</p>
                    </li>
                  ))}
                </ul>
              )}
            </section>
          )}
          <div className="route-cards">
            {displayedCandidates.map(({ candidate, label }) => {
              const active = candidate.route_type === selectedRouteType;
              return (
                <button key={candidate.route_type} type="button" className={`route-card ${active ? "route-card--active" : ""}`} onClick={() => void selectRoute(candidate.route_type)} aria-pressed={active}>
                  <span className="route-card-title"><strong><i className={`route-swatch ${active ? "route-swatch--active" : ""}`} aria-hidden="true" />{label}</strong>{active && <small>선택됨</small>}</span>
                  <dl>
                    <div><dt>거리</dt><dd>{formatDistance(candidate.route.properties.total_distance_m)}</dd></div>
                    <div><dt>예상 소요 시간</dt><dd>{estimatedWalkingMinutes(candidate.route.properties.total_distance_m) === null ? "계산 불가" : `약 ${estimatedWalkingMinutes(candidate.route.properties.total_distance_m)}분`}</dd></div>
                    <div><dt>계단 구간</dt><dd>{candidate.route.properties.stairs_segment_count}개</dd></div>
                    <div><dt>교차로 주변</dt><dd>{candidate.route.properties.intersection_data_available ? formatDistance(candidate.route.properties.intersection_distance_m ?? 0) : "데이터 미연결"}</dd></div>
                    <div><dt>연결된 육교</dt><dd>{candidate.route.properties.intersection_data_available ? `${candidate.route.properties.pedestrian_bridge_count ?? 0}개` : "확인 불가"}</dd></div>
                  </dl>
                </button>
              );
            })}
          </div>
          {selectedCandidate?.route.properties.streetlight_included === false && <p className="selection-message">낮 시간 안전도: CCTV·도움시설만 반영 · 가로등 제외</p>}
          {selectedCandidate?.route.properties.intersection_detour_limited && <p className="selection-message">먼 우회를 막기 위해 교차로 회피를 일부 완화했습니다.</p>}
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
            <button className="panel-close" type="button" aria-label="지도 객체 정보 닫기" onClick={() => setMapInfo(null)}>×</button>
          </header>
          {(mapInfo.kind === "building" || mapInfo.kind === "help_point") && (
            <div className="building-location-actions" role="group" aria-label={mapInfo.kind === "building" ? "건물 경로 선택" : "안전지원시설 경로 선택"}>
              <button type="button" disabled={!mapInfoLocationAvailable || buildingSelectionPending || requestState === "loading"} onClick={() => selectMapInfoLocation("origin")}>출발</button>
              <button type="button" disabled={!mapInfoLocationAvailable || buildingSelectionPending || requestState === "loading"} onClick={() => selectMapInfoLocation("destination")}>도착</button>
            </div>
          )}
          <dl>
            {mapInfo.rows.map((row) => (
              <div key={`${row.label}-${row.value}`}><dt>{row.label}</dt><dd>{row.value}</dd></div>
            ))}
          </dl>
        </aside>
      )}

    </main>
  );
}

export default App;
