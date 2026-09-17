import { useCallback, useEffect, useState } from "react";

import {
  CesiumRoadMap,
  type RoadMapStatus,
} from "./components/CesiumRoadMap";

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

function App() {
  const [health, setHealth] = useState<HealthState>({ kind: "loading" });
  const [roads, setRoads] = useState<RoadMapStatus>({ kind: "loading" });

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

  return (
    <main className="app-shell">
      <CesiumRoadMap onStatusChange={handleRoadStatus} />

      <aside className="map-panel">
        <p className="eyebrow">MICHUHOL-GU · COMPOSITE SAFETY</p>
        <h1>SafeAlley</h1>
        <p className="description">
          OpenStreetMap 위에 PostGIS 도로와 건물 공간정보를 표시합니다.
          도로 색상은 가로등·방범 CCTV·안전시설 접근성을 합산한 상대 안전지표입니다.
        </p>

        <div className="status-row">
          <span className={`indicator ${systemReady ? "indicator--ready" : ""}`} />
          <span>{systemReady ? "전체 데이터 흐름 정상" : "데이터 흐름 확인 중"}</span>
        </div>

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
              {roads.kind === "ready" && `${roads.cctvCount}개 point · EPSG:4326`}
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

        <div className="facility-legend" aria-label="시설 레이어 범례">
          <span><i className="facility-cctv" />방범 CCTV</span>
          <span><i className="facility-police" />경찰</span>
          <span><i className="facility-fire" />소방</span>
          <span><i className="facility-medical" />응급의료</span>
        </div>

        <p className="disclaimer">
          이 점수는 가로등·CCTV·안전시설 거리와 밀도의 상대 순위를 합산한 분석지표이며,
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
