// Third-party: OpenStreetMap / Nominatim (proxied via Orchestrator)
// Purpose: address search and location autocomplete for PK / UAE.
// No patient clinical data is transmitted; only search queries.

const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

export type AddressSuggestion = {
  place_id: string;
  label: string;
  lat?: number | null;
  lng?: number | null;
};

export async function fetchAddressSuggestions(query: string): Promise<AddressSuggestion[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  try {
    const params = new URLSearchParams({ q, limit: "6" });
    const res = await fetch(`${API_BASE}/portal/geocode/autocomplete?${params.toString()}`);
    if (!res.ok) return [];

    const data = (await res.json()) as { suggestions?: AddressSuggestion[] };
    return data.suggestions ?? [];
  } catch {
    return [];
  }
}

export async function resolveAddressSuggestion(
  label: string,
  placeId?: string,
  lat?: number | null,
  lng?: number | null
): Promise<{ lat: number; lng: number; label: string } | null> {
  if (lat != null && lng != null) {
    return { lat, lng, label };
  }

  try {
    const params = new URLSearchParams({ label });
    if (placeId) params.set("place_id", placeId);
    if (lat != null) params.set("lat", String(lat));
    if (lng != null) params.set("lng", String(lng));

    const res = await fetch(`${API_BASE}/portal/geocode/resolve?${params.toString()}`);
    if (!res.ok) return null;

    return await res.json();
  } catch {
    return null;
  }
}
