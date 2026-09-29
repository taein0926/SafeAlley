"""Periodic batch runner, not a web server; only weather cache tables are written."""
import signal
import time
from datetime import datetime, timedelta
from threading import Event

from collectors.weather import KST, latest_forecast_issue


def next_forecast_refresh(now: datetime) -> datetime:
    return latest_forecast_issue(now) + timedelta(hours=3, minutes=15)


def next_solar_refresh(now: datetime) -> datetime:
    return (now.astimezone(KST) + timedelta(days=1)).replace(
        hour=0, minute=0, second=0, microsecond=0,
    )


def wait_for_refresh(stopped: Event, delay: float) -> None:
    """Recheck wall time after short waits so PC sleep cannot defer a due refresh."""
    deadline = time.time() + delay
    while not stopped.is_set():
        remaining = deadline - time.time()
        if remaining <= 0:
            return
        if stopped.wait(min(30, remaining)):
            return


def run_weather_worker(collect) -> None:
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    # Bootstrap both caches once. Afterwards, each source has its own schedule
    # so a solar failure never causes another request for the same KMA issue.
    due = {"forecast": 0.0, "solar": 0.0}
    while not stopped.is_set():
        for source in due:
            if stopped.is_set():
                return
            if time.time() < due[source]:
                continue
            started = datetime.fromtimestamp(time.time(), KST)
            try:
                collect(include_forecast=source == "forecast", include_solar=source == "solar")
                next_run = (next_forecast_refresh(started) if source == "forecast"
                            else next_solar_refresh(started))
                due[source] = next_run.timestamp()
                print(f"{source}: next scheduled collection {next_run.isoformat()}", flush=True)
            except (Exception, SystemExit):
                # No credentials, upstream URL or DB connection strings in logs.
                print(f"{source} collection failed; keeping cache, retrying in 5 minutes", flush=True)
                due[source] = time.time() + 300
        wait_for_refresh(stopped, max(0, min(due.values()) - time.time()))
