// Dim only the basemap, not UI, route lines or facility markers.
export function mapLighting(night: boolean) {
  return night
    ? { brightness: 0.26, saturation: 0.45, contrast: 1.08, lightSize: 38,
        background: "#030812", ground: "#07111e" }
    : { brightness: 0.68, saturation: 0.78, contrast: 1.04, lightSize: 30,
        background: "#071a2b", ground: "#17303b" };
}

// One shared atlas texture, not thousands of lights or animated post-processes.
// Symbolic glow only: this is not a measured illumination radius.
export const STREETLIGHT_GLOW_IMAGE = `data:image/svg+xml,${encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
  + '<defs><radialGradient id="glow"><stop offset="0" stop-color="#fffbe4" stop-opacity="1"/>'
  + '<stop offset="0.18" stop-color="#fff2ad" stop-opacity="0.95"/>'
  + '<stop offset="0.36" stop-color="#ffda72" stop-opacity="0.52"/>'
  + '<stop offset="0.65" stop-color="#ffc449" stop-opacity="0.17"/>'
  + '<stop offset="1" stop-color="#ffbd44" stop-opacity="0"/></radialGradient></defs>'
  + '<circle cx="32" cy="32" r="31" fill="url(#glow)"/>'
  + '<circle cx="32" cy="32" r="5" fill="#fffef2"/>'
  + '</svg>',
)}`;
