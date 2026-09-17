import pytest

from safety_component_config import SafetyComponentConfig


def test_component_weights_have_one_configuration_source(monkeypatch) -> None:
    monkeypatch.setenv("SAFETY_STREETLIGHT_WEIGHT", "0.4")
    monkeypatch.setenv("SAFETY_CCTV_WEIGHT", "0.4")
    monkeypatch.setenv("SAFETY_HELP_POINT_WEIGHT", "0.2")
    config = SafetyComponentConfig.from_environment()
    assert config.safety_streetlight_weight == 0.4
    assert config.safety_cctv_weight == 0.4
    assert config.safety_help_point_weight == 0.2


def test_invalid_composite_weights_are_rejected(monkeypatch) -> None:
    monkeypatch.setenv("SAFETY_STREETLIGHT_WEIGHT", "0.5")
    monkeypatch.setenv("SAFETY_CCTV_WEIGHT", "0.5")
    monkeypatch.setenv("SAFETY_HELP_POINT_WEIGHT", "0.5")
    with pytest.raises(ValueError, match="sum to 1"):
        SafetyComponentConfig.from_environment()
