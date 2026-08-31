import type { PortalRole, PortalUser, RegisterPayload } from "./portal-types";

const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

const ALL_ROLES: PortalRole[] = ["patient", "dentist", "admin"];

function storageKey(role: PortalRole) {
  return `dantshaant_portal_${role}`;
}

export function getStoredUser(role: PortalRole): PortalUser | null {
  if (typeof window === "undefined") return null;
  const raw = localStorage.getItem(storageKey(role));
  if (!raw) return null;
  try {
    return JSON.parse(raw) as PortalUser;
  } catch {
    return null;
  }
}

export function getActivePortalRole(): PortalRole | null {
  for (const role of ALL_ROLES) {
    if (getStoredUser(role)) return role;
  }
  return null;
}

export function clearAllPortalSessions() {
  for (const role of ALL_ROLES) {
    clearPortalUser(role);
  }
}

export function savePortalUser(role: PortalRole, user: PortalUser) {
  for (const r of ALL_ROLES) {
    if (r !== role) localStorage.removeItem(storageKey(r));
  }
  localStorage.setItem(storageKey(role), JSON.stringify(user));
}

export function clearPortalUser(role: PortalRole) {
  localStorage.removeItem(storageKey(role));
}

export async function loginPortal(
  role: PortalRole,
  email: string,
  password: string
): Promise<PortalUser> {
  const res = await fetch(`${API_BASE}/portal/auth/${role}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(formatApiError(err));
  }
  const user = (await res.json()) as PortalUser;
  savePortalUser(role, user);
  return user;
}

export async function registerPortal(
  role: PortalRole,
  payload: RegisterPayload
): Promise<PortalUser> {
  const res = await fetch(`${API_BASE}/portal/auth/${role}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(formatApiError(err));
  }
  const user = (await res.json()) as PortalUser;
  savePortalUser(role, user);
  return user;
}

export async function fetchPortalProfile(token: string): Promise<PortalUser> {
  const res = await fetch(`${API_BASE}/portal/auth/me`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) throw new Error("Session expired");
  const profile = await res.json();
  return {
    access_token: token,
    token_type: "bearer",
    role: profile.role,
    user_id: profile.user_id,
    name: profile.name,
    email: profile.email,
    first_name: profile.first_name,
    last_name: profile.last_name,
    profile_image: profile.profile_image,
  };
}

export function readImageAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });
}

function formatApiError(body: { detail?: unknown }): string {
  const detail = body.detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => (typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)))
      .join(", ");
  }
  return "Request failed";
}

export { API_BASE };
