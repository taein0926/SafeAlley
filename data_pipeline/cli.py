import argparse
import json
import os
from datetime import datetime
from pathlib import Path

from analysis.streetlight_safety import run_streetlight_safety_analysis
from analysis.safety_components import run_safety_component_analysis
from analysis.road_quality import audit_road_network
from collectors.cctvs import collect_cctvs
from collectors.weather import KST, fetch_forecast, fetch_solar, forecast_grid
from loaders.weather import save_forecasts, save_solar
from collectors.osm import collect_osm_roads, collect_osm_streetlights
from loaders.buildings import load_buildings
from loaders.postgis import load_road_segments
from loaders.streetlights import load_streetlights
from loaders.cctvs import load_cctv_geojson
from loaders.help_points import load_help_points
from loaders.elevation import load_road_slopes
from loaders.public_crosswalks import load_public_crosswalks
from loaders.crosswalk_links import link_public_crosswalks
from loaders.pedestrian_references import load_pedestrian_references
from preprocess.buildings import preprocess_buildings
from preprocess.osm_roads import preprocess_osm_roads
from preprocess.elevation import calculate_road_slopes
from preprocess.public_crosswalks import preprocess_incheon_crosswalks
from preprocess.public_streetlights import preprocess_incheon_streetlights
from preprocess.roads import read_road_features
from preprocess.streetlights import preprocess_osm_streetlights, preprocess_streetlights


RAW_OSM_PATH = Path(__file__).parent / "raw" / "osm" / "michuhol_roads.json"
PROCESSED_ELEVATION_PATH = (
    Path(__file__).parent / "processed" / "elevation" / "road_slopes.json"
)
RAW_PUBLIC_CROSSWALKS_PATH = (
    Path(__file__).parent / "raw" / "public_pedestrian"
    / "incheon_road_facilities_3d_poi_20221031.zip"
)
PROCESSED_PUBLIC_CROSSWALKS_PATH = (
    Path(__file__).parent / "processed" / "public_pedestrian" / "crosswalks.geojson"
)
PROCESSED_PUBLIC_STREETLIGHTS_PATH = (
    Path(__file__).parent / "processed" / "public_pedestrian" / "streetlights.geojson"
)
PROCESSED_OSM_PATH = (
    Path(__file__).parent / "processed" / "osm" / "road_segments.geojson"
)
PROCESSED_BUILDINGS_PATH = (
    Path(__file__).parent / "processed" / "buildings" / "buildings.geojson"
)
RAW_STREETLIGHTS_PATH = (
    Path(__file__).parent
    / "raw"
    / "streetlights"
    / "인천광역시 미추홀구_가로등_20240806.csv"
)
PROCESSED_STREETLIGHTS_PATH = (
    Path(__file__).parent / "processed" / "streetlights" / "streetlights.geojson"
)
RAW_CCTVS_PATH = (
    Path(__file__).parent / "raw" / "cctvs" / "cctv_michuhol_ai_ready.geojson"
)
LEGACY_RAW_CCTVS_PATH = (
    Path(__file__).parent / "raw" / "cctvs" / "michuhol_cctvs.json"
)
RAW_NATIONAL_CCTVS_PATH = (
    Path(__file__).parent / "raw" / "cctvs" / "national_cctv.csv"
)
RAW_OSM_STREETLIGHTS_PATH = (
    Path(__file__).parent / "raw" / "streetlights" / "osm_streetlights.json"
)
PROCESSED_CCTVS_PATH = (
    Path(__file__).parent / "processed" / "cctvs" / "michuhol_cctvs.json"
)
RAW_HELP_POINTS_PATH = (
    Path(__file__).parent
    / "raw"
    / "help_points"
    / "help_points_michuhol_routing_ready.geojson"
)


def collect_weather(*, include_forecast: bool = True, include_solar: bool = True) -> None:
    now = datetime.now(KST)
    kma_key = os.environ.get("KMA_SERVICE_KEY", "").strip()
    kasi_key = os.environ.get("KASI_SERVICE_KEY", "").strip()
    failed = False
    # Independent writes: one source's outage must not block the other source.
    try:
        if include_forecast and not kma_key:
            raise ValueError("missing KMA key")
        nx_value, ny_value = os.environ.get("KMA_GRID_NX", "").strip(), os.environ.get("KMA_GRID_NY", "").strip()
        if include_forecast and bool(nx_value) != bool(ny_value):
            raise ValueError("both KMA grid coordinates are required")
        if include_forecast:
            nx, ny = (int(nx_value), int(ny_value)) if nx_value else forecast_grid()
            if not (1 <= nx <= 149 and 1 <= ny <= 253):
                raise ValueError("invalid grid")
            print(f"KMA: stored {save_forecasts(fetch_forecast(kma_key, nx, ny, now))} forecast hours (grid {nx},{ny})")
    except Exception:
        # Never echo exceptions containing secret-bearing URLs or DB DSNs.
        print("Forecast collection failed; check approval, grid, connectivity and migration; cache preserved")
        failed = True
    try:
        if include_solar and not kasi_key:
            raise ValueError("missing KASI key")
        if include_solar:
            save_solar(fetch_solar(kasi_key, now.date(), os.environ.get("KASI_LOCATION", "인천")))
            print("KASI: stored today's official sunrise/sunset")
    except Exception:
        print("Solar collection failed; check approval, location, connectivity and migration; cache preserved")
        failed = True
    if failed:
        raise SystemExit(1)


def collect_osm() -> None:
    element_count = collect_osm_roads(RAW_OSM_PATH)
    print(f"Collected {element_count} raw OSM elements into {RAW_OSM_PATH}")


def preprocess_osm() -> None:
    stats = preprocess_osm_roads(RAW_OSM_PATH, PROCESSED_OSM_PATH)
    print(
        f"Processed {stats['walkable_ways']} walkable OSM ways into "
        f"{stats['road_segments']} graph edges at {PROCESSED_OSM_PATH}"
    )


def load_osm() -> None:
    features = read_road_features(PROCESSED_OSM_PATH)
    loaded_count = load_road_segments(features, replace_source="osm")
    print(f"Replaced OSM roads with {loaded_count} PostGIS road segments")


def run_osm() -> None:
    collect_osm()
    preprocess_osm()
    load_osm()


def preprocess_building_file(arguments: argparse.Namespace) -> None:
    if arguments.input is None:
        raise SystemExit("preprocess-buildings requires --input")
    stats = preprocess_buildings(
        Path(arguments.input),
        PROCESSED_BUILDINGS_PATH,
        source=arguments.source or "imap",
        source_dataset=(
            arguments.source_dataset
            or "User-provided official building dataset"
        ),
        boundary_path=Path(arguments.boundary) if arguments.boundary else None,
        district_field=arguments.district_field,
        district_value=arguments.district_value,
        assume_michuhol_only=arguments.assume_michuhol_only,
        source_crs_override=arguments.source_crs,
        boundary_crs_override=arguments.boundary_crs,
        field_map_path=Path(arguments.field_map) if arguments.field_map else None,
        source_encoding=arguments.source_encoding,
    )
    print(
        f"Filtered {stats['input_features']} source features into "
        f"{stats['output_buildings']} Michuhol-gu buildings at "
        f"{PROCESSED_BUILDINGS_PATH}"
    )


def load_building_file(arguments: argparse.Namespace) -> None:
    source = arguments.source or "imap"
    loaded_count = load_buildings(
        PROCESSED_BUILDINGS_PATH,
        replace_source=source,
    )
    print(f"Replaced {source} buildings with {loaded_count} PostGIS rows")


def run_buildings(arguments: argparse.Namespace) -> None:
    preprocess_building_file(arguments)
    load_building_file(arguments)


def preprocess_streetlight_file(arguments: argparse.Namespace) -> None:
    input_path = Path(arguments.input) if arguments.input else RAW_STREETLIGHTS_PATH
    source = arguments.source or "michuhol-public-data"
    stats = preprocess_streetlights(
        input_path,
        PROCESSED_STREETLIGHTS_PATH,
        source=source,
        source_dataset=(
            arguments.source_dataset
            or "인천광역시 미추홀구_가로등_20240806"
        ),
        encoding=arguments.source_encoding or "cp949",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def load_streetlight_file(arguments: argparse.Namespace) -> None:
    source = arguments.source or "michuhol-public-data"
    count = load_streetlights(PROCESSED_STREETLIGHTS_PATH, replace_source=source)
    print(f"Replaced {source} streetlights with {count} PostGIS rows")


def analyze_streetlights(arguments: argparse.Namespace) -> None:
    source = arguments.source or "michuhol-public-data"
    stats = run_streetlight_safety_analysis(
        streetlight_source=source,
        road_source=arguments.road_source,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))


def run_streetlight_pipeline(arguments: argparse.Namespace) -> None:
    preprocess_streetlight_file(arguments)
    load_streetlight_file(arguments)
    analyze_streetlights(arguments)


def run_osm_streetlight_pipeline(arguments: argparse.Namespace) -> None:
    count = collect_osm_streetlights(RAW_OSM_STREETLIGHTS_PATH)
    print(f"Collected {count} OSM street_lamp nodes")
    stats = preprocess_osm_streetlights(
        RAW_OSM_STREETLIGHTS_PATH,
        PROCESSED_STREETLIGHTS_PATH,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    loaded = load_streetlights(
        PROCESSED_STREETLIGHTS_PATH,
        replace_source="osm-street-lamp",
    )
    print(f"Replaced osm-street-lamp streetlights with {loaded} PostGIS rows")
    arguments.source = "osm-street-lamp"
    analyze_streetlights(arguments)


def collect_cctv_file() -> None:
    print(json.dumps(collect_cctvs(LEGACY_RAW_CCTVS_PATH), ensure_ascii=False, indent=2))


def _safety_cctv_purposes() -> set[str]:
    return {
        value.strip()
        for value in os.getenv("SAFETY_CCTV_PURPOSES", "").split(",")
        if value.strip()
    }


def preprocess_cctv_file() -> None:
    from preprocess.cctvs import preprocess_cctvs

    stats = preprocess_cctvs(
        LEGACY_RAW_CCTVS_PATH,
        # Legacy API flow writes a normalized JSON file and is not the
        # operational local-GeoJSON path used by load-cctvs.
        PROCESSED_CCTVS_PATH,
        safety_purposes=_safety_cctv_purposes(),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def load_cctv_file() -> None:
    stats = load_cctv_geojson(
        RAW_CCTVS_PATH, replace_source="michuhol-cctv-ai-ready"
    )
    for item in stats["excluded_features"]:
        print(f"Excluded CCTV {item['identifier']}: {item['reason']}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def run_cctv_pipeline() -> None:
    load_cctv_file()


def run_cctv_csv_pipeline(arguments: argparse.Namespace) -> None:
    from preprocess.cctvs import preprocess_cctv_csv

    purposes = _safety_cctv_purposes() or {"생활방범", "어린이보호"}
    stats = preprocess_cctv_csv(
        Path(arguments.input) if arguments.input else RAW_NATIONAL_CCTVS_PATH,
        PROCESSED_CCTVS_PATH,
        district_name=arguments.district_name,
        safety_purposes=purposes,
        source=arguments.cctv_source,
        encoding=arguments.source_encoding or "cp949",
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    count = load_cctvs(
        PROCESSED_CCTVS_PATH,
        replace_source=arguments.cctv_source,
    )
    print(f"Replaced {arguments.cctv_source} CCTV records with {count} PostGIS rows")


def load_help_point_file(arguments: argparse.Namespace) -> None:
    path = Path(arguments.input) if arguments.input else RAW_HELP_POINTS_PATH
    stats = load_help_points(path, replace_source=arguments.help_point_source)
    for item in stats["excluded_features"]:
        print(f"Excluded help point {item['identifier']}: {item['reason']}")
    for warning in stats["warnings"]:
        print(f"WARNING: {warning}")
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def analyze_safety_components(arguments: argparse.Namespace) -> None:
    stats = run_safety_component_analysis(
        cctv_source=arguments.cctv_source,
        help_point_source=arguments.help_point_source,
        road_source=arguments.road_source,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2, default=str))


def run_safety_components(arguments: argparse.Namespace) -> None:
    load_cctv_file()
    load_help_point_file(arguments)
    analyze_safety_components(arguments)


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeAlley data pipeline")
    parser.add_argument(
        "command",
        choices=[
            "collect-weather",
            "weather-worker",
            "collect-osm",
            "preprocess-osm",
            "load-osm",
            "run-osm",
            "preprocess-buildings",
            "load-buildings",
            "run-buildings",
            "preprocess-streetlights",
            "load-streetlights",
            "analyze-streetlights",
            "run-streetlight-safety",
            "run-osm-streetlights",
            "collect-cctvs",
            "preprocess-cctvs",
            "load-cctvs",
            "run-cctvs",
            "run-cctv-csv",
            "load-help-points",
            "analyze-safety-components",
            "run-safety-components",
            "calculate-road-slopes",
            "load-road-slopes",
            "audit-road-network",
            "preprocess-public-crosswalks",
            "load-public-crosswalks",
            "link-public-crosswalks",
            "load-pedestrian-references",
            "preprocess-public-streetlights",
            "load-public-streetlights",
        ],
        help="One-time pipeline command to execute",
    )
    parser.add_argument("--input", help="Source SHP, GeoJSON, or GPKG inside raw/")
    parser.add_argument("--district-name", default="미추홀구")
    parser.add_argument("--boundary", help="Optional Michuhol-gu polygon file")
    parser.add_argument("--district-field", help="Source attribute used to filter Michuhol-gu")
    parser.add_argument("--district-value", default="미추홀구")
    parser.add_argument("--assume-michuhol-only", action="store_true")
    parser.add_argument("--source-crs", help="Required only when the source file has no CRS")
    parser.add_argument("--boundary-crs", help="Required only when the boundary has no CRS")
    parser.add_argument("--field-map", help="Canonical-to-source field mapping JSON")
    parser.add_argument(
        "--source-encoding",
        help="DBF text encoding when it cannot be detected, for example CP949",
    )
    parser.add_argument("--source")
    parser.add_argument("--road-source", default="osm")
    parser.add_argument("--cctv-source", default="michuhol-cctv-ai-ready")
    parser.add_argument("--help-point-source", default="ai-ready-help-points")
    parser.add_argument(
        "--source-dataset",
    )
    parser.add_argument("--source-url", help="Authoritative DEM dataset page URL")
    parser.add_argument("--source-date", help="DEM reference date")
    parser.add_argument("--source-license", help="DEM reuse license")
    parser.add_argument("--field-audit-output", help="Optional GeoJSON for on-site road checks")
    parser.add_argument("--crosswalk-audit-output", help="Optional GeoJSON of route-near crosswalk review candidates")
    arguments = parser.parse_args()

    if arguments.command == "collect-weather":
        collect_weather()
    elif arguments.command == "weather-worker":
        from weather_worker import run_weather_worker
        run_weather_worker(collect_weather)
    elif arguments.command == "collect-osm":
        collect_osm()
    elif arguments.command == "preprocess-osm":
        preprocess_osm()
    elif arguments.command == "load-osm":
        load_osm()
    elif arguments.command == "run-osm":
        run_osm()
    elif arguments.command == "preprocess-buildings":
        preprocess_building_file(arguments)
    elif arguments.command == "load-buildings":
        load_building_file(arguments)
    elif arguments.command == "run-buildings":
        run_buildings(arguments)
    elif arguments.command == "preprocess-streetlights":
        preprocess_streetlight_file(arguments)
    elif arguments.command == "load-streetlights":
        load_streetlight_file(arguments)
    elif arguments.command == "analyze-streetlights":
        analyze_streetlights(arguments)
    elif arguments.command == "run-streetlight-safety":
        run_streetlight_pipeline(arguments)
    elif arguments.command == "run-osm-streetlights":
        run_osm_streetlight_pipeline(arguments)
    elif arguments.command == "collect-cctvs":
        collect_cctv_file()
    elif arguments.command == "preprocess-cctvs":
        preprocess_cctv_file()
    elif arguments.command == "load-cctvs":
        load_cctv_file()
    elif arguments.command == "run-cctvs":
        run_cctv_pipeline()
    elif arguments.command == "run-cctv-csv":
        run_cctv_csv_pipeline(arguments)
    elif arguments.command == "load-help-points":
        load_help_point_file(arguments)
    elif arguments.command == "analyze-safety-components":
        analyze_safety_components(arguments)
    elif arguments.command == "run-safety-components":
        run_safety_components(arguments)
    elif arguments.command == "calculate-road-slopes":
        if not arguments.input:
            parser.error("calculate-road-slopes requires --input GeoTIFF")
        stats = calculate_road_slopes(
            PROCESSED_OSM_PATH,
            Path(arguments.input),
            PROCESSED_ELEVATION_PATH,
            source_name=arguments.source_dataset or "",
            source_url=arguments.source_url or "",
            source_date=arguments.source_date or "",
            license_name=arguments.source_license or "",
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif arguments.command == "load-road-slopes":
        print(f"Updated {load_road_slopes(PROCESSED_ELEVATION_PATH)} road grades")
    elif arguments.command == "audit-road-network":
        report = audit_road_network(
            PROCESSED_OSM_PATH,
            Path(__file__).parent / "config" / "pedestrian_route_cases.json",
            Path(arguments.field_audit_output) if arguments.field_audit_output else None,
            PROCESSED_PUBLIC_CROSSWALKS_PATH if arguments.crosswalk_audit_output else None,
            Path(arguments.crosswalk_audit_output) if arguments.crosswalk_audit_output else None,
        )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if report["passed"] != len(report["cases"]):
            raise SystemExit(1)
    elif arguments.command == "preprocess-public-crosswalks":
        stats = preprocess_incheon_crosswalks(
            Path(arguments.input) if arguments.input else RAW_PUBLIC_CROSSWALKS_PATH,
            PROCESSED_PUBLIC_CROSSWALKS_PATH,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif arguments.command == "load-public-crosswalks":
        print(f"Loaded {load_public_crosswalks(PROCESSED_PUBLIC_CROSSWALKS_PATH)} official crosswalk POIs")
    elif arguments.command == "link-public-crosswalks":
        print(json.dumps(link_public_crosswalks(), ensure_ascii=False, indent=2))
    elif arguments.command == "load-pedestrian-references":
        path = Path(arguments.input) if arguments.input else Path(__file__).parent / "raw" / "pedestrian_references" / "pedestrian_references.geojson"
        print(json.dumps(load_pedestrian_references(path), ensure_ascii=False, indent=2))
    elif arguments.command == "preprocess-public-streetlights":
        stats = preprocess_incheon_streetlights(
            Path(arguments.input) if arguments.input else RAW_PUBLIC_CROSSWALKS_PATH,
            PROCESSED_PUBLIC_STREETLIGHTS_PATH,
        )
        print(json.dumps(stats, ensure_ascii=False, indent=2))
    elif arguments.command == "load-public-streetlights":
        count = load_streetlights(
            PROCESSED_PUBLIC_STREETLIGHTS_PATH, replace_source="incheon-road-poi-2022"
        )
        print(f"Loaded {count} official streetlight POIs")


if __name__ == "__main__":
    main()
