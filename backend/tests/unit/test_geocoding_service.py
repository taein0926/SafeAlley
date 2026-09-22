from app.services import geocoding_service


BOUNDS = (126.6, 37.4, 126.75, 37.52)


def test_geocoder_preserves_korean_display_name_and_osm_identity(monkeypatch) -> None:
    monkeypatch.setattr(
        geocoding_service,
        "_request_results",
        lambda *_: [
            {
                "lat": "37.45",
                "lon": "126.65",
                "display_name": "인하대학교, 미추홀구, 인천광역시",
                "namedetails": {"name:ko": "인하대학교"},
                "type": "university",
                "osm_type": "way",
                "osm_id": 123,
            }
        ],
    )

    result = geocoding_service.geocode_place("인하대학교", BOUNDS)

    assert result is not None
    assert result["name"] == "인하대학교"
    assert result["source"] == "nominatim-osm"
    assert result["source_id"] == "way-123"


def test_geocoder_rejects_result_outside_loaded_osm_bounds(monkeypatch) -> None:
    monkeypatch.setattr(
        geocoding_service,
        "_request_results",
        lambda *_: [{"lat": "37.8", "lon": "127.1", "osm_id": 1}],
    )

    assert geocoding_service.geocode_place("동명이인", BOUNDS) is None


def test_reverse_geocoder_reuses_shared_nominatim_request(monkeypatch) -> None:
    captured: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        geocoding_service,
        "_request_payload",
        lambda path, params: captured.append((path, params)) or {
            "lat": "37.45",
            "lon": "126.65",
            "display_name": "인천대로, 미추홀구, 인천광역시",
            "name": "인천대로",
            "type": "road",
            "osm_type": "way",
            "osm_id": 456,
        },
    )

    result = geocoding_service.reverse_geocode_place(37.45, 126.65)

    assert captured[0][0] == "reverse"
    assert captured[0][1]["zoom"] == 18
    assert result["name"] == "인천대로"
    assert result["source_id"] == "way-456"
