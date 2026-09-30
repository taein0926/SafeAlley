import pytest
from contextlib import nullcontext

from app.services import personalization_service as service


def test_intersection_exposure_is_minimized():
    assert service._desirability("crosswalk_count", 0, [0, 100]) == 1
    assert service._desirability("crosswalk_count", 100, [0, 100]) == 0


def test_new_metrics_are_not_implicitly_learned(monkeypatch):
    candidates = [
        {"metrics": {"crosswalk_count": 0, "future_metric": 0}},
        {"metrics": {"crosswalk_count": 100, "future_metric": 100}},
    ]
    monkeypatch.setattr(service, "selection_transaction", lambda _: nullcontext(None))
    monkeypatch.setattr(service, "record_selection", lambda *args: (candidates, candidates[0], True))
    monkeypatch.setattr(service, "get_learned_preferences", lambda *args: {})
    monkeypatch.setitem(service.METRIC_REGISTRY, "future_metric", object())
    saved = {}
    monkeypatch.setattr(service, "upsert_learned_preferences", lambda _, updates, connection: saved.update(updates))
    service.learn_from_selection("recommendation", "user", "shortest")
    assert saved == {"crosswalk_count": pytest.approx(0.6)}
