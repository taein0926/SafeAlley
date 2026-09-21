import {
  Cartesian3,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  Credit,
  Entity,
  GeoJsonDataSource,
  ImageryLayer,
  Ion,
  JulianDate,
  Math as CesiumMath,
  OpenStreetMapImageryProvider,
  PointPrimitiveCollection,
  Rectangle,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { useEffect, useRef, useState } from "react";
import {
  roadBboxQuery,
  roadRequestBounds,
  viewportIsInside,
  type RoadViewport,
} from "../roadViewport";
import type { RouteCandidate, RouteType } from "../types";

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
  nightMode: boolean;
  routeCandidates: RouteCandidate[];
  selectedRouteType: RouteType | null;
};

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

function colorForSafetyScore(score: number): Color {
  if (score >= 80) return Color.fromCssColorString("#28e0a3");
  if (score >= 60) return Color.fromCssColorString("#8edb57");
  if (score >= 40) return Color.fromCssColorString("#ffd166");
  if (score >= 20) return Color.fromCssColorString("#ff9f43");
  return Color.fromCssColorString("#ff5c70");
}

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

function roadDescription(properties: Record<string, unknown>): string {
  const rows = [
    ["종합 안전도", properties.safety_score],
    ["가로등 점수", properties.streetlight_score],
    ["방범 CCTV 점수", properties.cctv_score],
    ["안전시설 점수", properties.help_point_score],
    ["가장 가까운 가로등", `${properties.nearest_light_distance_m ?? "-"}m`],
    ["주변 가로등 수", properties.nearby_light_count],
    ["가로등 밀도", properties.light_density],
    ["어두운 구간 대리값", `${properties.dark_gap_proxy_m ?? "-"}m`],
    ["가장 가까운 CCTV", `${properties.nearest_cctv_distance_m ?? "-"}m`],
    ["주변 CCTV 수", properties.nearby_cctv_count],
    ["CCTV 밀도", properties.cctv_density],
    ["CCTV 공백 대리값", `${properties.cctv_gap_proxy_m ?? "-"}m`],
    ["가장 가까운 안전시설", `${properties.nearest_help_point_distance_m ?? "-"}m`],
    ["최근접 안전시설 유형", properties.nearest_help_point_category],
    ["도로명", properties.name],
  ];
  return `<table class="cesium-infoBox-defaultTable"><tbody>${rows
    .map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`)
    .join("")}</tbody></table>`;
}

function pointDescription(
  title: string,
  properties: Record<string, unknown>,
  rows: Array<[string, unknown]>,
): Entity {
  const description = `<table class="cesium-infoBox-defaultTable"><tbody>${rows
    .map(([label, value]) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value)}</td></tr>`)
    .join("")}</tbody></table>`;
  return new Entity({ name: title, description: new ConstantProperty(description), properties });
}

function colorForHelpPoint(category: unknown): Color {
  if (category === "police") return Color.fromCssColorString("#4b8dff");
  if (category === "fire_station") return Color.fromCssColorString("#ff5b5b");
  if (category === "emergency_medical") return Color.fromCssColorString("#46df88");
  return Color.fromCssColorString("#c78cff");
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

const routeColors: Record<RouteType, Color> = {
  shortest: Color.fromCssColorString("#1261ff"),
  balanced: Color.fromCssColorString("#ffe600"),
  safe: Color.fromCssColorString("#ff2bd6"),
};

export function CesiumRoadMap({
  onStatusChange,
  nightMode,
  routeCandidates,
  selectedRouteType,
}: CesiumRoadMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const baseLayerRef = useRef<ImageryLayer | null>(null);
  const roadDataSourceRef = useRef<GeoJsonDataSource | null>(null);
  const routeCandidatesRef = useRef(routeCandidates);
  routeCandidatesRef.current = routeCandidates;
  const routeEntityIdsRef = useRef<string[]>([]);
  const lastRouteSignatureRef = useRef("");
  const [renderingError, setRenderingError] = useState<string | null>(null);

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
    const showStreetlights = import.meta.env.VITE_SHOW_STREETLIGHTS !== "false";
    const showCctvs = import.meta.env.VITE_SHOW_CCTVS !== "false";
    const showHelpPoints = import.meta.env.VITE_SHOW_HELP_POINTS !== "false";

    let cancelled = false;
    let renderingFailed = false;
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
        infoBox: true,
        navigationHelpButton: false,
        sceneModePicker: false,
        selectionIndicator: true,
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

    async function loadGeoJson<
      T extends { type: "FeatureCollection"; metadata: FeatureCollectionMetadata },
    >(
      url: string,
      label: string,
      signal?: AbortSignal,
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

    let roadRequestController: AbortController | null = null;
    let roadLoadTimer: ReturnType<typeof setTimeout> | null = null;
    let roadLoadSerial = 0;
    let loadedRoadBounds: RoadViewport | null = null;
    let pendingRoadBounds: RoadViewport | null = null;
    let layerCounts: Omit<Extract<RoadMapStatus, { kind: "ready" }>, "kind" | "roadCount"> | null = null;

    function publishRoadCount(count: number) {
      if (layerCounts !== null && !cancelled) {
        onStatusChange({ kind: "ready", ...layerCounts, roadCount: count });
      }
    }

    function removeRoadLayer() {
      if (roadDataSourceRef.current !== null && !viewer.isDestroyed()) {
        viewer.dataSources.remove(roadDataSourceRef.current);
        roadDataSourceRef.current = null;
        viewer.scene.requestRender();
      }
      loadedRoadBounds = null;
      publishRoadCount(0);
    }

    async function refreshVisibleRoads() {
      if (cancelled || renderingFailed || viewer.isDestroyed()) return;
      const rectangle = viewer.camera.computeViewRectangle(viewer.scene.globe.ellipsoid);
      if (rectangle === undefined) return;
      const view: RoadViewport = {
        west: CesiumMath.toDegrees(rectangle.west),
        south: CesiumMath.toDegrees(rectangle.south),
        east: CesiumMath.toDegrees(rectangle.east),
        north: CesiumMath.toDegrees(rectangle.north),
      };
      const bounds = roadRequestBounds(view);
      if (bounds === null || routeCandidatesRef.current.length > 0) {
        roadLoadSerial += 1;
        roadRequestController?.abort();
        roadRequestController = null;
        pendingRoadBounds = null;
        removeRoadLayer();
        return;
      }
      if (loadedRoadBounds !== null && viewportIsInside(view, loadedRoadBounds)) return;
      if (pendingRoadBounds !== null && viewportIsInside(view, pendingRoadBounds)) return;

      const serial = ++roadLoadSerial;
      roadRequestController?.abort();
      const controller = new AbortController();
      roadRequestController = controller;
      pendingRoadBounds = bounds;
      try {
        const roads = await loadGeoJson<RoadFeatureCollection>(
          "/api/safety/roads?source=osm&bbox=" + roadBboxQuery(bounds),
          "안전도 도로",
          controller.signal,
        );
        if (cancelled || renderingFailed || serial !== roadLoadSerial) return;
        const roadDataSource = await GeoJsonDataSource.load(
          roads as Parameters<typeof GeoJsonDataSource.load>[0],
          { clampToGround: false },
        );
        if (cancelled || renderingFailed || serial !== roadLoadSerial) {
          return;
        }
        roadDataSource.name = "Visible walkable road segments";
        const now = JulianDate.now();
        for (const entity of roadDataSource.entities.values) {
          if (!entity.polyline) continue;
          const properties = entity.properties?.getValue(now) as Record<string, unknown> | undefined;
          entity.name = String(properties?.name ?? "종합 안전도 분석 구간");
          entity.description = new ConstantProperty(roadDescription(properties ?? {}));
          entity.polyline.width = new ConstantProperty(5);
          entity.polyline.material = new ColorMaterialProperty(
            colorForSafetyScore(Number(properties?.safety_score ?? 50)),
          );
        }
        await viewer.dataSources.add(roadDataSource);
        if (cancelled || serial !== roadLoadSerial) {
          viewer.dataSources.remove(roadDataSource);
          return;
        }
        if (roadDataSourceRef.current !== null) {
          viewer.dataSources.remove(roadDataSourceRef.current);
        }
        roadDataSourceRef.current = roadDataSource;
        loadedRoadBounds = bounds;
        publishRoadCount(roads.metadata.count);
        viewer.scene.requestRender();
      } catch (error) {
        if (controller.signal.aborted || cancelled) return;
        const message = error instanceof Error ? error.message : "알 수 없는 도로 로딩 오류";
        setRenderingError(message);
        onStatusChange({ kind: "error", message });
      } finally {
        if (serial === roadLoadSerial) pendingRoadBounds = null;
      }
    }

    function scheduleRoadRefresh() {
      if (roadLoadTimer !== null) clearTimeout(roadLoadTimer);
      roadLoadTimer = setTimeout(() => void refreshVisibleRoads(), 250);
    }

    const removeMoveEndListener = viewer.camera.moveEnd.addEventListener(scheduleRoadRefresh);

    async function loadMapLayers() {
      onStatusChange({ kind: "loading" });

      try {
        const streetlightRequest = showStreetlights
          ? loadGeoJson<StreetlightFeatureCollection>(
              "/api/streetlights?source=michuhol-public-data",
              "가로등",
            )
          : Promise.resolve<StreetlightFeatureCollection>({
              type: "FeatureCollection",
              features: [],
              metadata: { count: 0, crs: "EPSG:4326" },
            });
        const emptyPoints: PointFeatureCollection = {
          type: "FeatureCollection",
          features: [],
          metadata: { count: 0, crs: "EPSG:4326" },
        };
        const cctvRequest = showCctvs
          ? loadGeoJson<PointFeatureCollection>(
              "/api/cctvs?source=mois-cctv-standard&safety_only=true",
              "방범 CCTV",
            )
          : Promise.resolve(emptyPoints);
        const helpPointRequest = showHelpPoints
          ? loadGeoJson<PointFeatureCollection>(
              "/api/help-points?source=official-help-points",
              "AI 안전시설",
            )
          : Promise.resolve(emptyPoints);
        const [buildings, streetlights, cctvs, helpPoints] = await Promise.all([
          loadGeoJson<BuildingFeatureCollection>(
            `/api/buildings?source=${encodeURIComponent(buildingSource)}`,
            "건물",
          ),
          streetlightRequest,
          cctvRequest,
          helpPointRequest,
        ]);

        const buildingDataSource = await GeoJsonDataSource.load(
          buildings as Parameters<typeof GeoJsonDataSource.load>[0],
          { clampToGround: false },
        );
        buildingDataSource.name = `${buildingSource} buildings`;
        const now = JulianDate.now();
        for (const entity of buildingDataSource.entities.values) {
          if (!entity.polygon) continue;
          const properties = entity.properties?.getValue(now) as
            | Record<string, unknown>
            | undefined;
          const height = Number(properties?.height_m);
          entity.name = String(properties?.building_name ?? properties?.building_id ?? "건물");
          entity.description = new ConstantProperty(
            buildingDescription(properties ?? {}),
          );
          entity.polygon.material = new ColorMaterialProperty(
            Color.fromCssColorString("#35b8c8").withAlpha(0.38),
          );
          entity.polygon.outline = new ConstantProperty(true);
          entity.polygon.outlineColor = new ConstantProperty(
            Color.fromCssColorString("#8be8f0").withAlpha(0.9),
          );
          if (properties?.height_m != null && Number.isFinite(height) && height >= 0) {
            entity.polygon.height = new ConstantProperty(0);
            entity.polygon.extrudedHeight = new ConstantProperty(height);
          }
        }

        if (cancelled || renderingFailed) return;
        await viewer.dataSources.add(buildingDataSource);
        const streetlightPrimitives = new PointPrimitiveCollection();
        for (const feature of streetlights.features) {
          const [longitude, latitude] = feature.geometry.coordinates;
          streetlightPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 2),
            pixelSize: 3,
            color: Color.fromCssColorString("#fff4a8").withAlpha(0.72),
            outlineWidth: 0,
          });
        }
        viewer.scene.primitives.add(streetlightPrimitives);
        const cctvPrimitives = new PointPrimitiveCollection();
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
              ["대표 주소", feature.properties.road_address ?? feature.properties.parcel_address],
              ["관리 기관", feature.properties.management_agency],
            ],
          );
          if (coordinateQuality === "source_approximate") {
            const longitudeDigits = Number(feature.properties.longitude_precision_digits ?? 2);
            const latitudeDigits = Number(feature.properties.latitude_precision_digits ?? 3);
            const longitudeHalfCell = 0.5 * 10 ** -longitudeDigits;
            const latitudeHalfCell = 0.5 * 10 ** -latitudeDigits;
            const alpha = Math.min(0.42, 0.10 + Math.log2(Math.max(1, recordCount)) * 0.045);
            viewer.entities.add({
              id: `cctv-cell-${feature.id}`,
              name: "CCTV 추정 위치 범위",
              description: new ConstantProperty(description),
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
            continue;
          }
          cctvPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 3),
            pixelSize: 6,
            color: Color.fromCssColorString("#38dce8").withAlpha(0.9),
            outlineColor: Color.fromCssColorString("#d8fcff"),
            outlineWidth: 1,
            id: description,
          });
        }
        viewer.scene.primitives.add(cctvPrimitives);

        const helpPointPrimitives = new PointPrimitiveCollection();
        for (const feature of helpPoints.features) {
          const [longitude, latitude] = feature.geometry.coordinates;
          helpPointPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 4),
            pixelSize: 9,
            color: colorForHelpPoint(feature.properties.category).withAlpha(0.94),
            outlineColor: Color.WHITE,
            outlineWidth: 1,
            id: pointDescription(
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
            ),
          });
        }
        viewer.scene.primitives.add(helpPointPrimitives);
        if (renderingFailed) return;
        // Start near the demo's Juan Station; load only visible detailed road segments.
        viewer.camera.flyTo({
          duration: 0,
          destination: Rectangle.fromDegrees(126.676, 37.459, 126.685, 37.467),
        });
        layerCounts = {
          buildingCount: buildings.metadata.count,
          streetlightCount: streetlights.metadata.count,
          cctvCount: cctvs.metadata.count,
          cctvRecordCount: cctvs.metadata.record_count ?? cctvs.metadata.count,
          helpPointCount: helpPoints.metadata.count,
        };
        publishRoadCount(0);
        scheduleRoadRefresh();
      } catch (error) {
        if (cancelled) return;
        const message = error instanceof Error ? error.message : "알 수 없는 지도 오류";
        setRenderingError(message);
        onStatusChange({ kind: "error", message });
      }
    }

    void loadMapLayers();

    return () => {
      cancelled = true;
      roadLoadSerial += 1;
      roadRequestController?.abort();
      if (roadLoadTimer !== null) clearTimeout(roadLoadTimer);
      removeMoveEndListener();
      removeRenderErrorListener();
      viewerRef.current = null;
      roadDataSourceRef.current = null;
      baseLayerRef.current = null;
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [onStatusChange]);

  useEffect(() => {
    const viewer = viewerRef.current;
    const baseLayer = baseLayerRef.current;
    if (viewer === null || viewer.isDestroyed() || baseLayer === null) return;

    // Dim only the basemap; route lines and safety markers stay readable.
    baseLayer.brightness = nightMode ? 0.42 : 1;
    baseLayer.saturation = nightMode ? 0.7 : 1;
    viewer.scene.backgroundColor = Color.fromCssColorString(
      nightMode ? "#030a15" : "#071a2b",
    );
    viewer.scene.globe.baseColor = Color.fromCssColorString(
      nightMode ? "#091925" : "#173944",
    );
    viewer.scene.requestRender();
  }, [nightMode]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null || viewer.isDestroyed()) return;

    if (roadDataSourceRef.current !== null) {
      roadDataSourceRef.current.show = routeCandidates.length === 0;
    }

    for (const id of routeEntityIdsRef.current) viewer.entities.removeById(id);
    routeEntityIdsRef.current = [];

    const visibleCandidates = selectedRouteType
      ? routeCandidates.filter((candidate) => candidate.route_type === selectedRouteType)
      : [];

    for (const candidate of visibleCandidates) {
      const selected = candidate.route_type === selectedRouteType;
      const casingId = `recommended-route-${candidate.route_type}-casing`;
      const lineId = `recommended-route-${candidate.route_type}`;
      const positions = candidate.route.geometry.coordinates.map(([longitude, latitude]) =>
        Cartesian3.fromDegrees(longitude, latitude, selected ? 12 : 9),
      );
      viewer.entities.add({
        id: casingId,
        name: `${candidate.route_type} 경로 후보 외곽선`,
        polyline: {
          positions,
          width: selected ? 8 : 5,
          material: selected
            ? Color.WHITE.withAlpha(0.98)
            : Color.fromCssColorString("#07111d").withAlpha(0.9),
          clampToGround: false,
        },
      });
      viewer.entities.add({
        id: lineId,
        name: `${candidate.route_type} 경로 후보`,
        polyline: {
          positions,
          width: selected ? 5 : 3,
          material: routeColors[candidate.route_type].withAlpha(selected ? 1 : 0.92),
          clampToGround: false,
        },
      });
      routeEntityIdsRef.current.push(casingId, lineId);
    }

    const signature = visibleCandidates
      .map((candidate) => [
        candidate.route_type,
        ...candidate.route.geometry.coordinates.flat(),
      ].join(":"))
      .join("|");
    if (visibleCandidates.length === 0) lastRouteSignatureRef.current = "";
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
    }
  }, [routeCandidates, selectedRouteType]);

  return (
    <div
      ref={containerRef}
      className="cesium-map"
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
