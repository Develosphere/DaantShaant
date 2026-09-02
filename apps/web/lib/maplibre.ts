// Third-party: MapLibre GL JS
// Purpose: client-side interactive dentist map rendering.
// No patient clinical data is transmitted; only map coordinates.

// Third-party: OpenFreeMap
// Purpose: vector map tiles and Liberty style source for MapLibre rendering.

import * as maplibregl from "maplibre-gl";

export const OPENFREEMAP_LIBERTY_STYLE = "https://tiles.openfreemap.org/styles/liberty";

/** Load MapLibre stylesheet dynamically if not already injected */
export function ensureMapLibreCSS(): void {
  if (typeof document === "undefined") return;
  if (document.querySelector('link[data-maplibre-css="1"]')) return;

  const link = document.createElement("link");
  link.rel = "stylesheet";
  link.href = "https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css";
  link.dataset.maplibreCss = "1";
  document.head.appendChild(link);
}

export { maplibregl };
