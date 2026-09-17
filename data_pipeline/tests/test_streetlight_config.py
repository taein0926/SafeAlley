import pytest

from streetlight_config import StreetlightAnalysisConfig


def test_default_streetlight_weights_sum_to_one(monkeypatch) -> None:
    for name in (
        "STREETLIGHT_DISTANCE_WEIGHT",
        "STREETLIGHT_DENSITY_WEIGHT",
        "STREETLIGHT_GAP_WEIGHT",
    ):
        monkeypatch.delenv(name, raising=False)
    config = StreetlightAnalysisConfig.from_environment()
    assert config.total_weight == pytest.approx(1.0)


def test_invalid_streetlight_weights_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("STREETLIGHT_DISTANCE_WEIGHT", "0.8")
    with pytest.raises(ValueError, match="add up"):
        StreetlightAnalysisConfig.from_environment()
