export const REST_RESOLUTION = 1.25;
export const MOVING_RESOLUTION = 1;
export const QUALITY_SETTLE_MS = 200;

type ResolutionViewer = {
  resolutionScale: number;
  camera: { frustum: { aspectRatio?: number; top?: number; bottom?: number } };
  resize(): void;
};

// Cesium rounds drawing-buffer dimensions to whole pixels on resize, then sets
// the camera aspect ratio from them. Preserve the projection for quality-only
// changes: otherwise odd-sized canvases produce false moveStart/moveEnd cycles
// and the viewport loaders keep aborting their own requests.
export function setRenderResolution(viewer: ResolutionViewer, scale: number): boolean {
  if (viewer.resolutionScale === scale) return false;
  const frustum = viewer.camera.frustum;
  const projection = "aspectRatio" in frustum
    ? { aspectRatio: frustum.aspectRatio }
    : { top: frustum.top, bottom: frustum.bottom };
  viewer.resolutionScale = scale;
  viewer.resize();
  Object.assign(frustum, projection);
  return true;
}

export class MapRenderQuality {
  private moving = false;
  private restoreAt = 0;
  start(): void { this.moving = true; }
  stop(now: number): void { this.moving = false; this.restoreAt = now + QUALITY_SETTLE_MS; }
  simplified(now: number): boolean { return this.moving || now < this.restoreAt; }
}
