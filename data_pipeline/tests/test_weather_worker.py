import weather_worker
from datetime import datetime

import pytest


@pytest.mark.parametrize("stamp,expected", [
    ("2026-09-29T01:00:00+09:00", "2026-09-29T02:15:00+09:00"),
    ("2026-09-29T08:14:59+09:00", "2026-09-29T08:15:00+09:00"),
    ("2026-09-29T08:15:00+09:00", "2026-09-29T11:15:00+09:00"),
    ("2026-09-29T09:30:00+09:00", "2026-09-29T11:15:00+09:00"),
    ("2026-09-29T23:15:00+09:00", "2026-09-30T02:15:00+09:00"),
])
def test_forecast_schedule_follows_issue_times_not_startup_hour(stamp, expected):
    assert weather_worker.next_forecast_refresh(datetime.fromisoformat(stamp)).isoformat() == expected


def test_solar_refresh_at_korean_midnight():
    now = datetime.fromisoformat("2026-09-29T14:30:00+00:00")
    assert weather_worker.next_solar_refresh(now).isoformat() == "2026-09-30T00:00:00+09:00"


def test_failed_solar_retries_without_recollecting_successful_forecast(monkeypatch):
    clock = [datetime.fromisoformat("2026-09-29T09:00:00+09:00").timestamp()]
    calls = []
    waits = []

    class Stop:
        stopped = False

        def is_set(self):
            return self.stopped

        def set(self):
            self.stopped = True

    stop = Stop()
    monkeypatch.setattr(weather_worker, "Event", lambda: stop)
    monkeypatch.setattr(weather_worker.signal, "signal", lambda *_: None)
    monkeypatch.setattr(weather_worker.time, "time", lambda: clock[0])

    def wait(_, delay):
        waits.append(delay)
        clock[0] += delay
        if len(waits) == 2:
            stop.set()

    def collect(**kwargs):
        calls.append(kwargs)
        if len(calls) == 2:
            raise SystemExit(1)

    monkeypatch.setattr(weather_worker, "wait_for_refresh", wait)
    weather_worker.run_weather_worker(collect)
    assert calls == [
        {"include_forecast": True, "include_solar": False},
        {"include_forecast": False, "include_solar": True},
        {"include_forecast": False, "include_solar": True},
    ]
    assert waits == [300, 7800]


def test_resume_after_pc_sleep_refreshes_without_waiting_the_remaining_hour(monkeypatch):
    clock = [1000.0]
    waits = []

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            waits.append(seconds)
            # The host sleeps overnight during the first short wait.
            clock[0] += 12 * 3600
            return False

    monkeypatch.setattr(weather_worker.time, "time", lambda: clock[0])
    weather_worker.wait_for_refresh(Stop(), 3600)
    assert waits == [30]


def test_normal_schedule_waits_until_due(monkeypatch):
    clock = [1000.0]

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            clock[0] += seconds
            return False

    monkeypatch.setattr(weather_worker.time, "time", lambda: clock[0])
    weather_worker.wait_for_refresh(Stop(), 75)
    assert clock[0] == 1075


def test_shutdown_interrupts_scheduled_wait(monkeypatch):
    monkeypatch.setattr(weather_worker.time, "time", lambda: 1000)

    class Stop:
        def is_set(self):
            return False

        def wait(self, seconds):
            assert seconds == 30
            return True

    weather_worker.wait_for_refresh(Stop(), 3600)
