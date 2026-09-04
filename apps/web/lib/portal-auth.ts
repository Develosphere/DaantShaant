import type { PortalRole, PortalUser, RegisterPayload } from "./portal-types";

const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

let activeUser: PortalUser | null = null;

export function getStoredUser(role: PortalRole): PortalUser | null {
  return activeUser?.role === role ? activeUser : null;
}

export function getActivePortalRole(): PortalRole | null {
  return activeUser?.role ?? null;
}

export function getAccessToken(role: PortalRole): string | null {
  return getStoredUser(role)?.access_token ?? null;
}

export function clearAllPortalSessions() {
  activeUser = null;
}

export function savePortalUser(_role: PortalRole, user: PortalUser) {
  activeUser = user;
}

export function clearPortalUser(role: PortalRole) {
  if (activeUser?.role === role) activeUser = null;
}

async function readUserResponse(res: Response): Promise<PortalUser> {
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(formatApiError(err));
  }
  return (await res.json()) as PortalUser;
}

let refreshPromise: Promise<PortalUser | null> | null = null;

export async function refreshPortalSession(
  expectedRole?: PortalRole
): Promise<PortalUser | null> {
  if (refreshPromise) {
    const user = await refreshPromise;
    if (expectedRole && user && user.role !== expectedRole) {
      return null;
    }
    return user;
  }

  refreshPromise = (async () => {
    try {
      const res = await fetch(`${API_BASE}/portal/auth/refresh`, {
        method: "POST",
        credentials: "include",
      });
      if (!res.ok) {
        activeUser = null;
        return null;
      }
      const user = (await res.json()) as PortalUser;
      activeUser = user;
      return user;
    } catch {
      return null;
    } finally {
      refreshPromise = null;
    }
  })();

  const user = await refreshPromise;
  if (expectedRole && user && user.role !== expectedRole) {
    return null;
  }
  return user;
}

export async function authorizedFetch(
  role: PortalRole,
  input: RequestInfo | URL,
  init: RequestInit = {}
): Promise<Response> {
  let user = getStoredUser(role) ?? (await refreshPortalSession(role));
  if (!user) throw new Error(`Please sign in as a ${role}`);

  const makeRequest = (token: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers, credentials: "include" });
  };

  let response = await makeRequest(user.access_token);
  if (response.status === 401) {
    user = await refreshPortalSession(role);
    if (user) response = await makeRequest(user.access_token);
  }
  return response;
}

export async function loginPortal(
  role: PortalRole,
  email: string,
  password: string
): Promise<PortalUser> {
  const res = await fetch(`${API_BASE}/portal/auth/${role}/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ email, password }),
  });
  const user = await readUserResponse(res);
  savePortalUser(role, user);
  return user;
}

export async function registerPortal(
  role: PortalRole,
  payload: RegisterPayload
): Promise<PortalUser> {
  if (role === "admin") throw new Error("Public admin registration is disabled");
  const res = await fetch(`${API_BASE}/portal/auth/${role}/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
    body: JSON.stringify(payload),
  });
  const user = await readUserResponse(res);
  savePortalUser(role, user);
  return user;
}

export async function fetchPortalProfile(role: PortalRole): Promise<PortalUser> {
  const user = getStoredUser(role) ?? (await refreshPortalSession(role));
  if (!user) throw new Error("Session expired");
  const res = await authorizedFetch(role, `${API_BASE}/portal/auth/me`);
  if (!res.ok) throw new Error("Session expired");
  const profile = await res.json();
  const updated = {
    ...user,
    role: profile.role,
    user_id: profile.user_id,
    name: profile.name,
    email: profile.email,
    first_name: profile.first_name,
    last_name: profile.last_name,
    profile_image: profile.profile_image,
  } as PortalUser;
  activeUser = updated;
  return updated;
}

export async function logoutPortal(role: PortalRole): Promise<void> {
  try {
    await fetch(`${API_BASE}/portal/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } finally {
    clearPortalUser(role);
  }
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
      .map((item) =>
        typeof item === "object" && item && "msg" in item ? String(item.msg) : String(item)
      )
      .join(", ");
  }
  return "Request failed";
}

export { API_BASE };
