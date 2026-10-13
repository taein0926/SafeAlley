import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { isNightDepartureTime } from "./nightMode";
import { defaultStreetlightVisibility } from "./mapLighting";
import { PreferenceSlider } from "./components/PreferenceSlider";
import { RecommendationIcons } from "./components/RecommendationIcons";
import { RouteProgressPanel } from "./components/RouteProgressPanel";
import { SpeechInput } from "./components/SpeechInput";
import { WelcomeIntro } from "./components/WelcomeIntro";
import { useWeather, WeatherHud } from "./components/WeatherHud";
import { facilityToggleFactor } from "./facilityToggleIcons";
import { ConditionIcon } from "./components/ConditionIcon";
import { routeInputMarkerImage } from "./routeMarkers";
import { createRouteSelectionSaver } from "./routeSelection";
import { mergeWorkUpdate, queryRouteWithProgress } from "./routeProgress";
import type { RouteWorkUpdate } from "./routeProgress";
import { useLiveIntentPreview } from "./useLiveIntentPreview";
import { createExampleTyper } from "./exampleTyping";
import { ExamplePicker } from "./components/ExamplePicker";
import { errorFromApiDetail, PlaceSelectionRequiredError, type MapFocusBounds, type PlaceSelectionTarget } from "./placeSelection";

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
const SEARCH_EXAMPLES = [
  "밤 10시에 도화119안전센터에서 두리하나어린이집 및 육아종합지원센터까지 가려고 해. 가로등이 많고 계단 없는 길로 안내해줘.",
  "낮 2시에 경원초등학교에서 신기프라자까지 CCTV가 많은 길로 안내해줘.",
  "밤 11시에 인천 비즈니스 고등학교에서 인천청인학교까지 가로등이 많고 횡단보도 적게 건너는 길로 가고 싶어",
  "낮 2시에 인천비즈니스고등학교에서 와이지타워까지 CCTV가 많고 건널목을 적게 건너는 길로 안내해줘.",
] as const;
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
  const data = (await response.json()) as T & { detail?: unknown };
  if (!response.ok) throw errorFromApiDetail(data.detail, `HTTP ${response.status}`);
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
  const [mapFocus, setMapFocus] = useState<MapFocusBounds | null>(null);
  const buildingRequestSerial = useRef(0);
  const [buildingSelectionPending, setBuildingSelectionPending] = useState(false);
  const [criteriaOpen, setCriteriaOpen] = useState(false);
  const [searchPanelOpen, setSearchPanelOpen] = useState(true);
  const [safetyWeight, setSafetyWeight] = useState(50);
  const [stairsWeight, setStairsWeight] = useState(50);
  const [crossingWeight, setCrossingWeight] = useState(50);
  const [departureTime, setDepartureTime] = useState(() => currentLocalTime());
  const [appliedDepartureTime, setAppliedDepartureTime] = useState<string | null>(departureTime);
  const [weatherRequested, setWeatherRequested] = useState(false);
  const [query, setQuery] = useState("");
  const [queryEditing, setQueryEditing] = useState(false);
  const [requestState, setRequestState] = useState<RequestState>("idle");
  const [activeSearchMode, setActiveSearchMode] = useState<SearchMode | null>(null);
  const [progressStage, setProgressStage] = useState<"interpreting" | "resolving" | "routing" | "done" | "failed">("interpreting");
  const [progressInterpretation, setProgressInterpretation] = useState<RouteQueryResponse["interpretation"] | null>(null);
  const [progressWork, setProgressWork] = useState<RouteWorkUpdate[]>([]);
  const livePreview = useLiveIntentPreview();
  const [exampleTyping, setExampleTyping] = useState(false);
  const queryInputRef = useRef<HTMLTextAreaElement>(null);
  const exampleTyper = useRef<ReturnType<typeof createExampleTyper> | null>(null);
  useEffect(() => {
    const typer = createExampleTyper({
      onText: (text) => { setQuery(text); livePreview.update(text); },
      onTypingChange: setExampleTyping,
    });
    exampleTyper.current = typer;
    return () => { typer.dispose(); exampleTyper.current = null; };
  }, [livePreview.update]);
  useEffect(() => { if (exampleTyping) queryInputRef.current?.focus(); }, [exampleTyping]);

  function typeExample(text: string) {
    if (requestState === "loading") return;
    exampleTyper.current?.cancel();
    livePreview.clear();
    ++buildingRequestSerial.current;
    setBuildingSelectionPending(false);
    setBuildingSelectionMode(null);
    setMapSelectionNotice(null);
    setMode("ai");
    setSearchPanelOpen(true);
    setMapInfo(null);
    setErrorMessage("");
    setRequestState("idle");
    setActiveSearchMode(null);
    setQueryEditing(true);
    exampleTyper.current?.start(text);
    queryInputRef.current?.focus();
  }

  function editQuery(text: string) {
    exampleTyper.current?.cancel();
    setQueryEditing(true);
    setActiveSearchMode(null);
    setRequestState("idle");
    setErrorMessage("");
    setMapInfo(null);
    setQuery(text);
    livePreview.update(text);
  }
  const processScrollRef = useRef<HTMLDivElement>(null);
  const [progressPlaces, setProgressPlaces] = useState<{ origin: string | null; destination: string | null }>({ origin: null, destination: null });
  const [errorMessage, setErrorMessage] = useState("");
  const [searchResult, setSearchResult] = useState<RouteSearchResult | null>(null);
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
  const showSearchResults = !queryEditing && displayedCandidates.length > 0;
  const previewBusy = mode === "ai" && queryEditing && livePreview.active && !livePreview.completed && !livePreview.blocked && requestState !== "loading";
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
    exampleTyper.current?.cancel();
    livePreview.clear();
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
      setMapFocus(null);
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
  }, [buildingSelectionMode, requestState, livePreview.clear]);

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
    setQueryEditing(false);
    setActiveSearchMode(searchMode);
    setProgressStage("interpreting");
    setProgressInterpretation(null);
    setProgressWork([]);
    setProgressPlaces({ origin: null, destination: null });
    setErrorMessage("");
    setSearchResult(null);
    setSelectedRouteType(null);
    setBuildingSelectionMode(null);
    setMapFocus(null);
    setMapSelectionNotice(null);
    setMapInfo(null);
  }

  function finishSearch(result: RouteSearchResult) {
    setAppliedDepartureTime(result.departureTime ?? currentLocalTime());
    setWeatherRequested(true);
    setSearchResult(result);
    setQueryEditing(false);
    setSelectedRouteType(
      result.result.recommendation_status === "ready"
        ? result.result.selected_route_type
        : null,
    );
    setRequestState("idle");
  }

  function failSearch(error: unknown, interpretation?: RouteQueryResponse["interpretation"] | null) {
    if (error instanceof PlaceSelectionRequiredError) {
      const target = error.target ?? "origin";
      if (interpretation?.origin_name) {
        setOriginLocation({ displayName: interpretation.origin_name, source: "text" });
      }
      if (interpretation?.destination_name) {
        setDestinationLocation({ displayName: interpretation.destination_name, source: "text" });
      }
      if (interpretation?.departure_time) setDepartureTime(interpretation.departure_time.slice(0, 5));
      setMode("direct");
      setSearchPanelOpen(true);
      setBuildingSelectionMode(target);
      setMapFocus(error.focus);
      setMapSelectionNotice({
        kind: "instruction",
        text: `${target === "origin" ? "출발지" : "도착지"}로 사용할 건물을 지도에서 선택하세요.`,
      });
    }
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
    beginSearch("direct");
    try {
      const resolveTarget = async (location: DirectLocationInput, target: PlaceSelectionTarget) => {
        try {
          return await resolveDirectLocation(location, resolvePlace);
        } catch (error) {
          if (error instanceof PlaceSelectionRequiredError) throw error.forTarget(target);
          throw error;
        }
      };
      const [origin, destination] = await Promise.all([
        resolveTarget(originLocation, "origin"),
        resolveTarget(destinationLocation, "destination"),
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
    await runAiSearch(query);
  }

  async function runAiSearch(text: string) {
    if (requestState === "loading" || !text.trim()) return;
    exampleTyper.current?.cancel();
    setMode("ai");
    setQuery(text);
    livePreview.pause();
    beginSearch("ai");
    let interpreted: RouteQueryResponse["interpretation"] | null = null;
    try {
      const data = await queryRouteWithProgress(text.trim(), userId, (event) => {
        if (event.type === "stage") setProgressStage(event.stage);
        if (event.type === "interpreted") {
          interpreted = event.data;
          setProgressInterpretation(event.data);
        }
        if (event.type === "route_progress") setProgressWork((updates) => mergeWorkUpdate(updates, event.data));
        if (event.type === "resolved") setProgressPlaces({
          origin: event.origin?.name ?? null,
          destination: event.destination?.name ?? null,
        });
      });
      setProgressStage("done");
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
      failSearch(error, interpreted);
    }
  }

  const selectRoute = useCallback(async (routeType: RouteType) => {
    setSearchPanelOpen(true);
    setMapInfo(null);
    if (routeType === selectedRouteType) return;
    setSelectedRouteType(routeType);
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
    <main className={`app-shell ${mapInfo ? "app-shell--map-info" : ""} ${searchPanelOpen ? "" : "app-shell--sidebar-closed"}`} data-theme="day">
      <WelcomeIntro />
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
        focusBounds={mapFocus}
      />
      {showSearchResults && !mapInfo && (
        <aside id="route-results" className="result-panel result-panel--floating" aria-label="경로 검색 결과">
          <div id="route-candidate-cards" className="floating-results-body">
          {searchResult && searchResult.result.recommendation_status !== "ready" && (
            <p className="route-review-warning" role="status">
              {searchResult?.result.recommendation_reason ?? "경로 추천을 확정하지 못했습니다."} 아래 경로는 비교용 후보이며 추천 경로가 아닙니다.
            </p>
          )}
          <div className="route-cards">
            {displayedCandidates.map(({ candidate, label }) => {
              const active = candidate.route_type === selectedRouteType;
              const walkingMinutes = estimatedWalkingMinutes(candidate.route.properties.total_distance_m);
              const showConditions = candidate.route_type === searchResult?.result.selected_route_type;
              return (
                <div key={candidate.route_type} className="route-card-group">
                <button type="button" className={`route-card ${active ? "route-card--active" : ""}`} onClick={() => void selectRoute(candidate.route_type)} aria-pressed={active}>
                  <span className="route-card-title"><strong><i className={`route-swatch ${active ? "route-swatch--active" : ""}`} aria-hidden="true" />{label}</strong></span>
                  <span className="route-card-primary"><strong>{walkingMinutes === null ? "시간 미제공" : <>{walkingMinutes}<span className="route-time-unit">분</span></>}</strong><span>{formatDistance(candidate.route.properties.total_distance_m)}</span></span>
                  <span className="route-card-details">
                    계단 {candidate.route.properties.stairs_segment_count}개
                    {" | "}육교 {candidate.route.properties.intersection_data_available ? `${candidate.route.properties.pedestrian_bridge_count ?? 0}개` : "확인 불가"}
                    {" | "}{formatCrosswalkCount(candidate.route.properties.total_crosswalk_count)}
                  </span>
                  {showConditions && <RecommendationIcons factors={searchResult?.result.recommendation_factors ?? []} conditions={searchResult?.result.recommendation_conditions} />}
                </button>
                </div>
              );
            })}
          </div>
          </div>
        </aside>
      )}
      <nav className="map-view-toggle" aria-label="지도 시점">
        <button type="button" aria-label="2D 지도" aria-pressed={!routeDetailOpen} onClick={() => setRouteDetailOpen(false)} title="2D · 전체 경로를 위에서 보기">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true"><rect x="5" y="5" width="14" height="14" rx="1" /></svg><span>2D</span>
        </button>
        <button type="button" aria-label="3D 지도" aria-pressed={routeDetailOpen} onClick={() => setRouteDetailOpen(true)} title="3D · 건물과 경로를 사선으로 보기">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" aria-hidden="true"><path d="m12 2 10 5v10l-10 5-10-5V7Z" /><path d="m2 7 10 5 10-5M12 12v10" /></svg><span>3D</span>
        </button>
      </nav>
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
          aria-label="가로등 표시"
          aria-pressed={facilityVisibility.streetlights}
          title="가로등"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            streetlights: !current.streetlights,
          }))}
        ><ConditionIcon factor={facilityToggleFactor("streetlights")} size={24} applied={facilityVisibility.streetlights} /></button>
        <button
          type="button"
          aria-label="CCTV 표시"
          aria-pressed={facilityVisibility.cctvs}
          title="CCTV"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            cctvs: !current.cctvs,
          }))}
        ><ConditionIcon factor={facilityToggleFactor("cctvs")} size={24} applied={facilityVisibility.cctvs} /></button>
        <button
          type="button"
          aria-label="안전시설 표시"
          aria-pressed={facilityVisibility.helpPoints}
          title="안전시설"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            helpPoints: !current.helpPoints,
          }))}
        ><ConditionIcon factor={facilityToggleFactor("helpPoints")} size={24} applied={facilityVisibility.helpPoints} /></button>
        <button
          type="button"
          aria-label="계단·육교 표시"
          aria-pressed={facilityVisibility.stairsAndBridges}
          title="계단·육교"
          onClick={() => setFacilityVisibility((current) => ({
            ...current,
            stairsAndBridges: !current.stairsAndBridges,
          }))}
        ><ConditionIcon factor={facilityToggleFactor("stairsAndBridges")} size={24} showAvoidance={false} applied={facilityVisibility.stairsAndBridges} /></button>
      </nav>
      </div>

      <div className={`search-panel-shell ${searchPanelOpen ? "" : "search-panel-shell--collapsed"}`}>
      <div id="map-sidebar-content" className="sidebar-content" inert={!searchPanelOpen} aria-hidden={!searchPanelOpen}>
      <div className="sidebar-primary">
      <header className="sidebar-header" data-map-status={systemReady ? "ready" : "pending"}>
        <div className="brand-row">
          <div className="brand-identity">
          <button type="button" className="brand-chip" aria-label="안전골목길 새로고침" onClick={() => window.location.reload()}><strong>안전골목길</strong></button>
          <p className="brand-slogan">골목에 안전을 더하다</p>
          </div>
        </div>
      </header>
      <section id="route-search-panel" className="search-panel" aria-label="경로 검색">
        {mode === "direct" ? (
          <form id="route-search-form" className="route-form" onSubmit={searchDirect}>
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
                  <div className="departure-time-control">
                    <input aria-label="출발 시간" type="time" value={departureTime} onChange={(event) => setDepartureTime(event.target.value)} required />
                    <button type="button" onClick={() => setDepartureTime(currentLocalTime())}>현재 시간</button>
                  </div>
                <PreferenceSlider label="경로 우선순위" value={safetyWeight} onChange={setSafetyWeight} levelLabels={["거리", "균형", "안전"]} />
                <PreferenceSlider label="계단 회피" value={stairsWeight} onChange={setStairsWeight} />
                <PreferenceSlider label="횡단보도 회피" value={crossingWeight} onChange={setCrossingWeight} />
              </div>
            )}
          </form>
        ) : (
          <form id="route-search-form" className="route-form" onSubmit={searchWithAi}>
            <div className="ai-query">
              <SpeechInput value={query} onText={editQuery} disabled={requestState === "loading" || !searchPanelOpen || exampleTyping}>
                <textarea ref={queryInputRef} id="ai-route-query" aria-label="문장으로 경로 요청" placeholder="어디로, 어떤 길로 가고 싶나요?" value={query} data-example-typing={exampleTyping || undefined}
                  onChange={(event) => editQuery(event.target.value)}
                  onBeforeInput={() => exampleTyper.current?.cancel()}
                  onPointerDown={() => exampleTyper.current?.cancel()}
                  onKeyDown={(event) => {
                    if (event.key === "Escape" || event.key === "Backspace" || event.key === "Delete" || event.key.length === 1) exampleTyper.current?.cancel();
                  }}
                  disabled={requestState === "loading"} rows={3} required />
              </SpeechInput>
            </div>
          </form>
        )}
        {mode === "ai" && (
          <section className="search-intent-preview" aria-label="맞춤경로 입력 조건" aria-busy={previewBusy}>
            <div className="search-intent-heading"><strong title="입력 중 요청 인식이며 실제 경로 반영은 검색 후 확정됩니다">{livePreview.blocked ? "요구사항 분석 불가" : livePreview.completed ? "요구사항 분석 완료" : previewBusy ? "요구사항 분석 중" : "요구사항 분석"}{previewBusy && <span className="live-preview-dots" role="status" aria-label="조건 분석 진행 중"><i /><i /><i /></span>}</strong>{livePreview.blocked && <span className="live-preview-error" role="status" title={livePreview.notice ?? undefined}>분석 사용 불가</span>}</div>
            <RecommendationIcons factors={[]} conditions={livePreview.cards} preview />
          </section>
        )}
        <div className="search-mode-toolbar">
          <button type="button" className="search-mode-switch" aria-label={mode === "ai" ? "직접 설정" : "문장 입력"} title={mode === "ai" ? "직접 설정" : "문장 입력"} disabled={requestState === "loading"} onClick={() => {
            ++buildingRequestSerial.current;
            setBuildingSelectionPending(false);
            setBuildingSelectionMode(null);
            setMapSelectionNotice(null);
            exampleTyper.current?.cancel();
            livePreview.clear();
            setMode(mode === "ai" ? "direct" : "ai");
          }}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false">
              {mode === "ai" ? <><path d="M3 5h4m4 0h10M3 12h10m4 0h4M3 19h4m4 0h10" /><circle cx="9" cy="5" r="2" /><circle cx="15" cy="12" r="2" /><circle cx="9" cy="19" r="2" /></> : <path d="M20 4H4a2 2 0 0 0-2 2v11a2 2 0 0 0 2 2h3v3l5-3h8a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2ZM7 9h10M7 13h6" />}
            </svg>
          </button>
          <ExamplePicker examples={SEARCH_EXAMPLES} disabled={requestState === "loading" || !searchPanelOpen} onSelect={typeExample} />
          <button className="search-button" type="submit" form="route-search-form" disabled={requestState === "loading"}>{requestState === "loading" ? "검색 중..." : "길찾기"}</button>
        </div>
        <div className="search-weather"><WeatherHud {...weather} requested={weatherRequested} /></div>
        {requestState === "error" && <p className="route-error" role="alert">{errorMessage}</p>}
      </section>

      <div ref={processScrollRef} className="sidebar-scroll" role="region" aria-label="경로 검색 처리 내용" tabIndex={0}>
      {!queryEditing && activeSearchMode === "ai" && (requestState === "loading" || requestState === "error" || searchResult?.mode === "ai") && (
        <RouteProgressPanel
          stage={progressStage}
          interpretation={progressInterpretation}
          originName={progressPlaces.origin}
          destinationName={progressPlaces.destination}
          result={searchResult?.mode === "ai" ? searchResult.result : null}
          workUpdates={progressWork}
        />
      )}

      {displayedCandidates.length === 0 && requestState !== "loading" && <div className="search-empty">
        <span aria-hidden="true">↗</span><strong>나에게 맞는 길을 찾아보세요</strong><p>장소를 입력하거나 지도에서 건물을 선택해<br />출발지와 도착지를 지정할 수 있어요.</p>
      </div>}
      </div>
      </div>
      </div>
      <button className="search-panel-handle" type="button" aria-label={searchPanelOpen ? "검색·결과·상세 패널 접기" : "검색·결과·상세 패널 열기"} aria-controls="map-sidebar-content" aria-expanded={searchPanelOpen} onClick={() => {
        exampleTyper.current?.cancel();
        setSearchPanelOpen((open) => !open);
        ++buildingRequestSerial.current;
        setBuildingSelectionPending(false);
        setBuildingSelectionMode(null);
        setMapSelectionNotice(null);
      }}>
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" focusable="false"><polyline points={searchPanelOpen ? "15 5 9 12 15 19" : "9 5 15 12 9 19"} /></svg>
      </button>
      </div>
      {searchPanelOpen && mapInfo && (
        <aside className="map-info-panel floating-secondary" data-kind={mapInfo.kind} aria-label="지도 객체 정보">
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
    </main>
  );
}

export default App;
