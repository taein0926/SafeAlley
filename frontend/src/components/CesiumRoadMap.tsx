import {
  BillboardCollection,
  CallbackProperty,
  BoundingSphere,
  Cartesian3,
  Cartesian2,
  Cartographic,
  ClassificationType,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  Credit,
  DistanceDisplayCondition,
  Entity,
  GeoJsonDataSource,
  HeightReference,
  HeadingPitchRange,
  ImageryLayer,
  Ion,
  JulianDate,
  Math as CesiumMath,
  Matrix4,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  PerspectiveFrustum,
  Rectangle,
  ScreenSpaceEventType,
  UrlTemplateImageryProvider,
  Transforms,
  Viewer,
  SceneTransforms,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { RouteCandidate, RouteType } from "../types";
import { estimatedWalkingMinutes, type BuildingMapSelection } from "../routeSearch";
export type { BuildingMapSelection } from "../routeSearch";
import { roadBboxQuery, type RoadViewport } from "../roadViewport";
import { BuildingViewportRequests, boundsIntersect, geometryBounds } from "../buildingViewport";
import { STAIRS_MARKER_IMAGE, stairMarkerPosition } from "../stairsMarkers";
import { CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE, bridgeMarkerPosition } from "../bridgeMarkers";
import { mapLighting, STREETLIGHT_GLOW_IMAGE } from "../mapLighting";
import { CCTV_MARKER_IMAGE, helpPointMarkerImage } from "../facilityMarkers";
import { routeMarkerImage, routeMarkerLocations, routeAccessConnectors, selectedRouteLabelLocation } from "../routeMarkers";
import { CROSSING_GUIDE_IMAGE, selectedRouteGuidePoints } from "../routeGuidePoints";
import { INITIAL_MAP_VIEW, zoomTargetHeight } from "../mapNavigation";
import { routeCapPath, routeEndCaps, routeGeometrySignature, routeLineStyle, routePickPriority } from "../routePresentation";
import { routeCameraFrame, routeCameraHeading, routeCameraTargetOffset } from "../routeCamera";
import { FacilityViewportCache, type FacilityFeature } from "../facilityViewport";
import { MapRenderQuality, setRenderResolution, MOVING_RESOLUTION, REST_RESOLUTION } from "../mapRenderQuality";
import type { MapFocusBounds } from "../placeSelection";

export type BuildingMapStatus = {
  kind: "loading" | "ready" | "zoom-in" | "error";
  count: number;
  cachedCount?: number;
};

export type RoadMapStatus =
  | { kind: "loading" }
  | {
      kind: "ready";
      buildingCount: number;
      streetlightCount: number;
      cctvCount: number;
      cctvRecordCount: number;
      helpPointCount: number;
    }
  | { kind: "error"; message: string };

type CesiumRoadMapProps = {
  onStatusChange: (status: RoadMapStatus) => void;
  onBuildingStatusChange?: (status: BuildingMapStatus) => void;
  routeCandidates: RouteCandidate[];
  selectedRouteType: RouteType | null;
  routeDetailOpen: boolean;
  facilityVisibility: FacilityVisibility;
  buildingSelectionMode: BuildingSelectionMode;
  onBuildingSelect: (selection: BuildingMapSelection) => void;
  onInvalidBuildingSelect: (message?: string) => void;
  draftLocations: DraftMapLocation[];
  onMapInfoChange: (selection: MapInfoSelection | null) => void;
  nightMode: boolean;
  onResetView: () => void;
  focusBounds: MapFocusBounds | null;
};

export type FacilityVisibility = {
  streetlights: boolean;
  cctvs: boolean;
  helpPoints: boolean;
  stairsAndBridges: boolean;
};

export type BuildingSelectionMode = "origin" | "destination" | null;

export type DraftMapLocation = {
  kind: "origin" | "destination";
  latitude: number;
  longitude: number;
};

export type MapInfoSelection = {
  kind: "building" | "streetlight" | "cctv" | "route_segment" | "stairs" | "bridge";
  title: string;
  rows: Array<{ label: string; value: string }>;
  buildingSelection?: BuildingMapSelection;
  routeType?: RouteType;
};

function infoRows(
  rows: Array<[string, unknown]>,
): Array<{ label: string; value: string }> {
  return rows
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([label, value]) => ({ label, value: String(value) }));
}

type FeatureCollectionMetadata = {
  count: number;
  crs: string;
  record_count?: number;
  coordinate_quality_counts?: Record<string, number>;
  position_semantics?: "coordinate_cells" | "point_locations";
};

type RoadFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: number | string;
    geometry: {
      type: "LineString";
      coordinates: number[][];
    };
    properties: {
      safety_score: number;
      nearest_light_distance_m: number;
      nearby_light_count: number;
      light_density: number;
      dark_gap_proxy_m: number;
      [key: string]: unknown;
    };
  }>;
  metadata: FeatureCollectionMetadata;
};

type PointFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: number | string;
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: Record<string, unknown>;
  }>;
  metadata: FeatureCollectionMetadata;
};

type BuildingFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: number | string;
    geometry: {
      type: "Polygon" | "MultiPolygon";
      coordinates: unknown;
    };
    properties: Record<string, unknown>;
  }>;
  metadata: FeatureCollectionMetadata;
};

function escapeHtml(value: unknown): string {
  return String(value ?? "-")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function buildingDescription(properties: Record<string, unknown>): string {
  const rows = [
    ["건물명", properties.building_name],
    ["주용도", properties.main_use],
    ["건축면적", properties.building_area == null ? null : `${properties.building_area}㎡`],
    ["연면적", properties.total_floor_area == null ? null : `${properties.total_floor_area}㎡`],
    ["높이", properties.height_m == null ? null : `${properties.height_m}m`],
    ["층수", properties.floors],
    ["주소", properties.address],
    ["출처", properties.source],
  ];
  return `<table class="cesium-infoBox-defaultTable"><tbody>${rows
    .map(
      ([label, value]) =>
        `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`,
    )
    .join("")}</tbody></table>`;
}

function pointDescription(
  title: string,
  properties: Record<string, unknown>,
  rows: Array<[string, unknown]>,
  layer: "cctv",
): Entity {
  const description = `<table class="cesium-infoBox-defaultTable"><tbody>${rows
    .map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`)
    .join("")}</tbody></table>`;
  return new Entity({
    name: title,
    description: new ConstantProperty(description),
    properties: { ...properties, safealley_layer: layer },
  });
}

function webGlCapabilityError(): string | null {
  const canvas = document.createElement("canvas");
  const context = (
    canvas.getContext("webgl2") ??
    canvas.getContext("webgl") ??
    canvas.getContext("experimental-webgl")
  ) as WebGL2RenderingContext | WebGLRenderingContext | null;

  if (context === null) {
    return "이 브라우저에서 WebGL GPU 컨텍스트를 사용할 수 없습니다.";
  }

  const maximumTextureSize = Number(
    context.getParameter(context.MAX_TEXTURE_SIZE),
  );
  if (!Number.isFinite(maximumTextureSize) || maximumTextureSize <= 0) {
    return `이 브라우저의 WebGL 최대 텍스처 크기가 ${maximumTextureSize}으로 감지됐습니다.`;
  }

  return null;
}


function pickedWgs84Coordinate(
  viewer: Viewer,
  position: Cartesian2,
): { latitude: number; longitude: number } | null {
  let cartesian: Cartesian3 | undefined;
  if (viewer.scene.pickPositionSupported) {
    try {
      cartesian = viewer.scene.pickPosition(position);
    } catch {
      cartesian = undefined;
    }
  }
  cartesian ??= viewer.camera.pickEllipsoid(position, viewer.scene.globe.ellipsoid);
  if (!cartesian) return null;
  const cartographic = Cartographic.fromCartesian(cartesian);
  return {
    latitude: CesiumMath.toDegrees(cartographic.latitude),
    longitude: CesiumMath.toDegrees(cartographic.longitude),
  };
}

// Both camera modes use the same fit, leaving the floating cards outside the
// usable map area. Read live bounds only when a search or view toggle requests it.
function flyToRouteFrame(viewer: Viewer, coordinates: number[][], heading: number, pitch: number) {
  if (!coordinates.length) return;
  const canvasBounds = viewer.canvas.getBoundingClientRect();
  const frustum = viewer.camera.frustum;
  if (!(frustum instanceof PerspectiveFrustum) || canvasBounds.width <= 0 || canvasBounds.height <= 0) return;
  const shell = viewer.canvas.closest(".app-shell");
  const sidebarClosed = shell?.classList.contains("app-shell--sidebar-closed");
  const panels = Array.from(shell?.querySelectorAll(".sidebar-primary, .floating-secondary, #route-results") ?? [])
    .filter(panel => !sidebarClosed || panel.id === "route-results");
  const leftInset = Math.max(0, ...panels.map(panel => panel.getBoundingClientRect())
    .filter(bounds => bounds.width > 0 && bounds.right > canvasBounds.left && bounds.left < canvasBounds.right)
    .map(bounds => bounds.right - canvasBounds.left + 16));
  const sphere = BoundingSphere.fromPoints(coordinates.map(([lon, lat]) => Cartesian3.fromDegrees(lon, lat)));
  const transform = Transforms.eastNorthUpToFixedFrame(sphere.center);
  const inverse = Matrix4.inverseTransformation(transform, new Matrix4());
  const localPoints = coordinates.map(([lon, lat]) => Matrix4.multiplyByPoint(inverse, Cartesian3.fromDegrees(lon, lat), new Cartesian3()));
  // Keep endpoint pins clear of the top-right view toggle and facility rail.
  const frame = routeCameraFrame(localPoints, canvasBounds.width, canvasBounds.height, frustum.fovy ?? Math.PI / 3, leftInset, heading, 128, pitch);
  const offset = routeCameraTargetOffset(frame.rightOffset, heading, frame.upOffset, pitch);
  const target = Matrix4.multiplyByPoint(transform, new Cartesian3(offset.east, offset.north, offset.up), new Cartesian3());
  viewer.camera.flyToBoundingSphere(new BoundingSphere(target, sphere.radius), {
    duration: 0.8, offset: new HeadingPitchRange(heading, frame.pitch, frame.range),
  });
}

export function CesiumRoadMap({
  onStatusChange,
  onBuildingStatusChange,
  routeCandidates,
  selectedRouteType,
  routeDetailOpen,
  facilityVisibility,
  buildingSelectionMode,
  onBuildingSelect,
  onInvalidBuildingSelect,
  draftLocations,
  onMapInfoChange,
  nightMode,
  onResetView,
  focusBounds,
}: CesiumRoadMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const routePinsRef = useRef<HTMLDivElement>(null);
  const baseLayerRef = useRef<ImageryLayer | null>(null);
  const streetlightDensityLayerRef = useRef<ImageryLayer | null>(null);
  const routeCandidatesRef = useRef(routeCandidates);
  const selectedRouteTypeRef = useRef(selectedRouteType);
  const refreshBuildingsRef = useRef<(() => void) | null>(null);
  const refreshFacilitiesRef = useRef<(() => void) | null>(null);
  const streetlightPrimitivesRef = useRef<BillboardCollection | null>(null);
  const nightModeRef = useRef(nightMode);
  const cctvPrimitivesRef = useRef<BillboardCollection | null>(null);
  const helpPointPrimitivesRef = useRef<BillboardCollection | null>(null);
  const cctvCellEntityIdsRef = useRef<string[]>([]);
  const stairBridgeEntityIdsRef = useRef<string[]>([]);
  const buildingSelectionsRef = useRef<WeakMap<Entity, Omit<BuildingMapSelection, "latitude" | "longitude">>>(new WeakMap());
  const mapInfoRef = useRef<WeakMap<Entity, MapInfoSelection>>(new WeakMap());
  const routeEntityIdsRef = useRef<string[]>([]);
  const lastRouteSignatureRef = useRef("");
  const lastRouteDetailOpenRef = useRef(routeDetailOpen);
  const facilityVisibilityRef = useRef(facilityVisibility);
  const buildingSelectionModeRef = useRef(buildingSelectionMode);
  const onBuildingSelectRef = useRef(onBuildingSelect);
  const onInvalidBuildingSelectRef = useRef(onInvalidBuildingSelect);
  const onMapInfoChangeRef = useRef(onMapInfoChange);
  const [renderingError, setRenderingError] = useState<string | null>(null);

  useEffect(() => {
    facilityVisibilityRef.current = facilityVisibility;
    const viewer = viewerRef.current;
    if (streetlightPrimitivesRef.current) {
      streetlightPrimitivesRef.current.show = facilityVisibility.streetlights;
    }
    if (streetlightDensityLayerRef.current) {
      streetlightDensityLayerRef.current.show = nightModeRef.current && facilityVisibility.streetlights;
    }
    if (cctvPrimitivesRef.current) cctvPrimitivesRef.current.show = facilityVisibility.cctvs;
    if (helpPointPrimitivesRef.current) {
      helpPointPrimitivesRef.current.show = facilityVisibility.helpPoints;
    }
    if (viewer && !viewer.isDestroyed()) {
      for (const id of cctvCellEntityIdsRef.current) {
        const entity = viewer.entities.getById(id);
        if (entity) entity.show = facilityVisibility.cctvs;
      }
      for (const id of stairBridgeEntityIdsRef.current) {
        const entity = viewer.entities.getById(id);
        if (entity) entity.show = facilityVisibility.stairsAndBridges;
      }
      viewer.scene.requestRender();
    }
    refreshFacilitiesRef.current?.();
  }, [facilityVisibility]);

  useEffect(() => {
    selectedRouteTypeRef.current = selectedRouteType;
    buildingSelectionModeRef.current = buildingSelectionMode;
    onBuildingSelectRef.current = onBuildingSelect;
    onInvalidBuildingSelectRef.current = onInvalidBuildingSelect;
    onMapInfoChangeRef.current = onMapInfoChange;
  }, [buildingSelectionMode, onBuildingSelect, onInvalidBuildingSelect, onMapInfoChange, selectedRouteType]);

  useEffect(() => {
    if (containerRef.current === null) return;

    const capabilityError = webGlCapabilityError();
    if (capabilityError !== null) {
      const message = `${capabilityError} Chrome 또는 Edge의 하드웨어 가속이 활성화된 환경에서 열어 주세요.`;
      setRenderingError(message);
      onStatusChange({ kind: "error", message });
      return;
    }

    const cesiumToken = import.meta.env.VITE_CESIUM_ION_TOKEN;
    if (cesiumToken) Ion.defaultAccessToken = cesiumToken;
    const osmTileUrl =
      import.meta.env.VITE_OSM_TILE_URL || "https://tile.openstreetmap.org/";
    const buildingSource =
      import.meta.env.VITE_BUILDING_SOURCE || "molit-gis-building";

    let cancelled = false;
    let renderingFailed = false;
    const layerController = new AbortController();
    let layerStatus: Extract<RoadMapStatus, { kind: "ready" }> | null = null;
    const buildingRequests = new BuildingViewportRequests(32);
    let buildingTimer: ReturnType<typeof setTimeout> | undefined;
    const buildingDataSource = new GeoJsonDataSource("Cached buildings");
    const renderQuality = new MapRenderQuality();
    let simplifiedBuildings = false;
    // Visibility of outlines is an attribute; building meshes/heights/materials
    // stay static. Never distance-cull the building bodies during navigation.
    const buildingOutline = new CallbackProperty(
      () => !simplifiedBuildings && !buildingRequests.routeFocused, false,
    );
    const buildingTiles = new Map<string, Set<string>>();
    const buildingRecords = new Map<string, { entities: Entity[]; tiles: Set<string> }>();
    let buildingStatus: BuildingMapStatus = { kind: "loading", count: 0 };
    const osmImagery = new OpenStreetMapImageryProvider({
      url: osmTileUrl,
      maximumLevel: 19,
      credit: new Credit(
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>',
        true,
      ),
    });
    const baseLayer = new ImageryLayer(osmImagery);
    let viewer: Viewer;
    try {
      viewer = new Viewer(containerRef.current, {
        animation: false,
        baseLayer,
        baseLayerPicker: false,
        fullscreenButton: false,
        geocoder: false,
        homeButton: false,
        infoBox: false,
        navigationHelpButton: false,
        sceneModePicker: false,
        selectionIndicator: false,
        showRenderLoopErrors: false,
        timeline: false,
      });
      viewerRef.current = viewer;
      baseLayerRef.current = baseLayer;
      // Smooth ground-clamped route edges without raising their geometry.
      // Modest supersampling avoids an uncapped high-DPI GPU/memory cost.
      viewer.resolutionScale = REST_RESOLUTION;
      viewer.scene.postProcessStages.fxaa.enabled = true;
    } catch (error) {
      const detail = error instanceof Error ? error.message : "알 수 없는 오류";
      const message = `Cesium 초기화에 실패했습니다: ${detail}`;
      setRenderingError(message);
      onStatusChange({ kind: "error", message });
      return;
    }

    const removeQualityStart = viewer.camera.moveStart.addEventListener(() => renderQuality.start());
    const removeQualityEnd = viewer.camera.moveEnd.addEventListener(() => renderQuality.stop(performance.now()));
    // Canvas resizing clears its drawing buffer. Do it BEFORE scene updates and
    // rendering, so the same frame redraws the cleared buffer before presentation.
    // postRender resizing would erase the completed frame and flash black.
    // Preserve projection as well, to avoid false camera movement/load cancellation.
    const removeQualityRender = viewer.scene.preUpdate.addEventListener(() => {
      if (cancelled || renderingFailed) return;
      simplifiedBuildings = renderQuality.simplified(performance.now());
      setRenderResolution(viewer, simplifiedBuildings ? MOVING_RESOLUTION : REST_RESOLUTION);
    });

    const removeRenderErrorListener = viewer.scene.renderError.addEventListener(
      (_scene, error) => {
        renderingFailed = true;
        const detail = error instanceof Error ? error.message : String(error);
        const message = `WebGL 렌더링이 중단됐습니다: ${detail}`;
        setRenderingError(message);
        onStatusChange({ kind: "error", message });
      },
    );

    viewer.scene.backgroundColor = Color.fromCssColorString("#071a2b");
    viewer.scene.globe.baseColor = Color.fromCssColorString("#173944");
    // Government complex coordinates from the existing GIS building location.
    // Set the camera before loading layers; late responses must not reset user navigation.
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(INITIAL_MAP_VIEW.longitude, INITIAL_MAP_VIEW.latitude, INITIAL_MAP_VIEW.height),
      orientation: { heading: 0, pitch: -CesiumMath.PI_OVER_TWO, roll: 0 },
    });
    viewer.screenSpaceEventHandler.setInputAction(
      (movement: { position: Cartesian2 }) => {
        const pickedObjects = viewer.scene.drillPick(movement.position);
        if (buildingSelectionModeRef.current !== null) {
          for (const picked of pickedObjects) {
            const candidate = picked.id;
            if (!(candidate instanceof Entity)) continue;
            const building = buildingSelectionsRef.current.get(candidate);
            if (!building) continue;
            const coordinate = pickedWgs84Coordinate(viewer, movement.position);
            if (!coordinate) break;
            onBuildingSelectRef.current({ ...building, ...coordinate });
            return;
          }
          const message = buildingStatus.kind === "zoom-in"
            ? "건물을 선택하려면 지도를 더 확대해주세요."
            : buildingStatus.kind === "loading"
              ? "화면 주변 건물을 불러오는 중입니다. 잠시 후 선택해주세요."
              : buildingStatus.kind === "error"
                ? "건물을 불러오지 못했습니다. 지도를 조금 이동해 다시 시도해주세요."
                : undefined;
          onInvalidBuildingSelectRef.current(message);
          return;
        }
        let selectedInfo: MapInfoSelection | null = null;
        let selectedPriority = -1;
        const priorities: Record<MapInfoSelection["kind"], number> = {
          route_segment: 5,
          stairs: 4,
          bridge: 4,
          cctv: 4,
          streetlight: 3,
          building: 2,
        };
        for (const picked of pickedObjects) {
          const candidate = picked.id;
          if (!(candidate instanceof Entity)) continue;
          const info = mapInfoRef.current.get(candidate);
          if (!info) continue;
          const priority = info.kind === "route_segment"
            ? routePickPriority(info.routeType, selectedRouteTypeRef.current)
            : priorities[info.kind];
          if (priority <= selectedPriority) continue;
          selectedInfo = info;
          if (info.kind === "building") {
            const building = buildingSelectionsRef.current.get(candidate);
            const coordinate = pickedWgs84Coordinate(viewer, movement.position);
            if (building && coordinate) {
              selectedInfo = { ...info, buildingSelection: { ...building, ...coordinate } };
            }
          }
          selectedPriority = priority;
        }
        onMapInfoChangeRef.current(selectedInfo);
      },
      ScreenSpaceEventType.LEFT_CLICK,
    );

    async function loadGeoJson<
      T extends { type: "FeatureCollection"; metadata: FeatureCollectionMetadata },
    >(
      url: string,
      label: string,
      signal: AbortSignal = layerController.signal,
    ): Promise<T> {
      const response = await fetch(url, {
        headers: { Accept: "application/geo+json, application/json" },
        signal,
      });
      if (!response.ok) throw new Error(`${label} API가 HTTP ${response.status}를 반환했습니다.`);
      const collection = (await response.json()) as T;
      if (
        collection.type !== "FeatureCollection" ||
        collection.metadata.crs !== "EPSG:4326"
      ) {
        throw new Error(`${label} API의 GeoJSON 또는 좌표계가 올바르지 않습니다.`);
      }
      return collection;
    }

    function publishBuildingStatus(status: BuildingMapStatus) {
      if (cancelled || renderingFailed) return;
      buildingStatus = status;
      onBuildingStatusChange?.({ ...status, cachedCount: buildingRecords.size });
      if (layerStatus) {
        layerStatus = { ...layerStatus, buildingCount: status.count };
        onStatusChange(layerStatus);
      }
    }

    function releaseBuildings(source: GeoJsonDataSource) {
      if (!viewer.isDestroyed()) viewer.dataSources.remove(source, true);
      source.entities.removeAll();
    }

    function syncBuildingVisibility(): number {
      let count = 0;
      for (const record of buildingRecords.values()) {
        const visible = [...record.tiles].some((key) => buildingRequests.visible.has(key));
        if (visible) count++;
        for (const entity of record.entities) {
          if (entity.show !== visible) entity.show = visible;
        }
      }
      buildingDataSource.show = buildingRequests.visible.size > 0;
      viewer.scene.requestRender();
      return count;
    }

    function evictBuildingTiles() {
      for (const key of buildingRequests.evict()) {
        for (const id of buildingTiles.get(key) ?? []) {
          const record = buildingRecords.get(id);
          if (!record) continue;
          record.tiles.delete(key);
          if (record.tiles.size) continue;
          for (const entity of record.entities) {
            buildingDataSource.entities.remove(entity);
            buildingSelectionsRef.current.delete(entity);
            mapInfoRef.current.delete(entity);
          }
          buildingRecords.delete(id);
        }
        buildingTiles.delete(key);
      }
    }

    async function refreshVisibleBuildings() {
      if (cancelled || renderingFailed || viewer.isDestroyed()) return;
      const rectangle = viewer.camera.computeViewRectangle();
      const route = routeCandidatesRef.current.find((candidate) => candidate.route_type === selectedRouteTypeRef.current)
        ?? routeCandidatesRef.current[0];
      const decision = buildingRequests.plan(rectangle ? {
        west: CesiumMath.toDegrees(rectangle.west),
        south: CesiumMath.toDegrees(rectangle.south),
        east: CesiumMath.toDegrees(rectangle.east),
        north: CesiumMath.toDegrees(rectangle.north),
      } : null, route?.route.geometry.coordinates ?? []);
      if (decision.kind === "hidden") {
        syncBuildingVisibility();
        publishBuildingStatus({ kind: "zoom-in", count: 0 });
        return;
      }
      const visibleCount = syncBuildingVisibility();
      if (decision.kind === "reuse") {
        publishBuildingStatus({ kind: "ready", count: visibleCount });
        return;
      }
      if (decision.kind !== "load") return;
      const request = decision.request;
      const isCurrent = () => !cancelled && !renderingFailed &&
        !viewer.isDestroyed() && buildingRequests.isCurrent(request);
      publishBuildingStatus({ kind: "loading", count: visibleCount });
      let nextSource: GeoJsonDataSource | null = null;
      try {
        for (const batch of request.batches) {
          if (!isCurrent()) return;
          const buildings = await loadGeoJson<BuildingFeatureCollection>(
            `/api/buildings?source=${encodeURIComponent(buildingSource)}&bbox=${roadBboxQuery(batch.bounds)}`,
            "화면 주변 건물",
            request.controller.signal,
          );
          if (!isCurrent()) return;
          const tileIds = new Map(batch.tiles.map((tile) => [tile.key, new Set<string>()]));
          const uniqueFeatures = new Map<string, BuildingFeatureCollection["features"][number]>();
          for (const feature of buildings.features) {
            const bounds = geometryBounds(feature.geometry.coordinates);
            if (!bounds) continue;
            const id = String(feature.id);
            let included = false;
            for (const tile of batch.tiles) if (boundsIntersect(bounds, tile.bounds)) {
              tileIds.get(tile.key)!.add(id);
              included = true;
            }
            if (included && !buildingRecords.has(id)) uniqueFeatures.set(id, {
              ...feature, properties: { ...feature.properties, safealley_building_key: id },
            });
          }
          nextSource = await GeoJsonDataSource.load(
            { ...buildings, features: [...uniqueFeatures.values()] } as Parameters<typeof GeoJsonDataSource.load>[0],
            { clampToGround: false },
          );
          if (!isCurrent()) return;
          nextSource.name = `${buildingSource} visible buildings`;
          nextSource.show = false;
          const prepared = new Map<string, Entity[]>();
          const now = JulianDate.now();
          let styledCount = 0;
          for (const entity of nextSource.entities.values) {
            if (!entity.polygon) continue;
            const properties = entity.properties?.getValue(now) as Record<string, unknown> | undefined;
            const height = Number(properties?.height_m);
            const buildingName = String(properties?.building_name ?? "").trim() || null;
            const address = String(properties?.address ?? "").trim() || null;
            buildingSelectionsRef.current.set(entity, { displayName: buildingName ?? address, address });
            const key = String(properties?.safealley_building_key);
            if (!prepared.has(key)) prepared.set(key, []);
            prepared.get(key)!.push(entity);
            mapInfoRef.current.set(entity, {
              kind: "building",
              title: buildingName ?? address ?? "건물",
              rows: infoRows([
                ["건물명", properties?.building_name],
                ["주용도", properties?.main_use],
                ["건축면적", properties?.building_area == null ? null : `${properties.building_area}㎡`],
                ["연면적", properties?.total_floor_area == null ? null : `${properties.total_floor_area}㎡`],
                ["높이", properties?.height_m == null ? null : `${properties.height_m}m`],
                ["층수", properties?.floors],
                ["주소", properties?.address],
                ["출처", properties?.source],
              ]),
            });
            entity.name = buildingName ?? address ?? "건물";
            entity.description = new ConstantProperty(buildingDescription(properties ?? {}));
            entity.polygon.material = new ColorMaterialProperty(
              Color.fromCssColorString("#35b8c8").withAlpha(0.38),
            );
            entity.polygon.outline = buildingOutline;
            entity.polygon.outlineColor = new ConstantProperty(Color.fromCssColorString("#8be8f0").withAlpha(0.9));
            if (properties?.height_m != null && Number.isFinite(height) && height >= 0) {
              entity.polygon.height = new ConstantProperty(0);
              entity.polygon.extrudedHeight = new ConstantProperty(height);
            }
            // Let input/painting run between batches; abandon stale parses during camera movement.
            if (++styledCount % 200 === 0) {
              await new Promise<void>((resolve) => setTimeout(resolve, 0));
              if (!isCurrent()) return;
            }
          }
          if (!isCurrent()) return;
          if (!viewer.dataSources.contains(buildingDataSource)) await viewer.dataSources.add(buildingDataSource);
          if (!isCurrent()) return;
          if (!buildingRequests.commit(request, batch)) return;
          buildingDataSource.entities.suspendEvents();
          try {
            for (const [id, entities] of prepared) {
              for (const entity of entities) {
                nextSource.entities.remove(entity);
                buildingDataSource.entities.add(entity);
              }
              buildingRecords.set(id, { entities, tiles: new Set() });
            }
          } finally { buildingDataSource.entities.resumeEvents(); }
          for (const [key, ids] of tileIds) {
            buildingTiles.set(key, ids);
            for (const id of ids) buildingRecords.get(id)?.tiles.add(key);
          }
          releaseBuildings(nextSource);
          nextSource = null;
          evictBuildingTiles();
          publishBuildingStatus({ kind: "loading", count: syncBuildingVisibility() });
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
        }
        publishBuildingStatus({ kind: "ready", count: syncBuildingVisibility() });
      } catch (error) {
        if (!isCurrent()) return;
        buildingRequests.fail(request);
        publishBuildingStatus({ kind: "error", count: buildingStatus.count });
        console.warn("화면 주변 건물 조회 실패", error);
      } finally {
        if (nextSource) releaseBuildings(nextSource);
      }
    }

    function scheduleBuildingRefresh() {
      clearTimeout(buildingTimer);
      buildingTimer = setTimeout(() => void refreshVisibleBuildings(), 250);
    }
    refreshBuildingsRef.current = scheduleBuildingRefresh;
    const removeBuildingMoveStart = viewer.camera.moveStart.addEventListener(() => {
      clearTimeout(buildingTimer);
      buildingRequests.cancelPending();
    });
    const removeBuildingMoveEnd = viewer.camera.moveEnd.addEventListener(scheduleBuildingRefresh);
    const buildingResizeObserver = new ResizeObserver(scheduleBuildingRefresh);
    buildingResizeObserver.observe(containerRef.current);
    publishBuildingStatus({ kind: "loading", count: 0 });
    scheduleBuildingRefresh();

    // Collections persist, but only the padded viewport owns GPU objects.
    const streetlightPrimitives = viewer.scene.primitives.add(new BillboardCollection({ scene: viewer.scene })) as BillboardCollection;
    const cctvPrimitives = viewer.scene.primitives.add(new BillboardCollection({ scene: viewer.scene })) as BillboardCollection;
    const helpPointPrimitives = viewer.scene.primitives.add(new BillboardCollection({ scene: viewer.scene })) as BillboardCollection;
    streetlightPrimitivesRef.current = streetlightPrimitives;
    cctvPrimitivesRef.current = cctvPrimitives;
    helpPointPrimitivesRef.current = helpPointPrimitives;
    function addStreetlight(raw: FacilityFeature): () => void {
      const feature = raw as PointFeatureCollection["features"][number];
      const lightSize = mapLighting(nightModeRef.current).lightSize;
      const [longitude, latitude] = feature.geometry.coordinates;
          const streetlightEntity = new Entity({ name: "가로등" });
          mapInfoRef.current.set(streetlightEntity, {
            kind: "streetlight",
            title: String(feature.properties.name ?? "가로등"),
            rows: infoRows([
              ["관리번호", feature.properties.management_id ?? feature.id],
              ["주소", feature.properties.road_address ?? feature.properties.parcel_address],
              ["광원", feature.properties.light_type],
              ["표시 안내", "빛 번짐은 위치 강조용이며 실제 조도·점등 상태가 아닙니다."],
              ["출처", feature.properties.source_dataset ?? feature.properties.source],
            ]),
          });
          const marker = streetlightPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 2),
            image: STREETLIGHT_GLOW_IMAGE,
            width: lightSize,
            height: lightSize,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.3),
            // At district scale the density raster communicates the pattern with less clutter.
            distanceDisplayCondition: new DistanceDisplayCondition(0, 4500),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: streetlightEntity,
          });
      return () => { streetlightPrimitives.remove(marker); };
    }

    function addCctv(raw: FacilityFeature): () => void {
      const feature = raw as PointFeatureCollection["features"][number];

      const [longitude, latitude] = feature.geometry.coordinates;
          const coordinateQuality = String(feature.properties.coordinate_quality ?? "unknown");
          const recordCount = Number(feature.properties.location_record_count ?? 1);
          const description = pointDescription(
            coordinateQuality === "source_approximate" ? "CCTV 저정밀 위치 셀" : "방범 CCTV",
            feature.properties,
            [
              ["좌표 품질", coordinateQuality],
              ["이 좌표에 묶인 원본", recordCount],
              ["카메라 수", feature.properties.camera_count],
              ["설치 목적", feature.properties.purpose],
              ["촬영 방면", feature.properties.direction_info],
              ["설치 연월", feature.properties.installed_at],
              ["대표 주소", feature.properties.road_address ?? feature.properties.parcel_address],
              ["관리 기관", feature.properties.management_agency],
            ],
            "cctv",
          );
          mapInfoRef.current.set(description, {
            kind: "cctv",
            title: coordinateQuality === "source_approximate" ? "CCTV 저정밀 위치 셀" : "방범 CCTV",
            rows: infoRows([
              ["좌표 품질", coordinateQuality],
              ["이 좌표에 묶인 원본", recordCount],
              ["카메라 수", feature.properties.camera_count],
              ["설치 목적", feature.properties.purpose],
              ["촬영 방면", feature.properties.direction_info],
              ["설치 연월", feature.properties.installed_at],
              ["대표 주소", feature.properties.road_address ?? feature.properties.parcel_address],
              ["관리 기관", feature.properties.management_agency],
            ]),
          });
          if (coordinateQuality === "source_approximate") {
            const longitudeDigits = Number(feature.properties.longitude_precision_digits ?? 2);
            const latitudeDigits = Number(feature.properties.latitude_precision_digits ?? 3);
            const longitudeHalfCell = 0.5 * 10 ** -longitudeDigits;
            const latitudeHalfCell = 0.5 * 10 ** -latitudeDigits;
            const alpha = Math.min(0.42, 0.10 + Math.log2(Math.max(1, recordCount)) * 0.045);
            const cellId = `cctv-cell-${feature.id}`;
            viewer.entities.add({
              id: cellId,
              name: "CCTV 추정 위치 범위",
              properties: description.properties,
              show: facilityVisibilityRef.current.cctvs,
              rectangle: {
                coordinates: Rectangle.fromDegrees(
                  longitude - longitudeHalfCell,
                  latitude - latitudeHalfCell,
                  longitude + longitudeHalfCell,
                  latitude + latitudeHalfCell,
                ),
                material: Color.fromCssColorString("#38dce8").withAlpha(alpha),
                outline: true,
                outlineColor: Color.fromCssColorString("#b8f9ff").withAlpha(0.55),
              },
            });
            const cellEntity = viewer.entities.getById(cellId);
            if (cellEntity) {
              const info = mapInfoRef.current.get(description);
              if (info) mapInfoRef.current.set(cellEntity, info);
            }
            cctvCellEntityIdsRef.current.push(cellId);
          }
          const marker = cctvPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 3),
            image: CCTV_MARKER_IMAGE,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.45),
            distanceDisplayCondition: new DistanceDisplayCondition(0, 18000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: description,
          });
      return () => { cctvPrimitives.remove(marker);
        const cellId = `cctv-cell-${feature.id}`;
        viewer.entities.removeById(cellId);
        cctvCellEntityIdsRef.current = cctvCellEntityIdsRef.current.filter((id) => id !== cellId); };
    }

    function addHelpPoint(raw: FacilityFeature): () => void {
      const feature = raw as PointFeatureCollection["features"][number];

      const [longitude, latitude] = feature.geometry.coordinates;
          // Decorative icon only. Drill-picking continues to the building underneath.
          const marker = helpPointPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 4),
            image: helpPointMarkerImage(feature.properties.category),
            width: 32,
            height: 32,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.7),
            distanceDisplayCondition: new DistanceDisplayCondition(0, 18000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          });
      return () => { helpPointPrimitives.remove(marker); };
    }

    function addStair(raw: FacilityFeature): () => void {
      const feature = raw as RoadFeatureCollection["features"][number];

      if (feature.properties.is_steps !== true && feature.properties.highway !== "steps") return () => {};
          const position = stairMarkerPosition(feature.geometry.coordinates);
          if (!position) return () => {};
          const entity = viewer.entities.add({
            id: `stairs-${feature.id}`,
            show: facilityVisibilityRef.current.stairsAndBridges,
            name: "계단",
            position: Cartesian3.fromDegrees(...position),
            billboard: {
              image: STAIRS_MARKER_IMAGE,
              width: 24,
              height: 24,
              heightReference: HeightReference.CLAMP_TO_GROUND,
              pixelOffset: new Cartesian2(0, -12),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              distanceDisplayCondition: new DistanceDisplayCondition(0, 15000),
            },
          });
          stairBridgeEntityIdsRef.current.push(entity.id);
          mapInfoRef.current.set(entity, {
            kind: "stairs", title: "계단",
            rows: infoRows([
              ["도로명", feature.properties.name], ["계단 수", feature.properties.step_count],
              ["경사", feature.properties.incline], ["난간", feature.properties.handrail],
              ["경사로", feature.properties.ramp], ["출처", "OpenStreetMap · 현장 확인 필요"],
            ]),
          });
      return () => {
        viewer.entities.remove(entity);
        mapInfoRef.current.delete(entity);
        stairBridgeEntityIdsRef.current = stairBridgeEntityIdsRef.current.filter((id) => id !== entity.id); };
    }

    function addBridge(raw: FacilityFeature): () => void {
      const feature = raw as PointFeatureCollection["features"][number];

      const position = bridgeMarkerPosition(feature.geometry.coordinates);
          if (!position) return () => {};
          const p = feature.properties;
          const connected = p.routing_connected === true;
          const title = String(p.name ?? "보도육교");
          const entity = viewer.entities.add({
            id: `bridge-${feature.id}`,
            show: facilityVisibilityRef.current.stairsAndBridges,
            name: title,
            position: Cartesian3.fromDegrees(...position),
            billboard: {
              image: connected ? CONNECTED_BRIDGE_IMAGE : REFERENCE_BRIDGE_IMAGE,
              width: 24, height: 24,
              heightReference: HeightReference.CLAMP_TO_GROUND,
              // Offset from the nearby stair marker so both remain selectable.
              pixelOffset: new Cartesian2(24, -30),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              distanceDisplayCondition: new DistanceDisplayCondition(0, 15000),
            },
          });
          stairBridgeEntityIdsRef.current.push(entity.id);
          mapInfoRef.current.set(entity, {
            kind: "bridge", title,
            rows: infoRows([
              ["시설", "보도육교"], ["주소", p.address],
              ["경로망", connected ? "OSM 보행 구간 연결" : "참조 위치만 표시 · 경로망 미연결"],
              ["길이", p.bridge_length_m == null ? null : `${p.bridge_length_m}m`],
              ["폭", p.bridge_width_m == null ? null : `${p.bridge_width_m}m`],
              ["접근 시설(원본)", p.accessible_facility_type],
              ["부대시설(원본)", p.auxiliary_facility_type],
              ["이용 제한(원본)", p.use_restriction],
              ["기준일", p.reference_date], ["출처", p.source_dataset],
              ["위치 안내", "자료의 대표 위치 · 진입 지점이 아닐 수 있음"],
              ["주의", "현장 통행 가능 여부 및 엘리베이터 운행 미확인"],
            ]),
          });
      return () => {
        viewer.entities.remove(entity);
        mapInfoRef.current.delete(entity);
        stairBridgeEntityIdsRef.current = stairBridgeEntityIdsRef.current.filter((id) => id !== entity.id); };
    }


    function layer(url: string, enabled: () => boolean, create: (feature: FacilityFeature) => () => void) {
      return { url, enabled, create, cache: new FacilityViewportCache(),
        active: new Map<string, () => void>() };
    }
    const facilityLayers = [
      layer("/api/streetlights?source=michuhol-public-data", () => facilityVisibilityRef.current.streetlights, addStreetlight),
      layer("/api/cctvs?source=michuhol-cctv-ai-ready&safety_only=true", () => facilityVisibilityRef.current.cctvs, addCctv),
      layer("/api/help-points?source=ai-ready-help-points", () => facilityVisibilityRef.current.helpPoints, addHelpPoint),
      layer("/api/roads?source=osm&steps_only=true", () => facilityVisibilityRef.current.stairsAndBridges, addStair),
      layer("/api/pedestrian-bridges", () => facilityVisibilityRef.current.stairsAndBridges, addBridge),
    ];
    type FacilityLayer = typeof facilityLayers[number];
    let facilityTimer: ReturnType<typeof setTimeout> | undefined;
    let cameraMoving = false;
    let densityTimer: ReturnType<typeof setTimeout> | undefined;
    let densityStarted = false;
    let densityWaitStarted = 0;

    function syncFacilities(item: FacilityLayer) {
      if (cancelled || renderingFailed || viewer.isDestroyed()) return;
      const features = item.enabled() ? item.cache.features() : [];
      const ids = new Set(features.map((feature) => String(feature.id)));
      viewer.entities.suspendEvents();
      try {
        for (const [id, dispose] of item.active) if (!ids.has(id)) {
          dispose(); item.active.delete(id);
        }
        for (const feature of features) {
          const id = String(feature.id);
          if (!item.active.has(id)) item.active.set(id, item.create(feature));
        }
      } finally { viewer.entities.resumeEvents(); }
      if (layerStatus) {
        layerStatus = { ...layerStatus,
          streetlightCount: facilityLayers[0].active.size,
          cctvCount: facilityLayers[1].active.size,
          cctvRecordCount: facilityLayers[1].cache.features().reduce((sum, f) => sum + Number(f.properties.location_record_count ?? 1), 0),
          helpPointCount: facilityLayers[2].active.size };
        onStatusChange(layerStatus);
      }
      viewer.scene.requestRender();
    }

    async function refreshFacility(item: FacilityLayer, view: RoadViewport | null) {
      const request = item.cache.plan(item.enabled() ? view : null);
      syncFacilities(item);
      if (!request) return;
      try {
        for (const batch of request.batches) {
          const collection = await loadGeoJson<PointFeatureCollection | RoadFeatureCollection>(
            `${item.url}${item.url.includes("?") ? "&" : "?"}bbox=${roadBboxQuery(batch.bounds)}`,
            "화면 주변 시설", request.controller.signal);
          if (cancelled || renderingFailed || !item.cache.commit(request, batch, collection.features)) return;
          syncFacilities(item);
          // Yield between cached batches so map painting/input can run.
          await new Promise<void>((resolve) => setTimeout(resolve, 0));
        }
      } catch (error) {
        if (!request.controller.signal.aborted && !cancelled) {
          item.cache.fail(request);
          console.warn("화면 주변 시설 조회 실패", error);
        }
      } finally { scheduleDensity(); }
    }

    async function refreshFacilities() {
      facilityTimer = undefined;
      if (cancelled || renderingFailed || viewer.isDestroyed() || cameraMoving) return;
      const rectangle = viewer.camera.computeViewRectangle();
      const view = rectangle ? {
        west: CesiumMath.toDegrees(rectangle.west), south: CesiumMath.toDegrees(rectangle.south),
        east: CesiumMath.toDegrees(rectangle.east), north: CesiumMath.toDegrees(rectangle.north),
      } : null;
      // A slow facility API never blocks the other layers.
      await Promise.all(facilityLayers.map((item) => refreshFacility(item, view)));
      scheduleDensity();
    }

    function scheduleFacilities() {
      clearTimeout(facilityTimer);
      facilityTimer = setTimeout(() => void refreshFacilities(), 250);
      scheduleDensity();
    }

    // No client rasterization. Load immutable, precomputed tiles only after the first
    // visible objects have had a chance to paint. A slow optional layer has a bounded wait.
    function scheduleDensity() {
      if (cancelled || densityStarted || densityTimer !== undefined || cameraMoving ||
          !nightModeRef.current || !facilityVisibilityRef.current.streetlights) return;
      if (!densityWaitStarted) densityWaitStarted = performance.now();
      densityTimer = setTimeout(() => {
        densityTimer = undefined;
        if (cancelled || viewer.isDestroyed() || cameraMoving ||
            !nightModeRef.current || !facilityVisibilityRef.current.streetlights) return;
        if ((buildingStatus.kind === "loading" || facilityLayers.some((item) => item.cache.loading) || facilityTimer !== undefined)
            && performance.now() - densityWaitStarted < 2000) {
          scheduleDensity(); return;
        }
        void loadDensityTiles();
      }, 300);
    }

    async function loadDensityTiles() {
      if (densityStarted) return;
      densityStarted = true;
      try {
        const response = await fetch("/api/streetlight-heatmap/manifest", { signal: layerController.signal });
        if (!response.ok) throw new Error(`Heatmap manifest HTTP ${response.status}`);
        const manifest = await response.json() as { version: string; bounds: number[]; minzoom: number; maxzoom: number };
        if (cancelled || viewer.isDestroyed()) return;
        const [west, south, east, north] = manifest.bounds;
        const provider = new UrlTemplateImageryProvider({
          url: `/api/streetlight-heatmap/${manifest.version}/{z}/{x}/{y}.png`,
          rectangle: Rectangle.fromDegrees(west, south, east, north),
          minimumLevel: manifest.minzoom, maximumLevel: manifest.maxzoom,
          credit: new Credit("가로등 위치 기반 상대 밀도", false),
        });
        const densityLayer = new ImageryLayer(provider, {
          alpha: 0.85, show: nightModeRef.current && facilityVisibilityRef.current.streetlights,
        });
        viewer.imageryLayers.add(densityLayer);
        streetlightDensityLayerRef.current = densityLayer;
        viewer.scene.requestRender();
      } catch (error) {
        densityStarted = false;
        if (!cancelled) console.warn("사전 계산 가로등 히트맵 조회 실패", error);
      }
    }

    refreshFacilitiesRef.current = () => {
      for (const item of facilityLayers) {
        if (!item.enabled()) item.cache.cancel();
        syncFacilities(item);
      }
      scheduleFacilities();
    };
    const removeFacilityMoveStart = viewer.camera.moveStart.addEventListener(() => {
      cameraMoving = true;
      clearTimeout(facilityTimer); facilityTimer = undefined;
      clearTimeout(densityTimer); densityTimer = undefined;
      densityWaitStarted = 0;
      for (const item of facilityLayers) item.cache.cancel();
    });
    const removeFacilityMoveEnd = viewer.camera.moveEnd.addEventListener(() => {
      cameraMoving = false; scheduleFacilities();
    });
    const facilityResizeObserver = new ResizeObserver(scheduleFacilities);
    facilityResizeObserver.observe(containerRef.current);
    layerStatus = { kind: "ready", buildingCount: buildingStatus.count,
      streetlightCount: 0, cctvCount: 0, cctvRecordCount: 0, helpPointCount: 0 };
    onStatusChange(layerStatus);
    scheduleFacilities();
    return () => {
      cancelled = true;
      layerController.abort();
      clearTimeout(facilityTimer);
      clearTimeout(densityTimer);
      removeFacilityMoveStart();
      removeFacilityMoveEnd();
      facilityResizeObserver.disconnect();
      for (const item of facilityLayers) item.cache.clear();
      refreshFacilitiesRef.current = null;
      buildingRequests.clear();
      clearTimeout(buildingTimer);
      removeBuildingMoveStart();
      removeBuildingMoveEnd();
      buildingResizeObserver.disconnect();
      releaseBuildings(buildingDataSource);
      buildingTiles.clear();
      buildingRecords.clear();
      refreshBuildingsRef.current = null;
      removeRenderErrorListener();
      removeQualityStart();
      removeQualityEnd();
      removeQualityRender();
      viewerRef.current = null;
      baseLayerRef.current = null;
      streetlightDensityLayerRef.current = null;
      streetlightPrimitivesRef.current = null;
      cctvPrimitivesRef.current = null;
      helpPointPrimitivesRef.current = null;
      cctvCellEntityIdsRef.current = [];
      stairBridgeEntityIdsRef.current = [];
      buildingSelectionsRef.current = new WeakMap();
      mapInfoRef.current = new WeakMap();
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [onStatusChange, onBuildingStatusChange]);

  useEffect(() => {
    nightModeRef.current = nightMode;
    const viewer = viewerRef.current;
    const baseLayer = baseLayerRef.current;
    if (!viewer || viewer.isDestroyed() || !baseLayer) return;
    const lighting = mapLighting(nightMode);
    baseLayer.brightness = lighting.brightness;
    baseLayer.saturation = lighting.saturation;
    baseLayer.contrast = lighting.contrast;
    viewer.scene.backgroundColor = Color.fromCssColorString(lighting.background);
    viewer.scene.globe.baseColor = Color.fromCssColorString(lighting.ground);
    const lights = streetlightPrimitivesRef.current;
    if (lights) {
      for (let index = 0; index < lights.length; index++) {
        const light = lights.get(index);
        light.width = lighting.lightSize;
        light.height = lighting.lightSize;
      }
    }
    if (streetlightDensityLayerRef.current) {
      streetlightDensityLayerRef.current.show = nightMode && facilityVisibilityRef.current.streetlights;
    }
    viewer.scene.requestRender();
    refreshFacilitiesRef.current?.();
  }, [nightMode]);

  useEffect(() => {
    routeCandidatesRef.current = routeCandidates;
    refreshBuildingsRef.current?.();
  }, [routeCandidates, selectedRouteType]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null || viewer.isDestroyed()) return;

    onMapInfoChangeRef.current(null);
    for (const id of routeEntityIdsRef.current) viewer.entities.removeById(id);
    routeEntityIdsRef.current = [];

    const visibleCandidates = routeCandidates;

    for (const candidate of visibleCandidates) {
      const style = routeLineStyle(candidate.route_type, selectedRouteType, nightMode);
      const casingId = `recommended-route-${candidate.route_type}-casing`;
      const positions = candidate.route.geometry.coordinates.map(([longitude, latitude]) =>
        Cartesian3.fromDegrees(longitude, latitude),
      );
      // One continuous casing/line pair per route joins road boundaries cleanly.
      // Keep the original geometry and terrain clamping; no elevated overlay.
      if (positions.length >= 2) {
        const info: MapInfoSelection = {
          kind: "route_segment",
          routeType: candidate.route_type,
          title: "경로",
          rows: [],
        };
        const casing = viewer.entities.add({
          id: casingId,
          name: `${candidate.route_type} 경로 후보 외곽선`,
          polyline: {
            positions,
            width: style.casingWidth,
            material: Color.fromCssColorString(style.casingColor),
            clampToGround: true,
            classificationType: ClassificationType.TERRAIN,
            zIndex: style.zIndex - 1,
          },
        });
        const lineId = `recommended-route-${candidate.route_type}`;
        const line = viewer.entities.add({
          id: lineId,
          name: `${candidate.route_type} 경로 후보`,
          polyline: {
            positions,
            width: style.width,
            material: Color.fromCssColorString(style.color),
            clampToGround: true,
            classificationType: ClassificationType.TERRAIN,
            zIndex: style.zIndex,
          },
        });
        mapInfoRef.current.set(casing, info);
        mapInfoRef.current.set(line, info);
        routeEntityIdsRef.current.push(casingId, lineId);
      }
    }

    // One zebra-crossing icon at each selected crossing's path midpoint.
    selectedRouteGuidePoints(visibleCandidates, selectedRouteType).forEach((point, index) => {
      const id = `route-guide-point-${index}`;
      const entity = viewer.entities.add({
        id,
        position: Cartesian3.fromDegrees(point.longitude, point.latitude),
        billboard: {
          image: CROSSING_GUIDE_IMAGE,
          width: 24,
          height: 24,
          heightReference: HeightReference.CLAMP_TO_GROUND,
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
        },
      });
      mapInfoRef.current.set(entity, {
        kind: "route_segment", routeType: selectedRouteType!, title: "경로", rows: [],
      });
      routeEntityIdsRef.current.push(id);
    });

    const signature = routeGeometrySignature(visibleCandidates);
    if (visibleCandidates.length > 0 && signature !== lastRouteSignatureRef.current) {
      const coordinates = [
        ...visibleCandidates.flatMap((candidate) => candidate.route.geometry.coordinates),
        ...routeMarkerLocations(visibleCandidates, selectedRouteType, draftLocations).map(p => [p.longitude, p.latitude]),
      ];
      const selected = visibleCandidates.find(candidate => candidate.route_type === selectedRouteType) ?? visibleCandidates[0];
      flyToRouteFrame(viewer, coordinates,
        routeDetailOpen ? routeCameraHeading(selected.route.geometry.coordinates) : 0,
        routeDetailOpen ? -CesiumMath.toRadians(55) : -CesiumMath.PI_OVER_TWO);
      lastRouteSignatureRef.current = signature;
    } else if (visibleCandidates.length === 0) {
      lastRouteSignatureRef.current = "";
    }
    viewer.scene.requestRender();
  }, [draftLocations, routeCandidates, selectedRouteType, nightMode, routeDetailOpen]);

  useEffect(() => {
    // Only a mode change moves the camera; manual map movement stays untouched.
    if (routeDetailOpen === lastRouteDetailOpenRef.current) return;
    lastRouteDetailOpenRef.current = routeDetailOpen;
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.cancelFlight();
    const selected = routeCandidates.find((candidate) => candidate.route_type === selectedRouteType) ?? routeCandidates[0];
    const coordinates = selected?.route.geometry.coordinates;
    if (!coordinates || coordinates.length < 2) {
      // The same controls work before a search, around the current map center.
      const center = viewer.camera.pickEllipsoid(
        new Cartesian2(viewer.canvas.clientWidth / 2, viewer.canvas.clientHeight / 2),
        viewer.scene.globe.ellipsoid,
      );
      if (center) {
        const pitch = routeDetailOpen ? -CesiumMath.toRadians(55) : -CesiumMath.PI_OVER_TWO;
        const range = Math.max(280, Cartesian3.distance(viewer.camera.positionWC, center));
        viewer.camera.flyToBoundingSphere(new BoundingSphere(center, 1), {
          duration: 0.8, offset: new HeadingPitchRange(viewer.camera.heading, pitch, range),
        });
      }
      viewer.scene.requestRender();
      return;
    }
    const frameCoordinates = [...routeCandidates.flatMap(candidate => candidate.route.geometry.coordinates),
      ...routeMarkerLocations(routeCandidates, selectedRouteType, draftLocations).map(p => [p.longitude, p.latitude])];
    flyToRouteFrame(viewer, frameCoordinates,
      routeDetailOpen ? routeCameraHeading(coordinates) : 0,
      routeDetailOpen ? -CesiumMath.toRadians(55) : -CesiumMath.PI_OVER_TWO);
    viewer.scene.requestRender();
  }, [routeDetailOpen, routeCandidates, selectedRouteType, draftLocations]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed() || !focusBounds) return;
    const width = focusBounds.east - focusBounds.west;
    const height = focusBounds.north - focusBounds.south;
    const padding = Math.max(width, height, 0.0005) * 0.35 + 0.0002;
    viewer.camera.cancelFlight();
    viewer.camera.flyTo({
      destination: Rectangle.fromDegrees(
        focusBounds.west - padding,
        focusBounds.south - padding,
        focusBounds.east + padding,
        focusBounds.north + padding,
      ),
      orientation: { heading: 0, pitch: -CesiumMath.PI_OVER_TWO, roll: 0 },
      duration: 0.8,
    });
    viewer.scene.requestRender();
  }, [focusBounds]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const layer = routePinsRef.current;
    if (!viewer || viewer.isDestroyed() || !layer) return;
    const points = routeMarkerLocations(routeCandidates, selectedRouteType, draftLocations);
    const pins = (["origin", "destination"] as const).map(kind => {
      const point = points.find(p => p.kind === kind);
      return {
        element: layer.querySelector<HTMLElement>(`[data-pin="${kind}"]`)!,
        position: point ? Cartesian3.fromDegrees(point.longitude, point.latitude) : null,
        screen: new Cartesian2(),
        offsetX: 20,
        offsetY: 45.5,
      };
    });
    const labelPoint = selectedRouteLabelLocation(routeCandidates, selectedRouteType);
    const labelElement = layer.querySelector<HTMLElement>(".route-map-sign")!;
    pins.push({ element: labelElement,
      position: labelPoint ? Cartesian3.fromDegrees(labelPoint.longitude, labelPoint.latitude) : null,
      screen: new Cartesian2(), offsetX: labelElement.offsetWidth / 2, offsetY: labelElement.offsetHeight + 9 });
    const direction = new Cartesian3();
    const normal = new Cartesian3();
    const connectors = routeAccessConnectors(routeCandidates, selectedRouteType, draftLocations).map(link => ({
      element: layer.querySelector<SVGLineElement>(`[data-access-link="${link.kind}"]`)!,
      from: Cartesian3.fromDegrees(...link.from), to: Cartesian3.fromDegrees(...link.to),
      fromScreen: new Cartesian2(), toScreen: new Cartesian2(),
    }));
    function projectGround(position: Cartesian3, screen: Cartesian2) {
      const inFront = Cartesian3.dot(Cartesian3.subtract(position, viewer!.camera.positionWC, direction), viewer!.camera.directionWC) > 0;
      const aboveHorizon = Cartesian3.dot(viewer!.scene.globe.ellipsoid.geodeticSurfaceNormal(position, normal), direction) < 0;
      return inFront && aboveHorizon ? SceneTransforms.worldToWindowCoordinates(viewer!.scene, position, screen) : undefined;
    }
    const caps = routeEndCaps(routeCandidates, selectedRouteType).map((cap, index) => ({
      element: layer.querySelector<SVGGElement>(`[data-route-cap="${index}"]`)!,
      position: Cartesian3.fromDegrees(cap.position[0], cap.position[1]),
      neighbor: Cartesian3.fromDegrees(cap.neighbor[0], cap.neighbor[1]),
      screen: new Cartesian2(), neighborScreen: new Cartesian2(),
    }));
    const update = () => {
      if (viewer.isDestroyed()) return;
      const ratio = window.devicePixelRatio || 1;
      for (const link of connectors) {
        // Project ground coordinates, never raise the connector above the map.
        const from = projectGround(link.from, link.fromScreen);
        const to = projectGround(link.to, link.toScreen);
        link.element.style.visibility = from && to ? "visible" : "hidden";
        if (from && to) {
          link.element.setAttribute("x1", String(from.x)); link.element.setAttribute("y1", String(from.y));
          link.element.setAttribute("x2", String(to.x)); link.element.setAttribute("y2", String(to.y));
        }
      }
      for (const cap of caps) {
        const inFront = Cartesian3.dot(Cartesian3.subtract(cap.position, viewer.camera.positionWC, direction), viewer.camera.directionWC) > 0;
        const aboveHorizon = Cartesian3.dot(viewer.scene.globe.ellipsoid.geodeticSurfaceNormal(cap.position, normal), direction) < 0;
        const end = inFront && aboveHorizon ? SceneTransforms.worldToWindowCoordinates(viewer.scene, cap.position, cap.screen) : undefined;
        const inner = end ? SceneTransforms.worldToWindowCoordinates(viewer.scene, cap.neighbor, cap.neighborScreen) : undefined;
        const visible = end && inner && end.x >= -12 && end.x <= viewer.canvas.clientWidth + 12
          && end.y >= -12 && end.y <= viewer.canvas.clientHeight + 12;
        cap.element.style.visibility = visible ? "visible" : "hidden";
        if (visible && end && inner) {
          const angle = Math.atan2(end.y - inner.y, end.x - inner.x) * 180 / Math.PI;
          cap.element.setAttribute("transform", `translate(${end.x} ${end.y}) rotate(${angle})`);
        }
      }
      for (const pin of pins) {
        const inFront = pin.position && Cartesian3.dot(
          Cartesian3.subtract(pin.position, viewer.camera.positionWC, direction),
          viewer.camera.directionWC,
        ) > 0;
        const aboveHorizon = pin.position && Cartesian3.dot(
          viewer.scene.globe.ellipsoid.geodeticSurfaceNormal(pin.position, normal), direction,
        ) < 0;
        const point = pin.position && inFront && aboveHorizon
          ? SceneTransforms.worldToWindowCoordinates(viewer.scene, pin.position, pin.screen) : undefined;
        const visible = point && point.x >= -40 && point.x <= viewer.canvas.clientWidth + 40
          && point.y >= -50 && point.y <= viewer.canvas.clientHeight + 50;
        const visibility = visible ? "visible" : "hidden";
        if (pin.element.style.visibility !== visibility) pin.element.style.visibility = visibility;
        if (point && visible) {
          // Align each marker tip to a device pixel without enlarging the canvas.
          const x = Math.round((point.x - pin.offsetX) * ratio) / ratio;
          const y = Math.round((point.y - pin.offsetY) * ratio) / ratio;
          const transform = `translate(${x}px, ${y}px)`;
          if (pin.element.style.transform !== transform) pin.element.style.transform = transform;
        }
      }
    };
    const remove = viewer.scene.postRender.addEventListener(update);
    update();
    viewer.scene.requestRender();
    return () => {
      remove();
      for (const pin of pins) pin.element.style.visibility = "hidden";
      for (const cap of caps) cap.element.style.visibility = "hidden";
      for (const link of connectors) link.element.style.visibility = "hidden";
    };
  }, [draftLocations, routeCandidates, selectedRouteType]);

  function navigateMap(action: "home" | "in" | "out") {
    const viewer = viewerRef.current;
    if (!viewer || viewer.isDestroyed()) return;
    viewer.camera.cancelFlight();
    if (action === "home") {
      // Prevent the route-detail effect from overriding the explicit home action.
      lastRouteDetailOpenRef.current = false;
      onResetView();
      viewer.camera.flyTo({
        destination: Cartesian3.fromDegrees(INITIAL_MAP_VIEW.longitude, INITIAL_MAP_VIEW.latitude, INITIAL_MAP_VIEW.height),
        orientation: { heading: 0, pitch: -CesiumMath.PI_OVER_TWO, roll: 0 },
        duration: 0.6,
      });
    } else {
      const height = viewer.camera.positionCartographic.height;
      const target = zoomTargetHeight(height, action);
      if (target < height) viewer.camera.zoomIn(height - target);
      else viewer.camera.zoomOut(target - height);
    }
    viewer.scene.requestRender();
  }

  const signRoute = routeCandidates.find(candidate => candidate.route_type === selectedRouteType);
  const signMinutes = signRoute ? estimatedWalkingMinutes(signRoute.route.properties.total_distance_m) : null;

  return (
    <>
    <div
      ref={containerRef}
      className={`cesium-map ${buildingSelectionMode ? "cesium-map--selecting" : ""}`}
      data-map-mode={nightMode ? "night" : "day"}
      aria-label={nightMode ? "야간 보행 가능 도로 지도" : "보행 가능 도로 지도"}
    >
      {renderingError !== null && (
        <div className="map-rendering-error" role="alert">
          <strong>3D 지도를 표시할 수 없습니다</strong>
          <span>{renderingError}</span>
        </div>
      )}
    </div>
    <div ref={routePinsRef} className="route-pins" aria-hidden="true">
      <svg width="100%" height="100%" style={{ position: "absolute", inset: 0, overflow: "hidden" }}>
        {(["origin", "destination"] as const).map(kind => <line key={kind} data-access-link={kind}
          stroke={nightMode ? "#c3cad3" : "#919aa6"} strokeWidth="5" strokeDasharray="0 10" strokeLinecap="round"
          style={{ visibility: "hidden" }} />)}
        {routeEndCaps(routeCandidates, selectedRouteType).map((cap, index) => {
          const style = routeLineStyle(cap.routeType, selectedRouteType);
          return <g key={`${cap.routeType}-${index}`} data-route-cap={index} style={{ visibility: "hidden" }}>
            <path d={routeCapPath(style.casingWidth)} fill={style.casingColor}/>
            <path d={routeCapPath(style.width)} fill={style.color}/>
          </g>;
        })}
      </svg>
      <div className="route-map-sign" style={{ "--route-sign-outline": routeLineStyle(selectedRouteType ?? "custom", selectedRouteType, nightMode).casingColor } as CSSProperties}><span>{selectedRouteType === "shortest" ? "최단경로" : "맞춤경로"}</span><strong>{signMinutes === null ? "시간 미제공" : `${signMinutes}분`}</strong></div>
      <img data-pin="origin" src={routeMarkerImage("origin")} width="40" height="50" alt="" draggable={false} />
      <img data-pin="destination" src={routeMarkerImage("destination")} width="40" height="50" alt="" draggable={false} />
    </div>
    <nav className="map-navigation" aria-label="지도 확대 및 위치 이동">
      <button className="map-home" type="button" aria-label="현재 위치로 이동 · 정부인천지방합동청사" title="정부인천지방합동청사 초기 화면으로 이동" onClick={() => navigateMap("home")}>
        <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.7"><circle cx="12" cy="12" r="6.5"/><circle cx="12" cy="12" r="2" fill="currentColor" stroke="none"/><path d="M12 2v4m0 12v4M2 12h4m12 0h4"/></svg>
      </button>
      <div className="map-zoom">
        <button type="button" aria-label="지도 확대" title="확대" onClick={() => navigateMap("in")}><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 12h14M12 5v14"/></svg></button>
        <button type="button" aria-label="지도 축소" title="축소" onClick={() => navigateMap("out")}><svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="1.8"><path d="M5 12h14"/></svg></button>
      </div>
    </nav>
    </>
  );
}
