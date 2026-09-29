export type WeatherData = {
  date: string;
  departure_time: string;
  region_label: string;
  forecast_status: "available" | "unavailable" | "stale";
  forecast: {
    provider: "kma";
    forecast_at: string; issued_at: string; temperature_c: number | null;
    wind_speed_ms: number | null; sky: number | null;
    precipitation_type: number | null; precipitation_probability: number | null;
  } | null;
  solar: { provider: "kasi"; solar_date: string; location: string; sunrise: string; sunset: string } | null;
  theme_source: "official_solar" | "fallback";
  is_night: boolean;
};

export function weatherRefreshDelay(data: WeatherData | null): number {
  return data?.forecast_status === "available" && data.solar
    ? 15 * 60_000
    : 60_000;
}

export function koreaDate(now = new Date()): string {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit" }).format(now);
}

export function koreaTime(now = new Date()): string {
  return new Intl.DateTimeFormat("en-GB", { timeZone: "Asia/Seoul", hour: "2-digit", minute: "2-digit", hourCycle: "h23" }).format(now);
}

export function weatherSymbol(forecast: WeatherData["forecast"]) {
  if (!forecast) return { icon: "—", label: "예보 없음" };
  if ([1, 2, 4].includes(forecast.precipitation_type ?? -1)) return { icon: "☂️", label: forecast.precipitation_type === 2 ? "비·눈 예보" : "비 예보" };
  if (forecast.precipitation_type === 3) return { icon: "❄️", label: "눈 예보" };
  // Missing precipitation is not evidence of clear weather.
  if (forecast.precipitation_type !== 0) return { icon: "—", label: "날씨 정보 부족" };
  if (forecast.sky === 1) return { icon: "☀️", label: "맑음" };
  if (forecast.sky === 3) return { icon: "🌤️", label: "구름 많음" };
  if (forecast.sky === 4) return { icon: "☁️", label: "흐림" };
  return { icon: "—", label: "하늘 상태 미제공" };
}

export function matchingWeather(data: WeatherData | null, date: string, time: string): WeatherData | null {
  return data?.date === date && data.departure_time.slice(0, 5) === time.slice(0, 5) ? data : null;
}
