import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isNightDepartureTime } from "./nightMode";
import { defaultStreetlightVisibility } from "./mapLighting";
import { PreferenceSlider } from "./components/PreferenceSlider";
import { RecommendationIcons } from "./components/RecommendationIcons";
import { RouteProgressPanel } from "./components/RouteProgressPanel";
import { SpeechInput } from "./components/SpeechInput";
import { useWeather, WeatherHud } from "./components/WeatherHud";
import { facilityToggleImage } from "./facilityToggleIcons";
import { routeInputMarkerImage } from "./routeMarkers";
import { createRouteSelectionSaver } from "./routeSelection";
import { mergeWorkUpdate, queryRouteWithProgress } from "./routeProgress";
import type { RouteWorkUpdate } from "./routeProgress";
import { useLiveIntentPreview } from "./useLiveIntentPreview";

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
  estimatedWalkingMinutes,
  formatCrosswalkCount,
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
  const [saveRouteSelection] = useState(() => createRouteSelectionSaver());
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [roads, setRoads] = useState<RoadMapStatus>({ kind: "loading" });
  const [mode, setMode] = useState<SearchMode>("ai");
  const [originLocation, setOriginLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [destinationLocation, setDestinationLocation] = useState<DirectLocationInput>(emptyDirectLocation);
  const [buildingSelectionMode, setBuildingSelectionMode] = useState<BuildingSelectionMode>(null);
  const [mapSelectionNotice, setMapSelectionNotice] = useState<MapSelectionNotice>(null);
  const buildingRequestSerial = useRef(0);
  const [buildingSelectionPending, setBuildingSelectionPending] = useState(false);
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(true);
  const [safetyWeight, setSafetyWeight] = useState(50);
  const [stairsWeight, setStairsWeight] = useState(50);
  const [crossingWeight, setCrossingWeight] = useState(50);
  const [departureTime, setDepartureTime] = useState(() => currentLocalTime());
  const [appliedDepartureTime, setAppliedDepartureTime] = useState<string | null>(departureTime);
  const [query, setQuery] = useState(
    "밤 10시에 정부인천지방합동청사에서 두리하나어린이집까지 계단은 피하고 가로등이 많은 길로 안내해줘.",
  );
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [activeSearchMode, setActiveSearchMode] = useState<SearchMode | null>(null);
  const [progressStage, setProgressStage] = useState<"interpreting" | "resolving" | "routing" | "done" | "failed">("interpreting");
  const [progressInterpretation, setProgressInterpretation] = useState<RouteQueryResponse["interpretation"] | null>(null);
  const [progressWork, setProgressWork] = useState<RouteWorkUpdate[]>([]);
  const livePreview = useLiveIntentPreview();
  const processScrollRef = useRef<HTMLDivElement>(null);
  const [progressPlaces, setProgressPlaces] = useState<{ origin: string | null; destination: string | null }>({ origin: null, destination: null });
  const [errorMessage, setErrorMessage] = useState("");
  const [searchResult, setSearchResult] = useState<RouteSearchResult | null>(null);
  const [resultPanelOpen, setResultPanelOpen] = useState(true);
  const [selectedRouteType, setSelectedRouteType] = useState<RouteType | null>(null);
  const [routeDetailOpen, setRouteDetailOpen] = useState(false);
  const [mapInfo, setMapInfo] = useState<MapInfoSelection | null>(null);
  const userId = useMemo(anonymousUserId, []);
  const weather = useWeather(appliedDepartureTime);
  const nightMode = isNightDepartureTime(weather.time, weather.solar);
  const defaultStreetlights = defaultStreetlightVisibility(nightMode, import.meta.env.VITE_SHOW_STREETLIGHTS !== "false");
  const [facilityVisibility, setFacilityVisibility] = useState<FacilityVisibility>(() => ({
    streetlights: defaultStreetlights,
    cctvs: import.meta.env.VITE_SHOW_CCTVS !== "false",
    helpPoints: import.meta.env.VITE_SHOW_HELP_POINTS !== "false",
    stairsAndBridges: true,
  }));

  // Reset only on an applied day/night transition, not while editing the time
  // or refreshing weather within the same theme. Manual toggles remain usable.
  useEffect(() => {
    setFacilityVisibility(current => current.streetlights === defaultStreetlights
      ? current : { ...current, streetlights: defaultStreetlights });
  }, [nightMode, defaultStreetlights]);

  useEffect(() => {
    if (requestState !== "idle" || !searchResult) return;
    // Wait until the completed messages are laid out; scroll only the result pane.
    const frame = window.requestAnimationFrame(() => {
      const pane = processScrollRef.current;
      if (pane) pane.scrollTop = pane.scrollHeight;
    });
    return () => window.cancelAnimationFrame(frame);
  }, [requestState, searchResult]);

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
    // Keep pins at the coordinates used for THIS search, including AI/text results.
    // Editing the next query must not move pins belonging to the displayed route.
    if (searchResult) {
      return (["origin", "destination"] as const).flatMap(kind => {
        const place = searchResult[kind];
        return place ? [{ kind, latitude: place.latitude, longitude: place.longitude }] : [];
      });
    }
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
  }, [destinationLocation, originLocation, searchResult]);

  const handleBuildingSelect = useCallback(async (
    selection: BuildingMapSelection,
    target: BuildingSelectionMode = buildingSelectionMode,
  ) => {
    if (target === null || requestState === "loading") return;
    const serial = ++buildingRequestSerial.current;
    setMode("direct");
    setSearchPanelOpen(true);
    setBuildingSelectionPending(true);
    setResultPanelOpen(false);
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
  }

  const mapInfoLocationAvailable = mapInfo?.kind === "building" && Boolean(mapInfo.buildingSelection);

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

  function beginSearch(searchMode: SearchMode) {
    if (processScrollRef.current) processScrollRef.current.scrollTop = 0;
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
    setRequestState("loading");
    setActiveSearchMode(searchMode);
    setProgressStage("interpreting");
    setProgressInterpretation(null);
    setProgressWork([]);
    setProgressPlaces({ origin: null, destination: null });
    setErrorMessage("");
    setSearchResult(null);
    setRouteDetailOpen(false);
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
      result.result.recommendation_status === "ready"
        ? result.result.selected_route_type
        : null,
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
    beginSearch("direct");
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
          { safety: safetyWeight, stairs: stairsWeight, crossing: crossingWeight },
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
    await runAiQuery(query.trim());
  }

  async function runAiQuery(submittedQuery: string) {
    if (requestState === "loading") return;
    livePreview.pause();
    beginSearch("ai");
    try {
      const data = await queryRouteWithProgress(submittedQuery, userId, (event) => {
        if (event.type === "stage") setProgressStage(event.stage);
        if (event.type === "interpreted") setProgressInterpretation(event.data);
        if (event.type === "route_progress") setProgressWork((updates) => mergeWorkUpdate(updates, event.data));
        if (event.type === "resolved") setProgressPlaces({
          origin: event.origin?.name ?? null,
          destination: event.destination?.name ?? null,
        });
      });
      setProgressStage("done");
      livePreview.clear();
      finishSearch({
        mode: "ai",
        origin: data.resolved_origin,
        destination: data.resolved_destination,
        model: data.model,
        departureTime: data.interpretation.departure_time,
        result: data.result,
      });
    } catch (error) {
      setProgressStage("failed");
      livePreview.clear();
      failSearch(error);
    }
  }

  const selectRoute = useCallback(async (routeType: RouteType) => {
    setSearchPanelOpen(true);
    setResultPanelOpen(true);
    setMapInfo(null);
    if (routeType === selectedRouteType) return;
    setSelectedRouteType(routeType);
    setRouteDetailOpen(false);
    const recommendationId = searchResult?.result.recommendation_id;
    if (!recommendationId) return;
    try {
      await saveRouteSelection({
        recommendation_id: recommendationId,
        user_id: userId,
        selected_route_type: routeType,
      });
    } catch (error) {
      // Saving feedback must not interrupt the route already shown on the map.
      console.warn("경로 선택 기록 저장 재시도 실패:", error);
    }
  }, [searchResult, selectedRouteType, userId, saveRouteSelection]);

  const handleMapInfoChange = useCallback((selection: MapInfoSelection | null) => {
    if (selection?.kind === "route_segment" && selection.routeType) {
      void selectRoute(selection.routeType);
      return;
    }
    setMapInfo(selection);
    if (selection) setSearchPanelOpen(true);
  }, [selectRoute]);

  return (
    <main className={`app-shell ${mapInfo ? "app-shell--map-info" : ""} ${searchPanelOpen ? "" : "app-shell--sidebar-closed"}`} data-theme={nightMode ? "night" : "day"}>
      <div className="map-stage">
      <CesiumRoadMap
        onStatusChange={handleRoadStatus}
        routeCandidates={mapCandidates}
        selectedRouteType={selectedRouteType}
        routeDetailOpen={routeDetailOpen}
        facilityVisibility={facilityVisibility}
        buildingSelectionMode={buildingSelectionMode}
        onBuildingSelect={(selection) => void handleBuildingSelect(selection)}
        onInvalidBuildingSelect={handleInvalidBuildingSelect}
        draftLocations={draftLocations}
        onMapInfoChange={handleMapInfoChange}
        nightMode={nightMode}
        onResetView={() => setRouteDetailOpen(false)}
      />
      {(displayedCandidates.length > 0 || (mode === "ai" && livePreview.active)) && !mapInfo && (
        <aside id="route-results" className="result-panel result-panel--floating" aria-label="경로 검색 결과">
          <header className="floating-results-header">
            <strong>경로 후보</strong>
            <button type="button" aria-label={resultPanelOpen ? "경로 후보 숨기기" : "경로 후보 보이기"} aria-expanded={resultPanelOpen} aria-controls="route-candidate-cards" onClick={() => setResultPanelOpen((open) => !open)}>{resultPanelOpen ? "숨기기" : "보이기"}</button>
          </header>
          {resultPanelOpen && (
          <div id="route-candidate-cards" className="floating-results-body">
          {livePreview.active && displayedCandidates.length === 0 && (
            <section className="route-card route-card--preview" aria-label="맞춤경로 입력 조건">
              <span className="route-card-title"><strong>실시간 분석</strong></span>
              {!livePreview.blocked && <RecommendationIcons factors={[]} conditions={livePreview.cards} preview />}
              <p className="live-preview-hint">{livePreview.blocked ? "실시간 조건 분석 중단" : livePreview.updating ? "새 입력 분석 중 · 경로는 검색 후 표시합니다." : "경로는 검색 후 표시합니다."}</p>
              {livePreview.notice && <p className="live-preview-notice" role="status">{livePreview.notice}</p>}
            </section>
          )}
          {searchResult && searchResult.result.recommendation_status !== "ready" && (
            <p className="route-review-warning" role="status">
              {searchResult?.result.recommendation_reason ?? "경로 추천을 확정하지 못했습니다."} 아래 경로는 비교용 후보이며 추천 경로가 아닙니다.
            </p>
          )}
          <div className="route-cards">
            {displayedCandidates.map(({ candidate, label }) => {
              const active = candidate.route_type === selectedRouteType;
              const walkingMinutes = estimatedWalkingMinutes(candidate.route.properties.total_distance_m);
              const previewRouteType = displayedCandidates.find((item) => item.candidate.route_type === "custom")?.candidate.route_type ?? searchResult?.result.selected_route_type;
              const showConditions = livePreview.active ? candidate.route_type === previewRouteType : candidate.route_type === searchResult?.result.selected_route_type;
              return (
                <div key={candidate.route_type} className="route-card-group">
                <button type="button" className={`route-card ${active ? "route-card--active" : ""}`} onClick={() => void selectRoute(candidate.route_type)} aria-pressed={active}>
                  <span className="route-card-title"><strong><i className={`route-swatch ${active ? "route-swatch--active" : ""}`} aria-hidden="true" />{label}</strong></span>
                  <span className="route-card-primary"><strong>{walkingMinutes === null ? "시간 미제공" : <>{walkingMinutes}<span className="route-time-unit">분</span></>}</strong><span>{formatDistance(candidate.route.properties.total_distance_m)}</span></span>
                  {showConditions && <>
                    {livePreview.active && <span className="live-preview-hint">{livePreview.blocked ? "실시간 조건 분석 중단" : livePreview.updating ? "새 입력 분석 중 · 경로는 검색 후 갱신" : "실시간 분석 · 경로는 검색 후 갱신"}</span>}
                    {(!livePreview.active || !livePreview.blocked) && <RecommendationIcons factors={searchResult?.result.recommendation_factors ?? []} conditions={livePreview.active ? livePreview.cards : searchResult?.result.recommendation_conditions} preview={livePreview.active} />}
                    {livePreview.active && livePreview.notice && <span className="live-preview-notice" role="status">{livePreview.notice}</span>}
                  </>}
                  <span className="route-card-details">
                    계단 {candidate.route.properties.stairs_segment_count}개
                    {" | "}육교 {candidate.route.properties.intersection_data_available ? `${candidate.route.properties.pedestrian_bridge_count ?? 0}개` : "확인 불가"}
                    {" | "}{formatCrosswalkCount(candidate.route.properties.total_crosswalk_count)}
                  </span>
                </button>
                {active && <button type="button" className="route-detail-button" onClick={() => setRouteDetailOpen((open) => !open)} aria-pressed={routeDetailOpen} title={routeDetailOpen ? "경로 전체가 보이는 시점으로 전환" : "출발지에서 도착지 방향으로 경로를 가까이 보기"}>{routeDetailOpen ? "전체 경로 보기" : "자세히 보기"}</button>}
                </div>
              );
            })}
          </div>
          {selectedCandidate?.route.properties.unverified_major_road_count ? (
            <p className="route-review-warning">현장 확인이 필요한 대로 구간 {selectedCandidate.route.properties.unverified_major_road_count}개가 포함됩니다.</p>
          ) : null}
          </div>
          )}
        </aside>
      )}
      {nightMode && facilityVisibility.streetlights && (
        <div className="density-legend" role="img" aria-label="등록된 가로등의 상대 밀집도입니다. 색상은 적음, 보통, 많음을 구분하며 실제 조도나 안전을 나타내지 않습니다.">
          <span>가로등 밀집도</span>
          <span className="density-legend-gradient" aria-hidden="true" />
          <span className="density-legend-scale"><span>적음</span><span>보통</span><span>많음</span></span>
        </div>
      )}
      </div>

      <div className="facility-panel-shell">
      <nav id="facility-controls" className="facility-controls" aria-label="시설 표시">
        <button
          type="button"
          aria-label="가로등 위치와 상대 밀집도 표시"
          aria-pressed={facilityVisibility.streetlights}
          title={nightMode ? "가로등 밀집도 (실제 조도 아님)" : "가로등 위치"}
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            streetlights: !current.streetlights,
          }))}
        ><img src={facilityToggleImage("streetlights")} width="24" height="24" alt="" aria-hidden="true" /></button>
        <button
          type="button"
          aria-label="CCTV 표시"
          aria-pressed={facilityVisibility.cctvs}
          title="CCTV"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            cctvs: !current.cctvs,
          }))}
        ><img src={facilityToggleImage("cctvs")} width="24" height="24" alt="" aria-hidden="true" /></button>
        <button
          type="button"
          aria-label="안전지원시설 표시"
          aria-pressed={facilityVisibility.helpPoints}
          title="안전지원시설"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            helpPoints: !current.helpPoints,
          }))}
        ><img src={facilityToggleImage("helpPoints")} width="24" height="24" alt="" aria-hidden="true" /></button>
        <button
          type="button"
          aria-label="계단·육교 표시"
          aria-pressed={facilityVisibility.stairsAndBridges}
          title="계단·육교"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            stairsAndBridges: !current.stairsAndBridges,
          }))}
        ><img src={facilityToggleImage("stairsAndBridges")} width="24" height="24" alt="" aria-hidden="true" /></button>
      </nav>
      </div>

      <div className={`search-panel-shell ${searchPanelOpen ? "" : "search-panel-shell--collapsed"}`}>
      <div id="map-sidebar-content" className="sidebar-content" inert={!searchPanelOpen} aria-hidden={!searchPanelOpen}>
      <div className="sidebar-primary">
      <header className="sidebar-header" data-map-status={systemReady ? "ready" : "pending"}>
        <div className="brand-row">
          <button type="button" className="brand-chip" aria-label="SafeAlley 새로고침" onClick={() => window.location.reload()}><strong>SafeAlley<span>안전한 길찾기</span></strong></button>
          <WeatherHud {...weather} />
        </div>
      </header>
      <section id="route-search-panel" className="search-panel" aria-label="경로 검색">
        <div className="segmented-control" role="tablist" aria-label="검색 방식">
          <button type="button" role="tab" aria-selected={mode === "ai"} onClick={() => { ++buildingRequestSerial.current; setBuildingSelectionPending(false); setMode("ai"); setBuildingSelectionMode(null); setMapSelectionNotice(null); }}>AI 검색</button>
          <button type="button" role="tab" aria-selected={mode === "direct"} onClick={() => { livePreview.clear(); setMode("direct"); }}>직접 검색</button>
        </div>

        {mode === "direct" ? (
          <form className="route-form" onSubmit={searchDirect}>
            <div className="place-inputs">
              <div className="location-input"><input aria-label="출발지" value={originLocation.displayName} placeholder="출발지 입력" onChange={(event) => editLocation("origin", event.target.value)} required /><button type="button" aria-label="출발지 지도 선택" aria-pressed={buildingSelectionMode === "origin"} title="지도에서 출발지 건물 선택" onClick={() => toggleBuildingSelection("origin")}><img src={routeInputMarkerImage("origin")} width="28" height="35" alt="" aria-hidden="true" /></button></div>
              <i aria-hidden="true" />
              <div className="location-input"><input aria-label="도착지" value={destinationLocation.displayName} placeholder="도착지 입력" onChange={(event) => editLocation("destination", event.target.value)} required /><button type="button" aria-label="도착지 지도 선택" aria-pressed={buildingSelectionMode === "destination"} title="지도에서 도착지 건물 선택" onClick={() => toggleBuildingSelection("destination")}><img src={routeInputMarkerImage("destination")} width="28" height="35" alt="" aria-hidden="true" /></button></div>
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
                </label>
                <PreferenceSlider label="안전 관련 시설" value={safetyWeight} onChange={setSafetyWeight} description="낮음은 거리 우선, 높음은 안전 시설 우선" />
                <PreferenceSlider label="계단 회피" value={stairsWeight} onChange={setStairsWeight} />
                <PreferenceSlider label="건널목 회피" value={crossingWeight} onChange={setCrossingWeight} />
              </div>
            )}
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        ) : (
          <form className="route-form" onSubmit={searchWithAi}>
            <div className="ai-query">
              <SpeechInput value={query} onText={(text) => { setQuery(text); livePreview.update(text); }} disabled={requestState === "loading" || !searchPanelOpen}>
                <textarea id="ai-route-query" aria-label="AI 경로 요청" value={query} onChange={(event) => { setQuery(event.target.value); livePreview.update(event.target.value); }} disabled={requestState === "loading"} rows={3} required />
              </SpeechInput>
            </div>
            <button className="search-button" type="submit" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "경로 검색"}</button>
          </form>
        )}
        {requestState === "error" && <p className="route-error" role="alert">{errorMessage}</p>}
      </section>

      <div ref={processScrollRef} className="sidebar-scroll" role="region" aria-label="경로 검색 처리 내용" tabIndex={0}>
      {activeSearchMode === "ai" && (requestState === "loading" || requestState === "error" || searchResult?.mode === "ai") && (
        <RouteProgressPanel
          stage={progressStage}
          interpretation={progressInterpretation}
          originName={progressPlaces.origin}
          destinationName={progressPlaces.destination}
          result={searchResult?.mode === "ai" ? searchResult.result : null}
          workUpdates={progressWork}
        />
      )}

      {!mapInfo && !searchResult && displayedCandidates.length === 0 && requestState !== "loading" && <div className="search-empty"><span aria-hidden="true">↗</span><strong>나에게 맞는 길을 찾아보세요</strong><p>장소를 입력하거나 지도에서 건물을 선택해<br />출발지와 도착지를 지정할 수 있어요.</p></div>}
      </div>
      </div>
      {mapInfo && (
        <aside className="map-info-panel" aria-label="지도 객체 정보">
          <header>
            <div>
              <span>{mapInfo.kind === "building" ? "건물 상세 정보" : mapInfo.kind === "route_segment" ? "경로 구간" : mapInfo.kind === "streetlight" ? "가로등 정보" : mapInfo.kind === "cctv" ? "CCTV 정보" : mapInfo.kind === "stairs" ? "계단 정보" : "육교 정보"}</span>
              <strong>{mapInfo.title}</strong>
            </div>
            <button className="panel-close" type="button" aria-label="지도 객체 정보 닫기" onClick={() => setMapInfo(null)}>×</button>
          </header>
          {mapInfo.kind === "building" && (
            <div className="building-location-actions" role="group" aria-label="건물 경로 선택">
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
      </div>
      <button className="search-panel-handle" type="button" aria-label={searchPanelOpen ? "검색·결과·상세 패널 접기" : "검색·결과·상세 패널 열기"} aria-controls="map-sidebar-content" aria-expanded={searchPanelOpen} onClick={() => {
        setSearchPanelOpen((open) => !open);
        ++buildingRequestSerial.current;
        setBuildingSelectionPending(false);
        setBuildingSelectionMode(null);
        setMapSelectionNotice(null);
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><polyline points={searchPanelOpen ? "15 5 9 12 15 19" : "9 5 15 12 9 19"} /></svg>
      </button>
      </div>
    </main>
  );
}

export default App;
