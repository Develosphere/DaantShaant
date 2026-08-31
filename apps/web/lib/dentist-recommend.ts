import { API_BASE, getStoredUser } from "./portal-auth";

export type DentistPin = {
  tier: "platform" | "general";
  dentist_id: string | null;
  place_id: string | null;
  name: string;
  lat: number;
  lng: number;
  address: string;
  phone: string | null;
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
};

function authHeaders(): HeadersInit {
  const user = getStoredUser("patient");
  if (!user?.access_token) throw new Error("Please sign in as a patient");
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${user.access_token}`,
  };
}

export async function fetchDentistRecommendations(params: {
  issue: string;
  lat?: number;
  lng?: number;
  severity?: string;
  scan_id?: string;
  session_id?: string;
}): Promise<DentistRecommendResponse> {
  const res = await fetch(`${API_BASE}/portal/recommend/dentists/`, {
    method: "POST",
    headers: authHeaders(),
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
  const res = await fetch(`${API_BASE}/portal/recommend/dentists/appointments`, {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify(params),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Booking failed");
  }
  return res.json();
}
