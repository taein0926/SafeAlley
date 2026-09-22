// Place one marker halfway along each mapped stair segment, not at an arbitrary vertex.
export function stairMarkerPosition(coordinates: number[][]): [number, number] | null {
  if (coordinates.length < 2 || coordinates.some(([x, y]) => !Number.isFinite(x) || !Number.isFinite(y))) return null;
  const lengths = coordinates.slice(1).map(([x, y], i) => {
    const [previousX, previousY] = coordinates[i];
    return Math.hypot((x - previousX) * Math.cos((y + previousY) * Math.PI / 360), y - previousY);
  });
  let remaining = lengths.reduce((sum, length) => sum + length, 0) / 2;
  if (remaining === 0) return [coordinates[0][0], coordinates[0][1]];
  for (let i = 0; i < lengths.length; i++) {
    if (remaining <= lengths[i] && lengths[i] > 0) {
      const ratio = remaining / lengths[i];
      return [coordinates[i][0] + (coordinates[i + 1][0] - coordinates[i][0]) * ratio,
        coordinates[i][1] + (coordinates[i + 1][1] - coordinates[i][1]) * ratio];
    }
    remaining -= lengths[i];
  }
  const last = coordinates[coordinates.length - 1];
  return [last[0], last[1]];
}
// A font-independent stair pictogram: emoji fonts do not consistently support 🪜.
export const STAIRS_MARKER_IMAGE = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="44" height="44" viewBox="0 0 44 44"><rect x="1" y="1" width="42" height="42" rx="11" fill="#173944" stroke="#e3f6ff" stroke-width="2"/><path d="M8 34h7v-8h7v-8h7v-8h7" fill="none" stroke="#ffffff" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/></svg>',
)}`;
