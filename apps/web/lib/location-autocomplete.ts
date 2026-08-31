const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
const GOOGLE_KEY = process.env.NEXT_PUBLIC_GOOGLE_MAPS_API_KEY ?? "";

export type AddressSuggestion = {
  place_id: string;
  label: string;
  lat?: number | null;
  lng?: number | null;
};

async function fetchGoogleSuggestions(query: string): Promise<AddressSuggestion[]> {
  if (!GOOGLE_KEY) return [];

  try {
    const res = await fetch("https://places.googleapis.com/v1/places:autocomplete", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": GOOGLE_KEY,
      },
      body: JSON.stringify({
        input: query,
        includedRegionCodes: ["pk", "ae"],
      }),
    });
    if (!res.ok) return [];

    const data = (await res.json()) as {
      suggestions?: Array<{
        placePrediction?: { placeId?: string; text?: { text?: string } };
      }>;
    };

    return (data.suggestions ?? [])
      .map((item) => {
        const pred = item.placePrediction;
        const label = pred?.text?.text ?? "";
        const place_id = pred?.placeId ?? "";
        return label ? { place_id, label } : null;
      })
      .filter((x): x is AddressSuggestion => x !== null);
  } catch {
    return [];
  }
}

async function fetchBackendSuggestions(query: string): Promise<AddressSuggestion[]> {
  const params = new URLSearchParams({ q: query, limit: "6" });
  const res = await fetch(`${API_BASE}/portal/geocode/autocomplete?${params.toString()}`);
  if (!res.ok) return [];

  const data = (await res.json()) as { suggestions?: AddressSuggestion[] };
  return data.suggestions ?? [];
}

export async function fetchAddressSuggestions(query: string): Promise<AddressSuggestion[]> {
  const q = query.trim();
  if (q.length < 2) return [];

  const google = await fetchGoogleSuggestions(q);
  if (google.length > 0) return google;

  return fetchBackendSuggestions(q);
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

  if (placeId && GOOGLE_KEY && !placeId.startsWith("osm:")) {
    try {
      const pid = placeId.replace(/^places\//, "");
      const res = await fetch(`https://places.googleapis.com/v1/places/${encodeURIComponent(pid)}`, {
        headers: {
          "X-Goog-Api-Key": GOOGLE_KEY,
          "X-Goog-FieldMask": "location,formattedAddress",
        },
      });
      if (res.ok) {
        const data = (await res.json()) as {
          location?: { latitude?: number; longitude?: number };
          formattedAddress?: string;
        };
        const glat = data.location?.latitude;
        const glng = data.location?.longitude;
        if (glat != null && glng != null) {
          return {
            lat: glat,
            lng: glng,
            label: data.formattedAddress || label,
          };
        }
      }
    } catch {
      /* fall through to backend */
    }
  }

  const params = new URLSearchParams({ label });
  if (placeId) params.set("place_id", placeId);
  if (lat != null) params.set("lat", String(lat));
  if (lng != null) params.set("lng", String(lng));

  const res = await fetch(`${API_BASE}/portal/geocode/resolve?${params.toString()}`);
  if (!res.ok) return null;

  return res.json();
}
