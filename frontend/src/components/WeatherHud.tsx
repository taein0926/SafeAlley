import { useEffect, useState } from "react";
import { koreaDate, koreaTime, matchingWeather, weatherRefreshDelay, weatherSymbol, type WeatherData } from "../weather";

export function useWeather(departureTime: string | null) {
  const [clock, setClock] = useState(() => new Date());
  const [data, setData] = useState<WeatherData | null>(null);
  const [error, setError] = useState(false);
  const date = koreaDate(clock);
  const time = departureTime ?? koreaTime(clock);
  useEffect(() => {
    const timer = window.setInterval(() => setClock(new Date()), 60_000);
    return () => window.clearInterval(timer);
  }, []);
  useEffect(() => {
    const controller = new AbortController();
    let timer: number | undefined;
    let loading = false;
    async function load() {
      if (loading || controller.signal.aborted) return;
      loading = true;
      window.clearTimeout(timer);
      let next: WeatherData | null = null;
      try {
        const response = await fetch(`/api/weather?departure_time=${encodeURIComponent(time)}`, { signal: controller.signal, cache: "no-store" });
        if (!response.ok) throw new Error();
        next = await response.json();
        if (!controller.signal.aborted) { setData(next); setError(false); }
      } catch {
        if (!controller.signal.aborted) { setData(null); setError(true); }
      } finally {
        loading = false;
        if (!controller.signal.aborted) {
          timer = window.setTimeout(() => void load(), weatherRefreshDelay(next));
        }
      }
    }
    function resume() {
      if (document.visibilityState === "hidden") return;
      setClock(new Date());
      void load();
    }
    setError(false);
    void load();
    window.addEventListener("focus", resume);
    window.addEventListener("online", resume);
    document.addEventListener("visibilitychange", resume);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
      window.removeEventListener("focus", resume);
      window.removeEventListener("online", resume);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [date, time]);
  const solar = data?.solar?.solar_date === date ? data.solar : null;
  return { data: matchingWeather(data, date, time), solar, error, date, time };
}

export function WeatherHud({ data, error, date, time }: ReturnType<typeof useWeather>) {
  const forecast = data?.forecast ?? null;
  const symbol = weatherSymbol(forecast);
  return <section id="map-weather" className="weather-hud" aria-label="출발 시간 날씨" aria-live="polite">
    <div className="weather-hud-toprow">
      <div className="weather-hud-heading">미추홀구 · {date.slice(5).replace("-", "/")} {time.slice(0, 5)} 기준</div>
    </div>
    {forecast ? <div className="weather-hud-values">
      <span role="img" aria-label={symbol.label} title={symbol.label}>{symbol.icon}</span>
      <span className="weather-temperature" title="예보 기온">{forecast.temperature_c === null ? "기온 미제공" : `${forecast.temperature_c}°C`}</span>
      <span className="weather-wind" title="예보 풍속">{forecast.wind_speed_ms === null ? "풍속 미제공" : `${forecast.wind_speed_ms} m/s`}</span>
    </div> : <div className="weather-hud-unavailable">{error ? "날씨 연결 재시도 중…" : !data ? "날씨 확인 중…" : data.forecast_status === "stale" ? "최신 예보 자동 갱신 대기 중…" : "해당 시간 예보 미연결 · 자동 재조회 중"}</div>}
  </section>;
}
