export const ROUTE_CAMERA_PITCH = -55 * Math.PI / 180;
const MIN_ROUTE_VIEWPORT_WIDTH = 160;

// Fit the actual route vertices, not an enclosing sphere. Camera-space depth
// accounts for perspective while the left inset excludes the result panel.
export function routeCameraFrame(
  points: Array<{ x: number; y: number; z: number }>,
  width: number, height: number, fovY: number, leftInset = 0, heading = 0, padding = 36, pitch = ROUTE_CAMERA_PITCH,
) {
  const tanY = Math.tan(fovY / 2);
  const tanX = tanY * width / height;
  // On compact screens the search panel and the floating route cards can
  // leave less horizontal room than the requested fixed padding. Reserving
  // that padding anyway collapses the usable viewport to a one-pixel strip,
  // which makes Cesium zoom out to a regional view for a sub-kilometre route.
  // Keep the full padding when it fits, otherwise spend only the space left
  // after preserving a practical route viewport. Bias the reduced budget to
  // the right so endpoint pins still avoid the map controls where possible.
  const minimumViewport = Math.min(MIN_ROUTE_VIEWPORT_WIDTH, Math.max(1, width));
  const boundedInset = Math.min(Math.max(0, leftInset), Math.max(0, width - minimumViewport));
  const horizontalPaddingBudget = Math.max(0, width - boundedInset - minimumViewport);
  const fullPaddingBudget = 2 * padding;
  const leftPadding = horizontalPaddingBudget >= fullPaddingBudget
    ? padding
    : Math.min(padding, horizontalPaddingBudget * 0.4);
  const rightPadding = horizontalPaddingBudget >= fullPaddingBudget
    ? padding
    : Math.min(padding, horizontalPaddingBudget - leftPadding);
  const verticalPadding = Math.min(padding, Math.max(0, (height - 1) / 2));
  const left = 2 * (boundedInset + leftPadding) / width - 1;
  const right = 1 - 2 * rightPadding / width;
  const top = 1 - 2 * verticalPadding / height;
  const sin = Math.sin(-pitch), cos = Math.cos(-pitch);
  const projected = (points.length ? points : [{ x: 0, y: 0, z: 0 }]).map(({ x, y, z }) => {
    const forward = x * Math.sin(heading) + y * Math.cos(heading);
    return { x: x * Math.cos(heading) - y * Math.sin(heading), y: forward * sin + z * cos, z: forward * cos - z * sin };
  });
  function fit(range: number) {
    let minX = -Infinity, maxX = Infinity, minY = -Infinity, maxY = Infinity;
    for (const point of projected) {
      const depth = range + point.z;
      if (depth <= 1) return null;
      minX = Math.max(minX, point.x - right * depth * tanX);
      maxX = Math.min(maxX, point.x - left * depth * tanX);
      minY = Math.max(minY, point.y - top * depth * tanY);
      maxY = Math.min(maxY, point.y + top * depth * tanY);
    }
    return minX <= maxX && minY <= maxY ? { rightOffset: (minX + maxX) / 2, upOffset: (minY + maxY) / 2 } : null;
  }
  let low = 280, high = 280;
  while (!fit(high)) high *= 2;
  for (let i = 0; i < 40; i++) {
    const middle = (low + high) / 2;
    if (fit(middle)) high = middle;
    else low = middle;
  }
  return { range: high, ...fit(high)!, pitch };
}

// Bearing clockwise from north, using the selected route's actual endpoints.
// A closed/zero-length route falls back to its first distinct point or north.
export function routeCameraHeading(coordinates: number[][]): number {
  const start = coordinates[0];
  if (!start) return 0;
  let end = coordinates[coordinates.length - 1];
  if (start[0] === end[0] && start[1] === end[1]) {
    end = coordinates.find(([lon, lat]) => lon !== start[0] || lat !== start[1]) ?? start;
  }
  const rad = Math.PI / 180;
  const lat1 = start[1] * rad, lat2 = end[1] * rad;
  const lonDelta = (end[0] - start[0]) * rad;
  const east = Math.sin(lonDelta) * Math.cos(lat2);
  const north = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(lonDelta);
  return (Math.atan2(east, north) + 2 * Math.PI) % (2 * Math.PI);
}

export function routeCameraTargetOffset(rightOffset: number, heading: number, upOffset = 0, pitch = ROUTE_CAMERA_PITCH) {
  const forward = upOffset * Math.sin(-pitch);
  return {
    east: rightOffset * Math.cos(heading) + forward * Math.sin(heading),
    north: -rightOffset * Math.sin(heading) + forward * Math.cos(heading),
    up: upOffset * Math.cos(-pitch),
  };
}
