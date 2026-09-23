import pytest

import cli


@pytest.fixture
def collection(monkeypatch):
    for name in ("KMA_SERVICE_KEY", "KASI_SERVICE_KEY", "KMA_GRID_NX", "KMA_GRID_NY"):
        monkeypatch.delenv(name, raising=False)
    saved = {"forecast": [], "solar": [], "grids": []}
    def kma(key, nx, ny, now):
        saved["grids"].append((nx, ny))
        return [{"provider": "kma"}]
    def forecasts(rows):
        saved["forecast"].extend(rows)
        return len(rows)
    monkeypatch.setattr(cli, "fetch_forecast", kma)
    monkeypatch.setattr(cli, "fetch_solar", lambda *_: {"provider": "kasi"})
    monkeypatch.setattr(cli, "save_forecasts", forecasts)
    monkeypatch.setattr(cli, "save_solar", saved["solar"].append)
    return saved


def test_kma_only_saves_forecast_but_does_not_invent_solar(monkeypatch, collection):
    monkeypatch.setenv("KMA_SERVICE_KEY", "test-key-not-a-real-secret")
    with pytest.raises(SystemExit):
        cli.collect_weather()
    assert collection["forecast"] == [{"provider": "kma"}]
    assert collection["solar"] == [] and collection["grids"] == [(55, 124)]


def test_no_keys_fail_without_writing_data(collection):
    with pytest.raises(SystemExit):
        cli.collect_weather()
    assert collection["forecast"] == collection["solar"] == []


def test_both_approved_keys_collect_official_sources(monkeypatch, collection):
    monkeypatch.setenv("KMA_SERVICE_KEY", "test-key")
    monkeypatch.setenv("KASI_SERVICE_KEY", "test-key")
    cli.collect_weather()
    assert collection["forecast"] == [{"provider": "kma"}]
    assert collection["solar"] == [{"provider": "kasi"}]
    assert collection["grids"] == [(55, 124)]


@pytest.mark.parametrize("failing_source,expected_forecast,expected_solar", [
    ("fetch_forecast", [], [{"provider": "kasi"}]),
    ("fetch_solar", [{"provider": "kma"}], []),
])
def test_outages_do_not_overwrite_other_provider_or_echo_key(monkeypatch, capsys, collection, failing_source, expected_forecast, expected_solar):
    monkeypatch.setenv("KMA_SERVICE_KEY", "test-private-key")
    monkeypatch.setenv("KASI_SERVICE_KEY", "test-private-key")
    def fail(*_):
        raise RuntimeError("upstream URL contains test-private-key")
    monkeypatch.setattr(cli, failing_source, fail)
    with pytest.raises(SystemExit) as error:
        cli.collect_weather()
    assert error.value.code == 1
    assert collection["forecast"] == expected_forecast and collection["solar"] == expected_solar
    assert "test-private-key" not in capsys.readouterr().out


def test_half_configured_grid_is_rejected_without_guessing(monkeypatch, collection):
    monkeypatch.setenv("KMA_SERVICE_KEY", "test-key")
    monkeypatch.setenv("KASI_SERVICE_KEY", "test-key")
    monkeypatch.setenv("KMA_GRID_NX", "55")
    with pytest.raises(SystemExit):
        cli.collect_weather()
    assert collection["grids"] == [] and collection["forecast"] == []
    assert collection["solar"] == [{"provider": "kasi"}]
