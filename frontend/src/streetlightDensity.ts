export type DensityPoint = readonly [longitude: number, latitude: number];

export type DensityBounds = {
  west: number;
  south: number;
  east: number;
  north: number;
};

export type StreetlightDensityTexture = {
  bounds: DensityBounds;
  dataUrl: string;
  width: number;
  height: number;
};

const DEFAULT_CANVAS_SIZE = 768;
const DEFAULT_KERNEL_RADIUS = 18;
const MINIMUM_SPAN_DEGREES = 0.001;
const DENSITY_ALPHA_THRESHOLD = 24;
const DENSITY_ALPHA_MAXIMUM = 96;

function finitePoint(point: DensityPoint): boolean {
  return Number.isFinite(point[0]) && Number.isFinite(point[1]);
}

export function streetlightDensityBounds(
  points: DensityPoint[],
  paddingRatio = 0.04,
): DensityBounds | null {
  const valid = points.filter(finitePoint);
  if (valid.length === 0) return null;

  const longitudes = valid.map(([longitude]) => longitude);
  const latitudes = valid.map(([, latitude]) => latitude);
  const west = Math.min(...longitudes);
  const east = Math.max(...longitudes);
  const south = Math.min(...latitudes);
  const north = Math.max(...latitudes);
  const longitudePadding = Math.max((east - west) * paddingRatio, MINIMUM_SPAN_DEGREES);
  const latitudePadding = Math.max((north - south) * paddingRatio, MINIMUM_SPAN_DEGREES);

  return {
    west: Math.max(-180, west - longitudePadding),
    south: Math.max(-90, south - latitudePadding),
    east: Math.min(180, east + longitudePadding),
    north: Math.min(90, north + latitudePadding),
  };
}

export function densityCanvasPosition(
  point: DensityPoint,
  bounds: DensityBounds,
  width: number,
  height: number,
): { x: number; y: number } {
  const longitudeSpan = Math.max(bounds.east - bounds.west, Number.EPSILON);
  const latitudeSpan = Math.max(bounds.north - bounds.south, Number.EPSILON);
  return {
    x: ((point[0] - bounds.west) / longitudeSpan) * width,
    // Canvas Y grows downward while latitude grows northward.
    y: ((bounds.north - point[1]) / latitudeSpan) * height,
  };
}

export function densityDisplayAlpha(sourceAlpha: number): number {
  if (!Number.isFinite(sourceAlpha) || sourceAlpha <= DENSITY_ALPHA_THRESHOLD) return 0;
  return Math.min(
    DENSITY_ALPHA_MAXIMUM,
    Math.round((sourceAlpha - DENSITY_ALPHA_THRESHOLD) * 1.35),
  );
}

function createGlowKernel(radius: number): HTMLCanvasElement {
  const kernel = document.createElement("canvas");
  const diameter = radius * 2;
  kernel.width = diameter;
  kernel.height = diameter;
  const context = kernel.getContext("2d");
  if (!context) return kernel;

  const gradient = context.createRadialGradient(radius, radius, 0, radius, radius, radius);
  gradient.addColorStop(0, "rgba(255, 253, 232, 0.05)");
  gradient.addColorStop(0.28, "rgba(255, 242, 190, 0.025)");
  gradient.addColorStop(0.65, "rgba(255, 225, 148, 0.009)");
  gradient.addColorStop(1, "rgba(255, 220, 140, 0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, diameter, diameter);
  return kernel;
}

/**
 * Rasterize streetlight locations once so Cesium can reuse one transparent image.
 * This is a relative location-density visualization, not measured illuminance.
 */
export function createStreetlightDensityTexture(
  points: DensityPoint[],
  size = DEFAULT_CANVAS_SIZE,
): StreetlightDensityTexture | null {
  const valid = points.filter(finitePoint);
  const bounds = streetlightDensityBounds(valid);
  if (!bounds || typeof document === "undefined") return null;

  const canvas = document.createElement("canvas");
  canvas.width = size;
  canvas.height = size;
  const context = canvas.getContext("2d");
  if (!context) return null;

  const kernelRadius = Math.max(10, Math.round(DEFAULT_KERNEL_RADIUS * (size / DEFAULT_CANVAS_SIZE)));
  const kernel = createGlowKernel(kernelRadius);
  context.globalCompositeOperation = "lighter";
  for (const point of valid) {
    const { x, y } = densityCanvasPosition(point, bounds, size, size);
    context.drawImage(kernel, x - kernelRadius, y - kernelRadius);
  }

  // Remove isolated/low-density glow and retain only meaningful overlaps.
  // A capped alpha keeps dense cells from obscuring the basemap and route lines.
  const image = context.getImageData(0, 0, size, size);
  for (let offset = 0; offset < image.data.length; offset += 4) {
    const alpha = densityDisplayAlpha(image.data[offset + 3]);
    if (alpha === 0) {
      image.data[offset] = 0;
      image.data[offset + 1] = 0;
      image.data[offset + 2] = 0;
      image.data[offset + 3] = 0;
      continue;
    }
    image.data[offset] = 255;
    image.data[offset + 1] = 246;
    image.data[offset + 2] = 210;
    image.data[offset + 3] = alpha;
  }
  context.globalCompositeOperation = "source-over";
  context.putImageData(image, 0, 0);

  return {
    bounds,
    dataUrl: canvas.toDataURL("image/png"),
    width: size,
    height: size,
  };
}
