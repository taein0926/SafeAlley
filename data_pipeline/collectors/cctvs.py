import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen


class CctvCollectionError(RuntimeError):
    """Raised when the configured official CCTV API cannot be collected."""


def _records(document: Any) -> list[dict[str, Any]]:
    candidates: list[Any] = [document]
    while candidates:
        value = candidates.pop(0)
        if isinstance(value, list) and all(isinstance(item, dict) for item in value):
            return value
        if not isinstance(value, dict):
            continue
        for key in ("data", "items", "item", "records", "row"):
            if key in value:
                candidates.append(value[key])
        for key in ("response", "body", "result"):
            if key in value:
                candidates.append(value[key])
    raise CctvCollectionError("Cannot locate a CCTV record array in the API response")


def collect_cctvs(output_path: Path) -> dict[str, Any]:
    endpoint = os.getenv("DATA_GO_KR_CCTV_API_URL", "").strip()
    service_key = os.getenv("DATA_GO_KR_SERVICE_KEY", "").strip()
    if not endpoint:
        raise CctvCollectionError(
            "DATA_GO_KR_CCTV_API_URL is required; copy the official request URL "
            "from data.go.kr dataset 15096428 without inventing an endpoint"
        )
    if not service_key:
        raise CctvCollectionError("DATA_GO_KR_SERVICE_KEY is required")

    # data.go.kr may issue a percent-encoded key. Preserve existing percent escapes
    # while still safely encoding a decoded key.
    query = "serviceKey=" + quote(service_key, safe="%") + "&" + urlencode(
        {"pageNo": 1, "numOfRows": 10000, "type": "json"}
    )
    separator = "&" if "?" in endpoint else "?"
    request = Request(
        f"{endpoint}{separator}{query}",
        headers={"Accept": "application/json", "User-Agent": "SafeAlley-MVP/0.1"},
    )
    try:
        with urlopen(request, timeout=120) as response:
            document = json.load(response)
    except (OSError, ValueError) as exc:
        raise CctvCollectionError("Official CCTV API request failed") from exc

    records = _records(document)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(
            {
                "source": "data-go-kr-15096428",
                "dataset_id": "15096428",
                "records": records,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return {"record_count": len(records), "output_path": str(output_path)}
