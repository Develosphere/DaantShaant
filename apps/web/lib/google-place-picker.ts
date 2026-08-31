const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";
const EXTENDED_LIB =
  "https://ajax.googleapis.com/ajax/libs/@googlemaps/extended-component-library/0.6.11/index.min.js";

export type GmpPlace = {
  displayName?: string;
  formattedAddress?: string;
  name?: string;
  location?: { lat: number; lng: number };
};

export type GmpPlacePickerElement = HTMLElement & {
  value?: GmpPlace;
  placeholder?: string;
};

let libPromise: Promise<void> | null = null;
let loaderAttached = false;

function ensureApiLoader(): void {
  if (loaderAttached || typeof document === "undefined") return;
  if (!MAPS_KEY) return;
  if (document.querySelector("gmpx-api-loader")) {
    loaderAttached = true;
    return;
  }

  const loader = document.createElement("gmpx-api-loader");
  loader.setAttribute("key", MAPS_KEY);
  loader.setAttribute("solution-channel", "GMP_GE_mapsandplacesautocomplete_v2");
  document.body.appendChild(loader);
  loaderAttached = true;
}

/** Load Google Extended Component Library (gmpx-place-picker). */
export function loadGooglePlacePickerLibrary(): Promise<void> {
  if (typeof window === "undefined") {
    return Promise.reject(new Error("Place picker only works in the browser"));
  }
  if (!MAPS_KEY) {
    return Promise.reject(new Error("Google Maps API key not configured"));
  }

  if (customElements.get("gmpx-place-picker")) {
    ensureApiLoader();
    return Promise.resolve();
  }

  if (libPromise) return libPromise;

  libPromise = new Promise((resolve, reject) => {
    ensureApiLoader();

    const existing = document.querySelector('script[data-dantshaant-gmp-extended="1"]');
    if (existing) {
      customElements
        .whenDefined("gmpx-place-picker")
        .then(() => resolve())
        .catch(reject);
      return;
    }

    const script = document.createElement("script");
    script.type = "module";
    script.src = EXTENDED_LIB;
    script.dataset.dantshaantGmpExtended = "1";
    script.onload = () => {
      customElements
        .whenDefined("gmpx-place-picker")
        .then(() => resolve())
        .catch(reject);
    };
    script.onerror = () => {
      libPromise = null;
      reject(new Error("Failed to load Google Places picker"));
    };
    document.head.appendChild(script);
  });

  return libPromise;
}

export function placeToLocation(place: GmpPlace | undefined): {
  lat: number;
  lng: number;
  label: string;
} | null {
  if (!place?.location) return null;
  const lat = place.location.lat;
  const lng = place.location.lng;
  const label =
    place.formattedAddress || place.displayName || place.name || `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
  return { lat, lng, label };
}
