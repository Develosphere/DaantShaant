// Third-party: OpenStreetMap / Nominatim
// Purpose: client-side reverse geocoding of coordinates to readable location label.
// No patient clinical data is transmitted; only geographic coordinates.

export type PickedLocation = {
  lat: number;
  lng: number;
  label: string;
};

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

/** Browser GPS only via navigator.geolocation. */
export function getCurrentPosition(): Promise<GeolocationPosition> {
  const geoPromise = new Promise<GeolocationPosition>((resolve, reject) => {
    if (typeof window === "undefined" || !navigator.geolocation) {
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

/** Reverse geocode lat/lng using OpenStreetMap Nominatim or coordinate string. */
export async function reverseGeocode(lat: number, lng: number): Promise<string> {
  const fallback = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=14`,
      {
        headers: {
          "Accept": "application/json",
        },
      }
    );
    if (!res.ok) return fallback;
    const data = (await res.json()) as { display_name?: string };
    return data.display_name || fallback;
  } catch {
    return fallback;
  }
}

/** Browser GPS location with human-readable label. */
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
