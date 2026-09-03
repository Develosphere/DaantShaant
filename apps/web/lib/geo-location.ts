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

function formatReverseGeocodeLabel(data: any, locale: string = "en", fallback: string): string {
  if (!data) return fallback;
  const isUrdu = locale.toLowerCase().startsWith("ur");
  const namedetails = data.namedetails || {};
  const address = data.address || {};

  const placeName = isUrdu
    ? namedetails["name:ur"] || namedetails["official_name:ur"] || namedetails["short_name:ur"] || data.name || ""
    : namedetails["name:en"] || namedetails["official_name:en"] || namedetails["short_name:en"] || data.name || "";

  const suburb = address.suburb || address.neighbourhood || address.quarter || address.residential || address.city_district || "";
  const city = address.city || address.town || address.municipality || address.village || address.county || "";
  const state = address.state || address.province || address.state_district || address.region || "";
  const country = address.country || "";

  const placeAliases = new Set([
    (data.name || "").toLowerCase(),
    (namedetails["name"] || "").toLowerCase(),
    (namedetails["name:en"] || "").toLowerCase(),
    (namedetails["name:ur"] || "").toLowerCase(),
    placeName.toLowerCase(),
  ]);
  placeAliases.delete("");

  const components: string[] = [];
  if (placeName) components.push(placeName);
  if (suburb && !placeAliases.has(suburb.toLowerCase()) && !components.some((c) => c.toLowerCase() === suburb.toLowerCase())) components.push(suburb);
  if (city && !placeAliases.has(city.toLowerCase()) && !components.some((c) => c.toLowerCase() === city.toLowerCase())) components.push(city);
  if (state && !placeAliases.has(state.toLowerCase()) && !components.some((c) => c.toLowerCase() === state.toLowerCase())) components.push(state);
  if (country && !components.some((c) => c.toLowerCase() === country.toLowerCase())) components.push(country);

  if (components.length > 0) return components.join(", ");

  const raw = data.display_name || "";
  if (raw) {
    const parts = raw.split(",").map((p: string) => p.trim()).filter(Boolean);
    if (parts.length > 4) return [parts[0], parts[1], parts[parts.length - 2], parts[parts.length - 1]].join(", ");
    return raw;
  }
  return fallback;
}

/** Reverse geocode lat/lng using OpenStreetMap Nominatim or coordinate string. */
export async function reverseGeocode(lat: number, lng: number, locale: string = "en"): Promise<string> {
  const fallback = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=json&lat=${lat}&lon=${lng}&zoom=14&addressdetails=1&namedetails=1&accept-language=${encodeURIComponent(locale)}`,
      {
        headers: {
          "Accept": "application/json",
          "Accept-Language": locale,
          "User-Agent": "DaantShaant/1.0 (oral health screening platform; contact@daantshaant.app)",
        },
      }
    );
    if (!res.ok) return fallback;
    const data = await res.json();
    return formatReverseGeocodeLabel(data, locale, fallback);
  } catch {
    return fallback;
  }
}

/** Browser GPS location with human-readable label. */
export async function getCurrentLocationLabel(locale: string = "en"): Promise<PickedLocation> {
  const pos = await getCurrentPosition();
  const lat = pos.coords.latitude;
  const lng = pos.coords.longitude;
  const coordsLabel = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;

  try {
    const label = await reverseGeocode(lat, lng, locale);
    return { lat, lng, label: label || coordsLabel };
  } catch {
    return { lat, lng, label: coordsLabel };
  }
}

