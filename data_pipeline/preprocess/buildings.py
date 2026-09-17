import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import fiona
from pyproj import CRS, Transformer
from shapely import make_valid, union_all
from shapely.geometry import GeometryCollection, MultiPolygon, Polygon, mapping, shape
from shapely.ops import transform as transform_geometry


class BuildingPreprocessError(RuntimeError):
    """Raised when a source building file cannot produce valid building polygons."""


FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "building_id": (
        "building_id",
        "buld_pk",
        "bd_mgt_sn",
        "관리건축물대장pk",
        "건물id",
    ),
    "building_name": ("building_name", "buld_nm", "건물명", "건물명칭"),
    "address": ("address", "plat_plc", "new_plat_plc", "주소", "대지위치"),
    "main_use": (
        "main_use",
        "building_use",
        "main_purps_nm",
        "buld_usenm",
        "주용도",
        "용도",
    ),
    "building_area": ("building_area", "arch_area", "buld_area", "건축면적"),
    "total_floor_area": (
        "total_floor_area",
        "tot_area",
        "연면적",
        "용적율산정연면적",
    ),
    "height_m": ("height", "height_m", "heit", "건물높이", "높이"),
    "floors": ("floors", "grnd_flr_cnt", "지상층수", "층수"),
    "source_updated_at": (
        "updated_at",
        "source_updated_at",
        "gis_cret_dat",
        "갱신일자",
        "기준일자",
    ),
}


def _normalized_fields(properties: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).strip().lower(): str(key) for key in properties}


def _field_value(
    properties: Mapping[str, Any],
    canonical_name: str,
    field_map: Mapping[str, str | list[str]],
) -> Any:
    normalized = _normalized_fields(properties)
    configured = field_map.get(canonical_name)
    if isinstance(configured, list):
        parts = []
        for configured_field in configured:
            original_name = normalized.get(configured_field.strip().lower())
            value = properties.get(original_name) if original_name is not None else None
            if value is not None and str(value).strip():
                parts.append(str(value).strip())
        return " ".join(parts) or None

    candidates = (configured,) if configured else FIELD_ALIASES[canonical_name]
    for candidate in candidates:
        if candidate is None:
            continue
        original_name = normalized.get(candidate.strip().lower())
        if original_name is not None:
            return properties.get(original_name)
    return None


def _optional_number(value: Any) -> float | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        number = float(str(value).replace(",", ""))
    except ValueError:
        return None
    return number if number >= 0 else None


def _optional_integer(value: Any) -> int | None:
    number = _optional_number(value)
    return int(number) if number is not None else None


def _source_crs(collection: fiona.Collection, override: str | None) -> CRS:
    value: Any = override or collection.crs_wkt or collection.crs
    if not value:
        raise BuildingPreprocessError(
            "The input file has no CRS. Provide --source-crs, for example EPSG:5179."
        )
    try:
        return CRS.from_user_input(value)
    except Exception as exc:
        raise BuildingPreprocessError(f"Invalid source CRS: {value}") from exc


def _polygonal_geometry(geometry: Any) -> MultiPolygon | None:
    if geometry.is_empty:
        return None
    geometry = make_valid(geometry)
    if isinstance(geometry, Polygon):
        return MultiPolygon([geometry])
    if isinstance(geometry, MultiPolygon):
        return geometry
    if isinstance(geometry, GeometryCollection):
        polygons = [
            part
            for part in geometry.geoms
            if isinstance(part, (Polygon, MultiPolygon)) and not part.is_empty
        ]
        if not polygons:
            return None
        return _polygonal_geometry(union_all(polygons))
    return None


def _load_boundary(path: Path, source_crs_override: str | None) -> MultiPolygon:
    try:
        with fiona.open(path) as collection:
            source_crs = _source_crs(collection, source_crs_override)
            transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)
            parts = [
                transform_geometry(transformer.transform, shape(feature["geometry"]))
                for feature in collection
                if feature.get("geometry") is not None
            ]
    except BuildingPreprocessError:
        raise
    except Exception as exc:
        raise BuildingPreprocessError(f"Cannot read boundary file: {path}") from exc

    boundary = _polygonal_geometry(union_all(parts)) if parts else None
    if boundary is None:
        raise BuildingPreprocessError("Boundary file contains no polygon geometry")
    return boundary


def _load_field_map(path: Path | None) -> dict[str, str | list[str]]:
    if path is None:
        return {}
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise BuildingPreprocessError(f"Cannot read field map: {path}") from exc
    if not isinstance(document, dict):
        raise BuildingPreprocessError("Field map must be a JSON object")
    unknown = set(document) - set(FIELD_ALIASES)
    if unknown:
        raise BuildingPreprocessError(
            f"Unknown canonical field names: {', '.join(sorted(unknown))}"
        )
    field_map: dict[str, str | list[str]] = {}
    for key, value in document.items():
        if isinstance(value, str) and value.strip():
            field_map[str(key)] = value
        elif (
            isinstance(value, list)
            and value
            and all(isinstance(item, str) and item.strip() for item in value)
        ):
            field_map[str(key)] = value
        elif value:
            raise BuildingPreprocessError(
                f"Field map value for {key} must be a field name or a list of field names"
            )
    return field_map


def preprocess_buildings(
    input_path: Path,
    output_path: Path,
    *,
    source: str,
    source_dataset: str,
    boundary_path: Path | None = None,
    district_field: str | None = None,
    district_value: str = "미추홀구",
    assume_michuhol_only: bool = False,
    source_crs_override: str | None = None,
    boundary_crs_override: str | None = None,
    field_map_path: Path | None = None,
    source_encoding: str | None = None,
) -> dict[str, int]:
    if not input_path.exists():
        raise BuildingPreprocessError(f"Building source file does not exist: {input_path}")
    if not source.strip():
        raise BuildingPreprocessError("Building source name is required")
    if boundary_path is None and district_field is None and not assume_michuhol_only:
        raise BuildingPreprocessError(
            "Provide --boundary, --district-field, or explicitly use "
            "--assume-michuhol-only for an already filtered source file."
        )

    boundary = (
        _load_boundary(boundary_path, boundary_crs_override)
        if boundary_path is not None
        else None
    )
    field_map = _load_field_map(field_map_path)
    output_features: list[dict[str, Any]] = []
    input_count = 0

    try:
        open_options = {"encoding": source_encoding} if source_encoding else {}
        with fiona.open(input_path, **open_options) as collection:
            source_crs = _source_crs(collection, source_crs_override)
            transformer = Transformer.from_crs(source_crs, "EPSG:4326", always_xy=True)

            for feature in collection:
                input_count += 1
                properties = dict(feature.get("properties") or {})
                if district_field is not None:
                    normalized = _normalized_fields(properties)
                    actual_field = normalized.get(district_field.strip().lower())
                    if actual_field is None:
                        raise BuildingPreprocessError(
                            f"District field does not exist: {district_field}"
                        )
                    if str(properties.get(actual_field, "")).strip() != district_value:
                        continue

                raw_geometry = feature.get("geometry")
                if raw_geometry is None:
                    continue
                geometry = transform_geometry(
                    transformer.transform,
                    shape(raw_geometry),
                )
                geometry = _polygonal_geometry(geometry)
                if geometry is None:
                    continue
                if boundary is not None:
                    if not geometry.intersects(boundary):
                        continue
                    geometry = _polygonal_geometry(geometry.intersection(boundary))
                    if geometry is None:
                        continue

                source_feature_id = str(feature.get("id") or input_count)
                building_id_value = _field_value(
                    properties,
                    "building_id",
                    field_map,
                )
                building_id = str(building_id_value or source_feature_id).strip()
                canonical_properties = {
                    "source": source,
                    "building_id": building_id,
                    "building_name": _field_value(
                        properties, "building_name", field_map
                    ),
                    "address": _field_value(properties, "address", field_map),
                    "main_use": _field_value(properties, "main_use", field_map),
                    "building_area": _optional_number(
                        _field_value(properties, "building_area", field_map)
                    ),
                    "total_floor_area": _optional_number(
                        _field_value(properties, "total_floor_area", field_map)
                    ),
                    "height_m": _optional_number(
                        _field_value(properties, "height_m", field_map)
                    ),
                    "floors": _optional_integer(
                        _field_value(properties, "floors", field_map)
                    ),
                    "source_updated_at": _field_value(
                        properties, "source_updated_at", field_map
                    ),
                    "source_dataset": source_dataset,
                    "source_file": input_path.name,
                    "source_feature_id": source_feature_id,
                }
                output_features.append(
                    {
                        "type": "Feature",
                        "id": building_id,
                        "geometry": mapping(geometry),
                        "properties": canonical_properties,
                    }
                )
    except BuildingPreprocessError:
        raise
    except Exception as exc:
        raise BuildingPreprocessError(f"Cannot read building source: {input_path}") from exc

    if not output_features:
        raise BuildingPreprocessError(
            "No Michuhol-gu Polygon or MultiPolygon buildings remained after filtering"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": output_features,
                "metadata": {
                    "crs": "EPSG:4326",
                    "source": source,
                    "source_dataset": source_dataset,
                    "source_file": input_path.name,
                    "input_features": input_count,
                    "output_buildings": len(output_features),
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"input_features": input_count, "output_buildings": len(output_features)}
