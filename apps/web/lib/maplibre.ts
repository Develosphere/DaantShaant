// Third-party: MapLibre GL JS
// Purpose: client-side interactive dentist map rendering.
// No patient clinical data is transmitted; only map coordinates.

// Third-party: OpenFreeMap
// Purpose: vector map tiles and Liberty style source for MapLibre rendering.

import * as maplibregl from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";

export const OSM_RASTER_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
      tileSize: 256,
      attribution: "© OpenStreetMap contributors",
      maxzoom: 19,
    },
  },
  layers: [
    {
      id: "osm-tiles",
      type: "raster",
      source: "osm",
      minzoom: 0,
      maxzoom: 19,
    },
  ],
};

/** Ensure MapLibre stylesheet is present (bundled import is primary, fallback verifies element) */
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
