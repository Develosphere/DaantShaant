/**
 * Deprecated module — Google Maps JS runtime has been removed.
 * Re-exports open browser geolocation and coordinates types.
 */

export {
  getCurrentLocationLabel,
  getCurrentPosition,
  reverseGeocode,
  type PickedLocation,
} from "./geo-location";

export async function loadGoogleMaps(): Promise<void> {
  // No-op for backward compatibility: Google Maps is no longer loaded.
  return Promise.resolve();
}
