import argparse
import json
import os
from pathlib import Path

from analysis.streetlight_safety import run_streetlight_safety_analysis
from analysis.safety_components import run_safety_component_analysis
from collectors.cctvs import collect_cctvs
from collectors.osm import collect_osm_roads
from loaders.buildings import load_buildings
from loaders.postgis import load_road_segments
from loaders.streetlights import load_streetlights
from loaders.cctvs import load_cctvs
from loaders.help_points import load_help_points
from preprocess.buildings import preprocess_buildings
from preprocess.osm_roads import preprocess_osm_roads
from preprocess.roads import read_road_features
from preprocess.streetlights import preprocess_streetlights


RAW_OSM_PATH = Path(__file__).parent / "raw" / "osm" / "michuhol_roads.json"
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
RAW_CCTVS_PATH = Path(__file__).parent / "raw" / "cctvs" / "michuhol_cctvs.json"
PROCESSED_CCTVS_PATH = (
    Path(__file__).parent / "processed" / "cctvs" / "michuhol_cctvs.json"
)
RAW_HELP_POINTS_PATH = (
    Path(__file__).parent
    / "raw"
    / "help_points"
    / "help_points_michuhol_routing_ready.geojson"
)


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


def collect_cctv_file() -> None:
    print(json.dumps(collect_cctvs(RAW_CCTVS_PATH), ensure_ascii=False, indent=2))


def _safety_cctv_purposes() -> set[str]:
    return {
        value.strip()
        for value in os.getenv("SAFETY_CCTV_PURPOSES", "").split(",")
        if value.strip()
    }


def preprocess_cctv_file() -> None:
    from preprocess.cctvs import preprocess_cctvs

    stats = preprocess_cctvs(
        RAW_CCTVS_PATH,
        PROCESSED_CCTVS_PATH,
        safety_purposes=_safety_cctv_purposes(),
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))


def load_cctv_file() -> None:
    count = load_cctvs(
        PROCESSED_CCTVS_PATH, replace_source="data-go-kr-15096428"
    )
    print(f"Replaced data-go-kr-15096428 CCTV records with {count} PostGIS rows")


def run_cctv_pipeline() -> None:
    collect_cctv_file()
    preprocess_cctv_file()
    load_cctv_file()


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
    run_cctv_pipeline()
    load_help_point_file(arguments)
    analyze_safety_components(arguments)


def main() -> None:
    parser = argparse.ArgumentParser(description="SafeAlley data pipeline")
    parser.add_argument(
        "command",
        choices=[
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
            "collect-cctvs",
            "preprocess-cctvs",
            "load-cctvs",
            "run-cctvs",
            "load-help-points",
            "analyze-safety-components",
            "run-safety-components",
        ],
        help="One-time pipeline command to execute",
    )
    parser.add_argument("--input", help="Source SHP, GeoJSON, or GPKG inside raw/")
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
    parser.add_argument("--cctv-source", default="data-go-kr-15096428")
    parser.add_argument("--help-point-source", default="ai-ready-help-points")
    parser.add_argument(
        "--source-dataset",
    )
    arguments = parser.parse_args()

    if arguments.command == "collect-osm":
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
    elif arguments.command == "collect-cctvs":
        collect_cctv_file()
    elif arguments.command == "preprocess-cctvs":
        preprocess_cctv_file()
    elif arguments.command == "load-cctvs":
        load_cctv_file()
    elif arguments.command == "run-cctvs":
        run_cctv_pipeline()
    elif arguments.command == "load-help-points":
        load_help_point_file(arguments)
    elif arguments.command == "analyze-safety-components":
        analyze_safety_components(arguments)
    elif arguments.command == "run-safety-components":
        run_safety_components(arguments)


if __name__ == "__main__":
    main()
