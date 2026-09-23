import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { koreaDate, koreaTime, matchingWeather, weatherSymbol, type WeatherData } from "../weather";

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
    async function load() {
      try {
        const response = await fetch(`/api/weather?departure_time=${encodeURIComponent(time)}`, { signal: controller.signal });
        if (!response.ok) throw new Error();
        const next: WeatherData = await response.json();
        if (!controller.signal.aborted) { setData(next); setError(false); }
      } catch {
        if (!controller.signal.aborted) { setData(null); setError(true); }
      }
    }
    setError(false);
    void load();
    const timer = window.setInterval(() => void load(), 15 * 60_000);
    return () => { controller.abort(); window.clearInterval(timer); };
  }, [date, time]);
  const solar = data?.solar?.solar_date === date ? data.solar : null;
  return { data: matchingWeather(data, date, time), solar, error, date, time };
}

export function WeatherHud({ data, error, date, time, onHeightChange }: ReturnType<typeof useWeather> & { onHeightChange: (height: number) => void }) {
  const hudRef = useRef<HTMLElement>(null);
  useLayoutEffect(() => {
    const hud = hudRef.current;
    if (!hud) return;
    // Keep search/results below the weather card as its content or viewport changes.
    const measure = () => onHeightChange(hud.getBoundingClientRect().height);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(hud);
    return () => observer.disconnect();
  }, [onHeightChange]);
  const forecast = data?.forecast ?? null;
  const symbol = weatherSymbol(forecast);
  return <section ref={hudRef} className="weather-hud" aria-label="출발 시간 날씨" aria-live="polite">
    <div className="weather-hud-toprow">
      <a className="weather-source" href="https://www.data.go.kr/data/15084084/openapi.do" target="_blank" rel="noreferrer">기상청 데이터</a>
      <div className="weather-hud-heading">미추홀구 · {date.slice(5).replace("-", "/")} {time.slice(0, 5)} 기준</div>
    </div>
    {forecast ? <div className="weather-hud-values">
      <span className="weather-condition" title={symbol.label}><span aria-hidden="true">{symbol.icon}</span><small>{symbol.label}</small></span>
      <strong>{forecast.temperature_c === null ? "기온 미제공" : `${forecast.temperature_c}°C`}</strong>
      <span title="예보 풍속"><span aria-hidden="true">💨</span> {forecast.wind_speed_ms === null ? "풍속 미제공" : `${forecast.wind_speed_ms} m/s`}</span>
    </div> : <div className="weather-hud-unavailable">{error ? "날씨 연결을 확인해주세요" : !data ? "날씨 확인 중…" : data.forecast_status === "stale" ? "예보 갱신 필요" : "해당 시간 예보 미연결"}</div>}
  </section>;
}
