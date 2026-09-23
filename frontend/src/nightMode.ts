const DEPARTURE_TIME = /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/;

export function isNightDepartureTime(value: string | null, solar?: { sunrise: string; sunset: string } | null): boolean {
  if (value === null) return false;
  const match = DEPARTURE_TIME.exec(value);
  if (match === null) return false;
  if (solar && DEPARTURE_TIME.test(solar.sunrise) && DEPARTURE_TIME.test(solar.sunset)) {
    const seconds = (clock: string) => clock.split(":").reduce((sum, value, index) => sum + Number(value) * [3600, 60, 1][index], 0);
    const sunrise = seconds(solar.sunrise), sunset = seconds(solar.sunset);
    if (sunrise < sunset) return seconds(value) < sunrise || seconds(value) >= sunset;
  }
  const hour = Number(match[1]);
  return hour >= 20 || hour < 6;
}
