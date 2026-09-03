import { API_BASE, authorizedFetch } from "./portal-auth";

export type DentistPin = {
  tier: "platform" | "general";
  source?: "platform" | "osm" | "curated" | string;
  dentist_id: string | null;
  place_id: string | null;
  name: string;
  lat: number;
  lng: number;
  address: string;
  phone: string | null;
  website?: string | null;
  rating: number | null;
  distance_km: number;
  specialties: string[];
  is_partner: boolean;
  is_verified: boolean;
  is_best: boolean;
  rank: number;
  clinic_name: string;
  degree?: string | null;
  profile_image?: string | null;
  recommendation_reason: string;
};

export type DentistRecommendResponse = {
  session_id: string;
  issue: string;
  patient_lat: number;
  patient_lng: number;
  dentists: DentistPin[];
  search_radius_km?: number;
};

export async function fetchDentistRecommendations(params: {
  issue: string;
  lat?: number;
  lng?: number;
  severity?: string;
  scan_id?: string;
  session_id?: string;
}): Promise<DentistRecommendResponse> {
  const res = await authorizedFetch("patient", `${API_BASE}/portal/recommend/dentists/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to load dentists");
  }
  return res.json();
}

export async function bookConsultation(params: {
  dentist_id: string;
  issue: string;
  scan_id?: string;
  session_id?: string;
  message?: string;
}): Promise<{ appointment_id: string; status: string; message: string }> {
  const res = await authorizedFetch("patient", `${API_BASE}/portal/recommend/dentists/appointments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Booking failed");
  }
  return res.json();
}
