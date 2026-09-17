import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any


class CctvPreprocessError(RuntimeError):
    """Raised when the collected CCTV response cannot be normalized."""


ALIASES: dict[str, tuple[str, ...]] = {
    "management_agency": ("관리기관명", "managementAgency", "mngInsttNm"),
    "road_address": ("소재지도로명주소", "roadAddress", "rdnmadr"),
    "parcel_address": ("소재지지번주소", "parcelAddress", "lnmadr"),
    "purpose": ("설치목적구분", "installationPurposeType", "instlPurpsSe"),
    "camera_count": ("카메라대수", "cameraCount", "cameraNumber", "cameraCo"),
    "camera_pixels": ("카메라화소수", "cameraPixels", "cameraPixel"),
    "direction_info": ("촬영방면정보", "directionInfo", "potogrfInfo"),
    "retention_days": ("보관일수", "retentionDays", "cstdyDayCnt"),
    "installed_at": ("설치년월", "installedAt", "instlYymm"),
    "agency_phone": ("관리기관전화번호", "agencyPhone", "mngInsttTelno"),
    "latitude": ("위도", "latitude"),
    "longitude": ("경도", "longitude"),
    "data_reference_date": ("데이터기준일자", "referenceDate"),
}


def _pick(record: dict[str, Any], name: str) -> Any:
    for alias in ALIASES[name]:
        if alias in record:
            return record[alias]
    return None


def _text(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if value in (None, ""):
        return None
    try:
        number = float(str(value).replace(",", "").strip())
    except (TypeError, ValueError):
        return None
    return int(number) if integer else number


def _coordinate(value: Any) -> tuple[float | None, str | None]:
    if value in (None, ""):
        return None, "null"
    try:
        return float(str(value).strip()), None
    except (TypeError, ValueError):
        return None, "not_numeric"


def preprocess_cctvs(
    input_path: Path,
    output_path: Path,
    *,
    safety_purposes: set[str],
) -> dict[str, Any]:
    try:
        document = json.loads(input_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CctvPreprocessError(f"Cannot read CCTV raw JSON: {input_path}") from exc
    records = document.get("records")
    if not isinstance(records, list) or not all(isinstance(row, dict) for row in records):
        raise CctvPreprocessError("CCTV raw JSON requires a records object array")

    purpose_counts: Counter[str] = Counter()
    normalized: list[dict[str, Any]] = []
    coordinate_present = 0
    coordinate_null = 0
    coordinate_invalid = 0
    for record_index, record in enumerate(records):
        purpose = _text(_pick(record, "purpose"))
        purpose_counts[purpose or "(NULL)"] += 1
        longitude, longitude_error = _coordinate(_pick(record, "longitude"))
        latitude, latitude_error = _coordinate(_pick(record, "latitude"))
        coordinate_status = "valid"
        if longitude_error == "null" or latitude_error == "null":
            coordinate_status = "null"
            coordinate_null += 1
        elif longitude_error or latitude_error:
            coordinate_status = "not_numeric"
            coordinate_invalid += 1
        elif not (124 <= float(longitude) <= 132 and 33 <= float(latitude) <= 39):
            coordinate_status = "out_of_korea_range"
            coordinate_invalid += 1
        else:
            coordinate_present += 1

        canonical = json.dumps(record, ensure_ascii=False, sort_keys=True)
        source_id = hashlib.sha256(
            f"{record_index}:{canonical}".encode("utf-8")
        ).hexdigest()[:32]
        normalized.append(
            {
                "source": "data-go-kr-15096428",
                "source_id": source_id,
                "management_agency": _text(_pick(record, "management_agency")),
                "road_address": _text(_pick(record, "road_address")),
                "parcel_address": _text(_pick(record, "parcel_address")),
                "purpose": purpose,
                "camera_count": _number(_pick(record, "camera_count"), integer=True),
                "camera_pixels": _number(_pick(record, "camera_pixels")),
                "direction_info": _text(_pick(record, "direction_info")),
                "retention_days": _number(_pick(record, "retention_days"), integer=True),
                "installed_at": _text(_pick(record, "installed_at")),
                "agency_phone": _text(_pick(record, "agency_phone")),
                "longitude": longitude if coordinate_status == "valid" else None,
                "latitude": latitude if coordinate_status == "valid" else None,
                "coordinate_status": coordinate_status,
                "data_reference_date": _text(_pick(record, "data_reference_date")),
                "is_safety_cctv": purpose in safety_purposes,
                "properties": record,
            }
        )

    output = {
        "source": "data-go-kr-15096428",
        "dataset_id": "15096428",
        "records": normalized,
        "metadata": {
            "total_count": len(records),
            "purpose_counts": dict(sorted(purpose_counts.items())),
            "configured_safety_purposes": sorted(safety_purposes),
            "safety_cctv_count": sum(row["is_safety_cctv"] for row in normalized),
            "coordinate_present_count": coordinate_present,
            "coordinate_null_count": coordinate_null,
            "coordinate_invalid_count": coordinate_invalid,
        },
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return output["metadata"]
