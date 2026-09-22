const DEPARTURE_TIME = /^([01]\d|2[0-3]):[0-5]\d(?::[0-5]\d)?$/;

export function isNightDepartureTime(value: string | null): boolean {
  if (value === null) return false;
  const match = DEPARTURE_TIME.exec(value);
  if (match === null) return false;
  const hour = Number(match[1]);
  return hour >= 20 || hour < 6;
}
