import {
  BillboardCollection,
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
  ImageryLayer,
  Ion,
  JulianDate,
  Math as CesiumMath,
  NearFarScalar,
  OpenStreetMapImageryProvider,
  Rectangle,
  ScreenSpaceEventType,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { useEffect, useRef, useState } from "react";
import type { RouteCandidate, RouteRoadSegment, RouteType } from "../types";
import { roadBboxQuery, roadRequestBounds, viewportIsInside, type RoadViewport } from "../roadViewport";
import { BuildingViewportRequests, boundsIntersect, geometryBounds } from "../buildingViewport";
import { STAIRS_MARKER_IMAGE, stairMarkerPosition } from "../stairsMarkers";
import { CONNECTED_BRIDGE_IMAGE, REFERENCE_BRIDGE_IMAGE, bridgeMarkerPosition } from "../bridgeMarkers";
import { mapLighting, STREETLIGHT_GLOW_IMAGE } from "../mapLighting";
import { CCTV_MARKER_IMAGE, helpPointMarkerImage } from "../facilityMarkers";

export type BuildingMapStatus = {
  kind: "loading" | "ready" | "zoom-in" | "error";
  count: number;
  cachedCount?: number;
};

export type RoadMapStatus =
  | { kind: "loading" }
  | {
      kind: "ready";
      roadCount: number;
      buildingCount: number;
      streetlightCount: number;
      cctvCount: number;
      cctvRecordCount: number;
      helpPointCount: number;
    }
  | { kind: "error"; message: string };

type CesiumRoadMapProps = {
  onStatusChange: (status: RoadMapStatus) => void;
  onBuildingStatusChange: (status: BuildingMapStatus) => void;
  routeCandidates: RouteCandidate[];
  selectedRouteType: RouteType | null;
  facilityVisibility: FacilityVisibility;
  buildingSelectionMode: BuildingSelectionMode;
  onBuildingSelect: (selection: BuildingMapSelection) => void;
  onInvalidBuildingSelect: (message?: string) => void;
  draftLocations: DraftMapLocation[];
  onMapInfoChange: (selection: MapInfoSelection | null) => void;
  nightMode: boolean;
};

export type FacilityVisibility = {
  streetlights: boolean;
  cctvs: boolean;
  helpPoints: boolean;
};

export type BuildingSelectionMode = "origin" | "destination" | null;

export type BuildingMapSelection = {
  displayName: string | null;
  address: string | null;
  latitude: number;
  longitude: number;
};

export type DraftMapLocation = {
  kind: "origin" | "destination";
  latitude: number;
  longitude: number;
};

export type MapInfoSelection = {
  kind: "building" | "streetlight" | "cctv" | "help_point" | "route_segment" | "stairs" | "bridge";
  title: string;
  rows: Array<{ label: string; value: string }>;
};

function infoRows(
  rows: Array<[string, unknown]>,
): Array<{ label: string; value: string }> {
  return rows
    .filter(([, value]) => value !== null && value !== undefined && value !== "")
    .map(([label, value]) => ({ label, value: String(value) }));
}

function routeSegmentInfo(segment: RouteRoadSegment): MapInfoSelection {
  return {
    kind: "route_segment",
    title: segment.name || "경로 구간",
    rows: infoRows([
      ["시설 접근성 지표(상대)", Number(segment.safety_score).toFixed(1)],
      ["도로 유형", segment.highway],
      ["거리", `${Math.round(segment.distance_m)}m`],
      ["계단", segment.is_steps ? "예" : "아니오"],
      ["가로등 위치 지표(상대)", Number(segment.streetlight_score).toFixed(1)],
      ["CCTV 위치 지표(상대)", Number(segment.cctv_score).toFixed(1)],
      ["도움시설 위치 지표(상대)", segment.help_point_score],
    ]),
  };
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

type StreetlightFeatureCollection = {
  type: "FeatureCollection";
  features: Array<{
    type: "Feature";
    id: number | string;
    geometry: { type: "Point"; coordinates: [number, number] };
    properties: Record<string, unknown>;
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
  layer: "cctv" | "help_point",
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

const routeColor = Color.fromCssColorString("#1261ff");

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

export function CesiumRoadMap({
  onStatusChange,
  onBuildingStatusChange,
  routeCandidates,
  selectedRouteType,
  facilityVisibility,
  buildingSelectionMode,
  onBuildingSelect,
  onInvalidBuildingSelect,
  draftLocations,
  onMapInfoChange,
  nightMode,
}: CesiumRoadMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const baseLayerRef = useRef<ImageryLayer | null>(null);
  const routeCandidatesRef = useRef(routeCandidates);
  const refreshRoadsRef = useRef<(() => void) | null>(null);
  const streetlightPrimitivesRef = useRef<BillboardCollection | null>(null);
  const nightModeRef = useRef(nightMode);
  const cctvPrimitivesRef = useRef<BillboardCollection | null>(null);
  const helpPointPrimitivesRef = useRef<BillboardCollection | null>(null);
  const cctvCellEntityIdsRef = useRef<string[]>([]);
  const buildingSelectionsRef = useRef<WeakMap<Entity, Omit<BuildingMapSelection, "latitude" | "longitude">>>(new WeakMap());
  const mapInfoRef = useRef<WeakMap<Entity, MapInfoSelection>>(new WeakMap());
  const routeEntityIdsRef = useRef<string[]>([]);
  const lastRouteSignatureRef = useRef("");
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
    if (cctvPrimitivesRef.current) cctvPrimitivesRef.current.show = facilityVisibility.cctvs;
    if (helpPointPrimitivesRef.current) {
      helpPointPrimitivesRef.current.show = facilityVisibility.helpPoints;
    }
    if (viewer && !viewer.isDestroyed()) {
      for (const id of cctvCellEntityIdsRef.current) {
        const entity = viewer.entities.getById(id);
        if (entity) entity.show = facilityVisibility.cctvs;
      }
      viewer.scene.requestRender();
    }
  }, [facilityVisibility]);

  useEffect(() => {
    buildingSelectionModeRef.current = buildingSelectionMode;
    onBuildingSelectRef.current = onBuildingSelect;
    onInvalidBuildingSelectRef.current = onInvalidBuildingSelect;
    onMapInfoChangeRef.current = onMapInfoChange;
  }, [buildingSelectionMode, onBuildingSelect, onInvalidBuildingSelect, onMapInfoChange]);

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
    let roadController: AbortController | null = null;
    let roadTimer: ReturnType<typeof setTimeout> | undefined;
    let roadRequestSerial = 0;
    let loadedRoadBounds: RoadViewport | null = null;
    let loadedRoadCount = 0;
    let pendingRoadBounds: RoadViewport | null = null;
    let layerStatus: Extract<RoadMapStatus, { kind: "ready" }> | null = null;
    const buildingRequests = new BuildingViewportRequests();
    let buildingTimer: ReturnType<typeof setTimeout> | undefined;
    const buildingDataSource = new GeoJsonDataSource("Cached buildings");
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
    } catch (error) {
      const detail = error instanceof Error ? error.message : "알 수 없는 오류";
      const message = `Cesium 초기화에 실패했습니다: ${detail}`;
      setRenderingError(message);
      onStatusChange({ kind: "error", message });
      return;
    }

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
    // Juan Station coordinates from the existing /api/places/resolve landmark.
    // Set the camera before loading layers; late responses must not reset user navigation.
    viewer.camera.setView({
      destination: Cartesian3.fromDegrees(126.6804, 37.4649, 1400),
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
          help_point: 4,
          streetlight: 3,
          building: 2,
        };
        for (const picked of pickedObjects) {
          const candidate = picked.id;
          if (!(candidate instanceof Entity)) continue;
          const info = mapInfoRef.current.get(candidate);
          if (!info || priorities[info.kind] <= selectedPriority) continue;
          selectedInfo = info;
          selectedPriority = priorities[info.kind];
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

    function publishRoadCount(count: number) {
      if (!layerStatus || cancelled || renderingFailed) return;
      layerStatus = { ...layerStatus, roadCount: count };
      onStatusChange(layerStatus);
    }

    async function refreshVisibleRoads() {
      if (cancelled || renderingFailed || !layerStatus || viewer.isDestroyed()) return;
      const rectangle = viewer.camera.computeViewRectangle();
      const view = rectangle ? {
        west: CesiumMath.toDegrees(rectangle.west),
        south: CesiumMath.toDegrees(rectangle.south),
        east: CesiumMath.toDegrees(rectangle.east),
        north: CesiumMath.toDegrees(rectangle.north),
      } : null;
      const bounds = view ? roadRequestBounds(view) : null;
      if (!bounds || routeCandidatesRef.current.length > 0) {
        ++roadRequestSerial;
        roadController?.abort();
        pendingRoadBounds = null;
        loadedRoadBounds = null;
        publishRoadCount(0);
        return;
      }
      if (view && pendingRoadBounds && viewportIsInside(view, pendingRoadBounds)) return;
      // Cancel an obsolete in-flight request even when returning to cached bounds.
      ++roadRequestSerial;
      roadController?.abort();
      pendingRoadBounds = null;
      if (view && loadedRoadBounds && viewportIsInside(view, loadedRoadBounds)) {
        publishRoadCount(loadedRoadCount);
        return;
      }
      const serial = roadRequestSerial;
      const controller = new AbortController();
      roadController = controller;
      pendingRoadBounds = bounds;
      publishRoadCount(0);
      try {
        const roads = await loadGeoJson<RoadFeatureCollection>(
          `/api/safety/roads?source=osm&bbox=${roadBboxQuery(bounds)}`,
          "화면 주변 안전도 도로",
          controller.signal,
        );
        if (cancelled || renderingFailed || serial !== roadRequestSerial) return;
        loadedRoadBounds = bounds;
        loadedRoadCount = roads.metadata.count;
        // Main hides the analysis layer: do not allocate hidden Cesium entities.
        publishRoadCount(roads.metadata.count);
      } catch (error) {
        if (cancelled || serial !== roadRequestSerial || controller.signal.aborted) return;
        loadedRoadBounds = null;
        // Optional analysis data must not disable route search or facility layers.
        console.warn("화면 주변 도로 조회 실패", error);
      } finally {
        if (serial === roadRequestSerial) pendingRoadBounds = null;
      }
    }

    function scheduleRoadRefresh() {
      clearTimeout(roadTimer);
      roadTimer = setTimeout(() => void refreshVisibleRoads(), 250);
    }
    refreshRoadsRef.current = scheduleRoadRefresh;
    const removeCameraListener = viewer.camera.moveEnd.addEventListener(scheduleRoadRefresh);

    function publishBuildingStatus(status: BuildingMapStatus) {
      if (cancelled || renderingFailed) return;
      buildingStatus = status;
      onBuildingStatusChange({ ...status, cachedCount: buildingRecords.size });
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
        for (const entity of record.entities) if (entity.show !== visible) entity.show = visible;
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
      const decision = buildingRequests.plan(rectangle ? {
        west: CesiumMath.toDegrees(rectangle.west),
        south: CesiumMath.toDegrees(rectangle.south),
        east: CesiumMath.toDegrees(rectangle.east),
        north: CesiumMath.toDegrees(rectangle.north),
      } : null);
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
            entity.polygon.outline = new ConstantProperty(true);
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
    const removeBuildingMoveStart = viewer.camera.moveStart.addEventListener(() => {
      clearTimeout(buildingTimer);
      buildingRequests.cancelPending();
    });
    const removeBuildingMoveEnd = viewer.camera.moveEnd.addEventListener(scheduleBuildingRefresh);
    const buildingResizeObserver = new ResizeObserver(scheduleBuildingRefresh);
    buildingResizeObserver.observe(containerRef.current);
    publishBuildingStatus({ kind: "loading", count: 0 });
    scheduleBuildingRefresh();

    async function loadMapLayers() {
      onStatusChange({ kind: "loading" });

      try {
        const streetlightRequest = loadGeoJson<StreetlightFeatureCollection>(
          "/api/streetlights?source=michuhol-public-data",
          "가로등",
        );
        const cctvRequest = loadGeoJson<PointFeatureCollection>(
          "/api/cctvs?source=michuhol-cctv-ai-ready&safety_only=true",
          "방범 CCTV",
        );
        const helpPointRequest = loadGeoJson<PointFeatureCollection>(
          "/api/help-points?source=ai-ready-help-points",
          "AI 안전시설",
        );
        const [streetlights, cctvs, helpPoints] = await Promise.all([
          streetlightRequest,
          cctvRequest,
          helpPointRequest,
        ]);

        if (cancelled || renderingFailed) return;
        const streetlightPrimitives = new BillboardCollection({ scene: viewer.scene });
        const lightSize = mapLighting(nightModeRef.current).lightSize;
        streetlightPrimitives.show = facilityVisibilityRef.current.streetlights;
        for (const feature of streetlights.features) {
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
          streetlightPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 2),
            image: STREETLIGHT_GLOW_IMAGE,
            width: lightSize,
            height: lightSize,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.3),
            distanceDisplayCondition: new DistanceDisplayCondition(0, 18000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: streetlightEntity,
          });
        }
        viewer.scene.primitives.add(streetlightPrimitives);
        streetlightPrimitivesRef.current = streetlightPrimitives;
        const cctvPrimitives = new BillboardCollection({ scene: viewer.scene });
        cctvPrimitives.show = facilityVisibilityRef.current.cctvs;
        for (const feature of cctvs.features) {
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
          cctvPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 3),
            image: CCTV_MARKER_IMAGE,
            width: 24,
            height: 24,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.45),
            distanceDisplayCondition: new DistanceDisplayCondition(0, 18000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: description,
          });
        }
        viewer.scene.primitives.add(cctvPrimitives);
        cctvPrimitivesRef.current = cctvPrimitives;

        const helpPointPrimitives = new BillboardCollection({ scene: viewer.scene });
        helpPointPrimitives.show = facilityVisibilityRef.current.helpPoints;
        for (const feature of helpPoints.features) {
          const [longitude, latitude] = feature.geometry.coordinates;
          const helpPointEntity = pointDescription(
            String(feature.properties.name ?? "안전·보건 시설"),
            feature.properties,
            [
              ["시설 유형", feature.properties.category],
              ["세부 유형", feature.properties.subtype],
              ["주소", feature.properties.address],
              ["전화", feature.properties.phone ?? feature.properties.emergency_phone],
              ["원천 기관", feature.properties.source_org],
              ["출처", feature.properties.source_dataset ?? feature.properties.source],
              ["기준일", feature.properties.reference_date],
            ],
            "help_point",
          );
          mapInfoRef.current.set(helpPointEntity, {
            kind: "help_point",
            title: String(feature.properties.name ?? "안전·보건 시설"),
            rows: infoRows([
              ["시설 유형", feature.properties.category],
              ["세부 유형", feature.properties.subtype],
              ["주소", feature.properties.address],
              ["전화", feature.properties.phone ?? feature.properties.emergency_phone],
              ["원천 기관", feature.properties.source_org],
              ["출처", feature.properties.source_dataset ?? feature.properties.source],
              ["기준일", feature.properties.reference_date],
            ]),
          });
          helpPointPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 4),
            image: helpPointMarkerImage(feature.properties.category),
            width: 32,
            height: 32,
            scaleByDistance: new NearFarScalar(250, 1, 12000, 0.7),
            distanceDisplayCondition: new DistanceDisplayCondition(0, 18000),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: helpPointEntity,
          });
        }
        viewer.scene.primitives.add(helpPointPrimitives);
        helpPointPrimitivesRef.current = helpPointPrimitives;
        if (renderingFailed) return;
        layerStatus = {
          kind: "ready",
          roadCount: 0,
          buildingCount: buildingStatus.count,
          streetlightCount: streetlights.metadata.count,
          cctvCount: cctvs.metadata.count,
          cctvRecordCount: cctvs.metadata.record_count ?? cctvs.metadata.count,
          helpPointCount: helpPoints.metadata.count,
        };
        onStatusChange(layerStatus);
        scheduleRoadRefresh();
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "알 수 없는 지도 오류";
        setRenderingError(message);
        onStatusChange({ kind: "error", message });
      }
    }

    async function loadStairMarkers() {
      try {
        const stairs = await loadGeoJson<RoadFeatureCollection>("/api/roads?source=osm&steps_only=true", "계단");
        if (cancelled || renderingFailed || viewer.isDestroyed()) return;
        for (const feature of stairs.features) {
          if (feature.properties.is_steps !== true && feature.properties.highway !== "steps") continue;
          const position = stairMarkerPosition(feature.geometry.coordinates);
          if (!position) continue;
          const entity = viewer.entities.add({
            id: `stairs-${feature.id}`,
            name: "계단",
            position: Cartesian3.fromDegrees(...position),
            billboard: {
              image: STAIRS_MARKER_IMAGE,
              width: 32,
              height: 32,
              heightReference: HeightReference.CLAMP_TO_GROUND,
              pixelOffset: new Cartesian2(0, -12),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              distanceDisplayCondition: new DistanceDisplayCondition(0, 15000),
            },
          });
          mapInfoRef.current.set(entity, {
            kind: "stairs", title: "계단",
            rows: infoRows([
              ["도로명", feature.properties.name], ["계단 수", feature.properties.step_count],
              ["경사", feature.properties.incline], ["난간", feature.properties.handrail],
              ["경사로", feature.properties.ramp], ["출처", "OpenStreetMap · 현장 확인 필요"],
            ]),
          });
        }
        viewer.scene.requestRender();
      } catch (error) {
        if (!cancelled) console.warn("계단 위치 조회 실패", error);
      }
    }

    async function loadBridgeMarkers() {
      try {
        const bridges = await loadGeoJson<PointFeatureCollection>("/api/pedestrian-bridges", "육교 위치");
        if (cancelled || renderingFailed || viewer.isDestroyed()) return;
        for (const feature of bridges.features) {
          const position = bridgeMarkerPosition(feature.geometry.coordinates);
          if (!position) continue;
          const p = feature.properties;
          const connected = p.routing_connected === true;
          const title = String(p.name ?? "보도육교");
          const entity = viewer.entities.add({
            id: `bridge-${feature.id}`,
            name: title,
            position: Cartesian3.fromDegrees(...position),
            billboard: {
              image: connected ? CONNECTED_BRIDGE_IMAGE : REFERENCE_BRIDGE_IMAGE,
              width: 34, height: 34,
              heightReference: HeightReference.CLAMP_TO_GROUND,
              // Offset from the nearby stair marker so both remain selectable.
              pixelOffset: new Cartesian2(24, -30),
              disableDepthTestDistance: Number.POSITIVE_INFINITY,
              distanceDisplayCondition: new DistanceDisplayCondition(0, 15000),
            },
          });
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
        }
        viewer.scene.requestRender();
      } catch (error) {
        if (!cancelled) console.warn("육교 위치 조회 실패", error);
      }
    }

    void loadMapLayers();
    void loadStairMarkers();
    void loadBridgeMarkers();

    return () => {
      cancelled = true;
      layerController.abort();
      roadController?.abort();
      buildingRequests.clear();
      clearTimeout(buildingTimer);
      removeBuildingMoveStart();
      removeBuildingMoveEnd();
      buildingResizeObserver.disconnect();
      releaseBuildings(buildingDataSource);
      buildingTiles.clear();
      buildingRecords.clear();
      clearTimeout(roadTimer);
      removeCameraListener();
      refreshRoadsRef.current = null;
      removeRenderErrorListener();
      viewerRef.current = null;
      baseLayerRef.current = null;
      streetlightPrimitivesRef.current = null;
      cctvPrimitivesRef.current = null;
      helpPointPrimitivesRef.current = null;
      cctvCellEntityIdsRef.current = [];
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
    viewer.scene.requestRender();
  }, [nightMode]);

  useEffect(() => {
    routeCandidatesRef.current = routeCandidates;
    refreshRoadsRef.current?.();
  }, [routeCandidates]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null || viewer.isDestroyed()) return;

    onMapInfoChangeRef.current(null);
    for (const id of routeEntityIdsRef.current) viewer.entities.removeById(id);
    routeEntityIdsRef.current = [];

    const visibleCandidates = selectedRouteType
      ? routeCandidates.filter((candidate) => candidate.route_type === selectedRouteType)
      : routeCandidates;

    for (const candidate of visibleCandidates) {
      const selected = candidate.route_type === selectedRouteType;
      const casingId = `recommended-route-${candidate.route_type}-casing`;
      const positions = candidate.route.geometry.coordinates.map(([longitude, latitude]) =>
        Cartesian3.fromDegrees(longitude, latitude),
      );
      const segments = candidate.route.properties.road_segments ?? [];
      if (segments.length > 0) {
        segments.forEach((segment, index) => {
          if (segment.coordinates.length < 2) return;
          const info = routeSegmentInfo(segment);
          const segmentCasingId = `${casingId}-${index}`;
          const segmentId = `recommended-route-${candidate.route_type}-segment-${index}`;
          const segmentPositions = segment.coordinates.map(([longitude, latitude]) =>
            Cartesian3.fromDegrees(longitude, latitude),
          );
          const segmentCasing = viewer.entities.add({
            id: segmentCasingId,
            name: `${segment.name || "경로 구간"} 외곽선`,
            polyline: {
              positions: segmentPositions,
              width: selected ? 10 : 8,
              material: Color.WHITE.withAlpha(0.95),
              clampToGround: true,
              classificationType: ClassificationType.TERRAIN,
              zIndex: 1,
            },
          });
          const segmentEntity = viewer.entities.add({
            id: segmentId,
            name: segment.name || "경로 구간",
            polyline: {
              positions: segmentPositions,
              width: selected ? 6 : 4,
              material: routeColor.withAlpha(selected ? 1 : 0.7),
              clampToGround: true,
              classificationType: ClassificationType.TERRAIN,
              zIndex: 2,
            },
          });
          mapInfoRef.current.set(segmentCasing, info);
          mapInfoRef.current.set(segmentEntity, info);
          routeEntityIdsRef.current.push(segmentCasingId, segmentId);
        });
      } else {
        viewer.entities.add({
          id: casingId,
          name: `${candidate.route_type} 경로 후보 외곽선`,
          polyline: {
            positions,
            width: selected ? 10 : 8,
            material: Color.WHITE.withAlpha(0.95),
            clampToGround: true,
            classificationType: ClassificationType.TERRAIN,
            zIndex: 1,
          },
        });
        const lineId = `recommended-route-${candidate.route_type}`;
        viewer.entities.add({
          id: lineId,
          name: `${candidate.route_type} 경로 후보`,
          polyline: {
            positions,
            width: selected ? 6 : 4,
            material: routeColor.withAlpha(selected ? 1 : 0.7),
            clampToGround: true,
            classificationType: ClassificationType.TERRAIN,
            zIndex: 2,
          },
        });
        routeEntityIdsRef.current.push(casingId, lineId);
      }
    }

    const selectedCandidate = visibleCandidates[0];
    const selectedCoordinates = selectedCandidate?.route.geometry.coordinates ?? [];
    if (selectedCoordinates.length > 0) {
      const markers = [
        { id: "selected-route-start", name: "출발지", coordinate: selectedCoordinates[0], color: "#4fe0ae" },
        { id: "selected-route-end", name: "도착지", coordinate: selectedCoordinates[selectedCoordinates.length - 1], color: "#ff6b7d" },
      ];
      for (const marker of markers) {
        viewer.entities.add({
          id: marker.id,
          name: marker.name,
          position: Cartesian3.fromDegrees(marker.coordinate[0], marker.coordinate[1]),
          point: {
            heightReference: HeightReference.CLAMP_TO_GROUND,
            pixelSize: 13,
            color: Color.fromCssColorString(marker.color),
            outlineColor: Color.WHITE,
            outlineWidth: 3,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        routeEntityIdsRef.current.push(marker.id);
      }
    } else {
      for (const location of draftLocations) {
        const markerId = `draft-route-${location.kind}`;
        viewer.entities.add({
          id: markerId,
          name: location.kind === "origin" ? "선택한 출발지" : "선택한 도착지",
          position: Cartesian3.fromDegrees(location.longitude, location.latitude),
          point: {
            heightReference: HeightReference.CLAMP_TO_GROUND,
            pixelSize: 13,
            color: Color.fromCssColorString(
              location.kind === "origin" ? "#4fe0ae" : "#ff6b7d",
            ),
            outlineColor: Color.WHITE,
            outlineWidth: 3,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        routeEntityIdsRef.current.push(markerId);
      }
    }

    const signature = visibleCandidates
      .map((candidate) => `${candidate.route_type}:${candidate.route.geometry.coordinates.length}`)
      .join("|");
    if (visibleCandidates.length > 0 && signature !== lastRouteSignatureRef.current) {
      const coordinates = visibleCandidates.flatMap((candidate) => candidate.route.geometry.coordinates);
      const longitudes = coordinates.map(([longitude]) => longitude);
      const latitudes = coordinates.map(([, latitude]) => latitude);
      const padding = 0.002;
      viewer.camera.flyTo({
        duration: 0.8,
        destination: Rectangle.fromDegrees(
          Math.min(...longitudes) - padding,
          Math.min(...latitudes) - padding,
          Math.max(...longitudes) + padding,
          Math.max(...latitudes) + padding,
        ),
      });
      lastRouteSignatureRef.current = signature;
    } else if (visibleCandidates.length === 0) {
      lastRouteSignatureRef.current = "";
    }
  }, [draftLocations, routeCandidates, selectedRouteType]);

  return (
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
  );
}
