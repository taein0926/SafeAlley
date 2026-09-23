"""Periodic batch runner, not a web server; only weather cache tables are written."""
import os
import signal
from threading import Event


def run_weather_worker(collect) -> None:
    stopped = Event()
    signal.signal(signal.SIGTERM, lambda *_: stopped.set())
    signal.signal(signal.SIGINT, lambda *_: stopped.set())
    interval = max(600, min(21600, int(os.environ.get("WEATHER_REFRESH_SECONDS", "3600"))))
    while not stopped.is_set():
        delay = interval
        try:
            collect()
        except (Exception, SystemExit):
            # No credentials, upstream URL or DB connection strings in logs.
            print("Weather collection failed; keeping cached data, retrying in 5 minutes", flush=True)
            delay = 300
        stopped.wait(delay)
