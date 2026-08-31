const MAPS_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

declare global {
  interface Window {
    google?: typeof google;
    initDantShaantMap?: () => void;
  }
}

let loadPromise: Promise<void> | null = null;

function withTimeout<T>(promise: Promise<T>, ms: number, message: string): Promise<T> {
  return new Promise((resolve, reject) => {
    const timer = window.setTimeout(() => reject(new Error(message)), ms);
    promise
      .then((value) => {
        window.clearTimeout(timer);
        resolve(value);
      })
      .catch((err) => {
        window.clearTimeout(timer);
        reject(err);
      });
  });
}

/** Load Google Maps JS + Places library (single script tag). */
export function loadGoogleMaps(): Promise<void> {
  if (typeof window === "undefined") return Promise.reject(new Error("Maps only in browser"));
  if (window.google?.maps?.places) return Promise.resolve();
  if (!MAPS_KEY) return Promise.reject(new Error("Google Maps API key not configured"));

  if (loadPromise) {
    return withTimeout(
      loadPromise,
      20000,
      "Google Maps took too long to load — type your address instead"
    ).catch((err) => {
      loadPromise = null;
      throw err;
    });
  }

  const promise = new Promise<void>((resolve, reject) => {
    const finish = (ok: boolean) => {
      if (ok && window.google?.maps) resolve();
      else reject(new Error("Google Maps failed to initialize"));
    };

    const existing = document.querySelector('script[data-dantshaant-maps="1"]');
    if (existing) {
      if (window.google?.maps) {
        finish(true);
        return;
      }
      const onLoad = () => finish(true);
      const onError = () => finish(false);
      existing.addEventListener("load", onLoad, { once: true });
      existing.addEventListener("error", onError, { once: true });
      return;
    }

    window.initDantShaantMap = () => finish(true);
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${MAPS_KEY}&libraries=places&callback=initDantShaantMap`;
    script.async = true;
    script.defer = true;
    script.dataset.dantshaantMaps = "1";
    script.onerror = () => finish(false);
    document.head.appendChild(script);
  });

  loadPromise = promise;

  return withTimeout(
    promise,
    20000,
    "Google Maps took too long to load — type your address instead"
  ).catch((err) => {
    loadPromise = null;
    throw err;
  });
}

export type PickedLocation = {
  lat: number;
  lng: number;
  label: string;
};

export async function reverseGeocode(lat: number, lng: number): Promise<string> {
  const fallback = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
  try {
    await loadGoogleMaps();
    const geocoder = new google.maps.Geocoder();
    return await withTimeout(
      new Promise<string>((resolve) => {
        geocoder.geocode({ location: { lat, lng } }, (results, status) => {
          if (status === "OK" && results?.[0]) resolve(results[0].formatted_address);
          else resolve(fallback);
        });
      }),
      10000,
      "reverse-geocode-timeout"
    );
  } catch {
    return fallback;
  }
}

function geolocationErrorMessage(code: number): string {
  switch (code) {
    case 1:
      return "Location access was denied. Allow location in your browser settings, or type your address.";
    case 2:
      return "Your device could not determine a location. Type your city or address instead.";
    case 3:
      return "Location request timed out. Type your address or try GPS again.";
    default:
      return "Could not get your location. Type your address instead.";
  }
}

export function getCurrentPosition(): Promise<GeolocationPosition> {
  const geoPromise = new Promise<GeolocationPosition>((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is not supported on this device — type your address instead"));
      return;
    }

    navigator.geolocation.getCurrentPosition(
      resolve,
      (err) => reject(new Error(geolocationErrorMessage(err.code))),
      {
        enableHighAccuracy: false,
        timeout: 12000,
        maximumAge: 120000,
      }
    );
  });

  return withTimeout(
    geoPromise,
    14000,
    "Location request timed out. Type your address instead."
  );
}

/** Browser GPS only — does not require Google Maps. */
export async function getCurrentLocationLabel(): Promise<PickedLocation> {
  const pos = await getCurrentPosition();
  const lat = pos.coords.latitude;
  const lng = pos.coords.longitude;
  const coordsLabel = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

  try {
    const label = await reverseGeocode(lat, lng);
    return { lat, lng, label: label || coordsLabel };
  } catch {
    return { lat, lng, label: coordsLabel };
  }
}
