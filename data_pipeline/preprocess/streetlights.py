import csv
import json
from pathlib import Path
from typing import Any


REQUIRED_COLUMNS = ("가로등주명", "소속 분전함", "표찰번호", "경도", "위도")


class StreetlightPreprocessError(RuntimeError):
    """Raised when the official streetlight CSV is malformed."""


def _coordinate(value: str | None, *, name: str, row_number: int) -> float:
    try:
        coordinate = float(str(value).strip())
    except (TypeError, ValueError) as exc:
        raise StreetlightPreprocessError(
            f"Row {row_number} has an invalid {name}: {value!r}"
        ) from exc
    return coordinate


def preprocess_streetlights(
    input_path: Path,
    output_path: Path,
    *,
    source: str,
    source_dataset: str,
    encoding: str = "cp949",
) -> dict[str, Any]:
    if not input_path.exists():
        raise StreetlightPreprocessError(
            f"Streetlight source file does not exist: {input_path}"
        )
    if not source.strip():
        raise StreetlightPreprocessError("Streetlight source name is required")

    features: list[dict[str, Any]] = []
    seen_coordinates: set[tuple[float, float]] = set()
    duplicate_coordinate_count = 0

    try:
        with input_path.open("r", encoding=encoding, newline="") as source_file:
            reader = csv.DictReader(source_file)
            fieldnames = tuple(reader.fieldnames or ())
            missing = set(REQUIRED_COLUMNS) - set(fieldnames)
            if missing:
                raise StreetlightPreprocessError(
                    f"Missing streetlight CSV columns: {', '.join(sorted(missing))}"
                )

            for row_number, row in enumerate(reader, start=1):
                longitude = _coordinate(
                    row.get("경도"), name="longitude", row_number=row_number
                )
                latitude = _coordinate(
                    row.get("위도"), name="latitude", row_number=row_number
                )
                if not (124 <= longitude <= 132 and 33 <= latitude <= 39):
                    raise StreetlightPreprocessError(
                        f"Row {row_number} is outside the expected Korean WGS84 range: "
                        f"{longitude}, {latitude}"
                    )

                coordinate = (longitude, latitude)
                if coordinate in seen_coordinates:
                    duplicate_coordinate_count += 1
                seen_coordinates.add(coordinate)

                source_id = f"michuhol-streetlight-20240806-{row_number:05d}"
                properties = {
                    "source": source,
                    "source_id": source_id,
                    "pole_name": (row.get("가로등주명") or "").strip() or None,
                    "cabinet_name": (row.get("소속 분전함") or "").strip() or None,
                    "label_no": (row.get("표찰번호") or "").strip() or None,
                    "longitude": longitude,
                    "latitude": latitude,
                    "source_dataset": source_dataset,
                    "source_file": input_path.name,
                    "source_row_number": row_number,
                }
                features.append(
                    {
                        "type": "Feature",
                        "id": source_id,
                        "geometry": {
                            "type": "Point",
                            "coordinates": [longitude, latitude],
                        },
                        "properties": properties,
                    }
                )
    except StreetlightPreprocessError:
        raise
    except (LookupError, OSError, UnicodeError) as exc:
        raise StreetlightPreprocessError(
            f"Cannot read streetlight CSV using {encoding}: {input_path}"
        ) from exc

    if not features:
        raise StreetlightPreprocessError("Streetlight CSV contains no data rows")

    document = {
        "type": "FeatureCollection",
        "features": features,
        "metadata": {
            "count": len(features),
            "crs": "EPSG:4326",
            "source": source,
            "source_dataset": source_dataset,
            "source_file": input_path.name,
            "source_encoding": encoding,
            "duplicate_coordinate_count": duplicate_coordinate_count,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return document["metadata"]
