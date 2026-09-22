import {
  Cartesian3,
  Cartesian2,
  Cartographic,
  ClassificationType,
  Color,
  ColorMaterialProperty,
  ConstantProperty,
  Credit,
  Entity,
  GeoJsonDataSource,
  HeightReference,
  ImageryLayer,
  Ion,
  JulianDate,
  Math as CesiumMath,
  OpenStreetMapImageryProvider,
  PointPrimitiveCollection,
  Rectangle,
  ScreenSpaceEventType,
  Viewer,
} from "cesium";
import "cesium/Build/Cesium/Widgets/widgets.css";
import { useEffect, useRef, useState } from "react";
import type { RouteCandidate, RouteRoadSegment, RouteType } from "../types";

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
  routeCandidates: RouteCandidate[];
  selectedRouteType: RouteType | null;
  facilityVisibility: FacilityVisibility;
  buildingSelectionMode: BuildingSelectionMode;
  onBuildingSelect: (selection: BuildingMapSelection) => void;
  onInvalidBuildingSelect: () => void;
  draftLocations: DraftMapLocation[];
  onMapInfoChange: (selection: MapInfoSelection | null) => void;
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
  kind: "building" | "streetlight" | "cctv" | "help_point" | "route_segment";
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
      ["안전도", Number(segment.safety_score).toFixed(1)],
      ["도로 유형", segment.highway],
      ["거리", `${Math.round(segment.distance_m)}m`],
      ["계단", segment.is_steps ? "예" : "아니오"],
      ["가로등 점수", Number(segment.streetlight_score).toFixed(1)],
      ["CCTV 점수", Number(segment.cctv_score).toFixed(1)],
      ["안전시설 점수", segment.help_point_score],
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
  routeCandidates,
  selectedRouteType,
  facilityVisibility,
  buildingSelectionMode,
  onBuildingSelect,
  onInvalidBuildingSelect,
  draftLocations,
  onMapInfoChange,
}: CesiumRoadMapProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const viewerRef = useRef<Viewer | null>(null);
  const roadDataSourceRef = useRef<GeoJsonDataSource | null>(null);
  const streetlightPrimitivesRef = useRef<PointPrimitiveCollection | null>(null);
  const cctvPrimitivesRef = useRef<PointPrimitiveCollection | null>(null);
  const helpPointPrimitivesRef = useRef<PointPrimitiveCollection | null>(null);
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
    const osmImagery = new OpenStreetMapImageryProvider({
      url: osmTileUrl,
      maximumLevel: 19,
      credit: new Credit(
        '© <a href="https://www.openstreetmap.org/copyright" target="_blank">OpenStreetMap contributors</a>',
        true,
      ),
    });
    let viewer: Viewer;
    try {
      viewer = new Viewer(containerRef.current, {
        animation: false,
        baseLayer: new ImageryLayer(osmImagery),
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
          onInvalidBuildingSelectRef.current();
          return;
        }
        let selectedInfo: MapInfoSelection | null = null;
        let selectedPriority = -1;
        const priorities: Record<MapInfoSelection["kind"], number> = {
          route_segment: 5,
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
    ): Promise<T> {
      const response = await fetch(url, {
        headers: { Accept: "application/geo+json, application/json" },
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
        const [roads, buildings, streetlights, cctvs, helpPoints] = await Promise.all([
          loadGeoJson<RoadFeatureCollection>("/api/safety/roads?source=osm", "안전도 도로"),
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
          const buildingName = String(properties?.building_name ?? "").trim() || null;
          const address = String(properties?.address ?? "").trim() || null;
          buildingSelectionsRef.current.set(entity, {
            displayName: buildingName ?? address,
            address,
          });
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

        const roadDataSource = await GeoJsonDataSource.load(
          roads as Parameters<typeof GeoJsonDataSource.load>[0],
          { clampToGround: false },
        );
        roadDataSource.name = "Walkable road segments";
        // Keep the full safety analysis layer available for a future layer control,
        // but do not confuse it with the route selected by the user.
        roadDataSource.show = false;
        roadDataSourceRef.current = roadDataSource;

        for (const entity of roadDataSource.entities.values) {
          if (!entity.polyline) continue;

          const properties = entity.properties?.getValue(now) as
            | Record<string, unknown>
            | undefined;
          const safetyScore = Number(properties?.safety_score ?? 50);
          entity.name = String(properties?.name ?? "종합 안전도 분석 구간");
          entity.description = new ConstantProperty(roadDescription(properties ?? {}));
          entity.polyline.width = new ConstantProperty(5);
          entity.polyline.material = new ColorMaterialProperty(
            colorForSafetyScore(safetyScore),
          );
        }

        if (cancelled || renderingFailed) return;
        await viewer.dataSources.add(buildingDataSource);
        await viewer.dataSources.add(roadDataSource);
        const streetlightPrimitives = new PointPrimitiveCollection();
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
              ["출처", feature.properties.source_dataset ?? feature.properties.source],
            ]),
          });
          streetlightPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 2),
            pixelSize: 3,
            color: Color.fromCssColorString("#fff4a8").withAlpha(0.72),
            outlineWidth: 0,
            id: streetlightEntity,
          });
        }
        viewer.scene.primitives.add(streetlightPrimitives);
        streetlightPrimitivesRef.current = streetlightPrimitives;
        const cctvPrimitives = new PointPrimitiveCollection();
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
            continue;
          }
          cctvPrimitives.add({
            position: Cartesian3.fromDegrees(longitude, latitude, 3),
            pixelSize: 6,
            color: Color.fromCssColorString("#38dce8").withAlpha(0.9),
            outlineColor: Color.fromCssColorString("#d8fcff"),
            outlineWidth: 1,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: description,
          });
        }
        viewer.scene.primitives.add(cctvPrimitives);
        cctvPrimitivesRef.current = cctvPrimitives;

        const helpPointPrimitives = new PointPrimitiveCollection();
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
            pixelSize: 9,
            color: colorForHelpPoint(feature.properties.category).withAlpha(0.94),
            outlineColor: Color.WHITE,
            outlineWidth: 1,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            id: helpPointEntity,
          });
        }
        viewer.scene.primitives.add(helpPointPrimitives);
        helpPointPrimitivesRef.current = helpPointPrimitives;
        if (renderingFailed) return;
        if (roads.features.length > 0) {
          const coordinates = roads.features.flatMap(
            (feature) => feature.geometry.coordinates,
          );
          const longitudes = coordinates.map(([longitude]) => longitude);
          const latitudes = coordinates.map(([, latitude]) => latitude);
          const padding = 0.0015;

          viewer.camera.flyTo({
            duration: 0,
            destination: Rectangle.fromDegrees(
              Math.min(...longitudes) - padding,
              Math.min(...latitudes) - padding,
              Math.max(...longitudes) + padding,
              Math.max(...latitudes) + padding,
            ),
          });
        }
        onStatusChange({
          kind: "ready",
          roadCount: roads.metadata.count,
          buildingCount: buildings.metadata.count,
          streetlightCount: streetlights.metadata.count,
          cctvCount: cctvs.metadata.count,
          cctvRecordCount: cctvs.metadata.record_count ?? cctvs.metadata.count,
          helpPointCount: helpPoints.metadata.count,
        });
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
      removeRenderErrorListener();
      viewerRef.current = null;
      roadDataSourceRef.current = null;
      streetlightPrimitivesRef.current = null;
      cctvPrimitivesRef.current = null;
      helpPointPrimitivesRef.current = null;
      cctvCellEntityIdsRef.current = [];
      buildingSelectionsRef.current = new WeakMap();
      mapInfoRef.current = new WeakMap();
      if (!viewer.isDestroyed()) viewer.destroy();
    };
  }, [onStatusChange]);

  useEffect(() => {
    const viewer = viewerRef.current;
    if (viewer === null || viewer.isDestroyed()) return;

    if (roadDataSourceRef.current !== null) roadDataSourceRef.current.show = false;

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
      aria-label="보행 가능 도로 지도"
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
