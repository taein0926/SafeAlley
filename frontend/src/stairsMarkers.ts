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
// Solid stair profile and ascent arrow remain legible at map-marker size.
export const STAIRS_MARKER_IMAGE = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 44 44"><circle cx="22" cy="22" r="21" fill="#ffffff" stroke="#52677d" stroke-width="2"/><g transform="translate(4.4 4.4) scale(0.8)"><path d="M8 35v-7h7v-7h7v-7h7V8h7v27Z" fill="#34495e"/><path d="M8 20 20 8M12 8h8v8" fill="none" stroke="#34495e" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/></g></svg>',
)}`;
