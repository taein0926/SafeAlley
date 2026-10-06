from threading import Event

import pytest

from app.schemas.agent import RoutePreference
from app.services import route_progress


def test_progress_arrives_while_routing_is_still_blocked():
    release = Event()
    finished = Event()

    def work(callback):
        callback({"id": "candidate", "message": "최단 후보 확인", "state": "completed"})
        assert release.wait(3)
        finished.set()
        return "result"

    events = route_progress.iter_workflow_progress(work)
    try:
        assert next(events)["type"] == "route_progress"
        assert not finished.is_set()
    finally:
        release.set()
    assert next(events) == {"type": "routing_result", "data": "result"}
    with pytest.raises(StopIteration):
        next(events)


def test_worker_errors_are_propagated_without_result():
    def work(callback):
        raise ValueError("no route")
    with pytest.raises(ValueError, match="no route"):
        list(route_progress.iter_workflow_progress(work))


def test_facility_numbers_are_real_counts_and_only_requested_categories_are_shown(monkeypatch):
    geometry = {"type": "LineString", "coordinates": [[126.6, 37.4], [126.7, 37.5]]}
    calls = []
    def count(value):
        calls.append(value)
        return {"streetlights": 17, "cctvs": 8}
    monkeypatch.setattr(route_progress, "count_route_facilities", count)
    candidate = {"route_type": "shortest", "metrics": {"distance_m": 920}, "route": {"geometry": geometry}}
    preferences = [RoutePreference(factor="streetlight_score", direction="maximize")]
    events = []
    route_progress.candidate_report(None, candidate, preferences)
    assert calls == []
    route_progress.candidate_report(events.append, candidate, preferences)
    assert calls == [geometry]
    assert "가로등 위치 17곳" in events[-1]["message"]
    assert "CCTV" not in events[-1]["message"]


def test_missing_or_equal_metrics_do_not_claim_better_route():
    preferences = [RoutePreference(factor="stairs_distance_m", direction="avoid"),
                   RoutePreference(factor="cctv_score", direction="maximize")]
    candidates = [{"route_type": name, "metrics": {"stairs_distance_m": 0, "cctv_score": None}}
                  for name in ("shortest", "custom")]
    events = []
    route_progress.comparison_reports(events.append, candidates, preferences)
    assert "두 후보의 값이 같아요" in events[0]["message"]
    assert events[1]["state"] == "unavailable"
    assert "반영할 수 없어요" in events[1]["message"]


def test_comparisons_show_tradeoffs_instead_of_always_favoring_custom():
    candidates = [
        {"route_type": "shortest", "metrics": {"cctv_score": 26.4, "crosswalk_count": 5}},
        {"route_type": "custom", "metrics": {"cctv_score": 23.9, "crosswalk_count": 2}},
    ]
    events = []
    route_progress.comparison_reports(events.append, candidates, [
        RoutePreference(factor="cctv_score", direction="maximize"),
        RoutePreference(factor="crosswalk_count", direction="minimize"),
    ])
    assert "CCTV를 비교" in events[0]["message"]
    assert "최단 후보가 더 유리" in events[0]["message"]
    assert "맞춤 후보가 더 유리" in events[1]["message"]
