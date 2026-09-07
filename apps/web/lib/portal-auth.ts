import type { PortalRole, PortalUser, RegisterPayload } from "./portal-types";
import {
  withCrossTabLock,
  broadcastAuthEvent,
  subscribeToAuthEvents,
} from "./cross-tab-auth";

const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

let activeUser: PortalUser | null = null;

export class SessionExpiredError extends Error {
  isSessionExpired = true;
  constructor(message: string = "Session expired") {
    super(message);
    this.name = "SessionExpiredError";
  }
}

export class AuthApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.name = "AuthApiError";
    this.status = status;
  }
}

// Listen for cross-tab auth events (e.g. logout in another tab)
if (typeof window !== "undefined") {
  subscribeToAuthEvents((msg) => {
    if (msg.type === "LOGGED_OUT") {
      if (!msg.role || activeUser?.role === msg.role) {
        activeUser = null;
      }
    } else if (msg.type === "REFRESH_FAILED") {
      activeUser = null;
    }
  });
}

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
    throw new AuthApiError(formatApiError(err), res.status);
  }
  return (await res.json()) as PortalUser;
}

let refreshPromise: Promise<PortalUser | null> | null = null;

export async function refreshPortalSession(
  expectedRole?: PortalRole
): Promise<PortalUser | null> {
  // Deduplicate concurrent refresh calls within the same tab:
  // other callers await the exact same in-flight refresh promise
  if (refreshPromise) {
    const user = await refreshPromise;
    if (expectedRole && user && user.role !== expectedRole) {
      return null;
    }
    return user;
  }

  refreshPromise = (async () => {
    try {
      // Coordinate across tabs using the cross-tab mutex
      return await withCrossTabLock(async () => {
        broadcastAuthEvent("REFRESH_STARTED", { role: expectedRole });

        try {
          const res = await fetch(`${API_BASE}/portal/auth/refresh`, {
            method: "POST",
            credentials: "include",
          });

          if (res.ok) {
            const user = (await res.json()) as PortalUser;
            activeUser = user;
            broadcastAuthEvent("REFRESH_SUCCEEDED", { role: user.role });
            return user;
          }

          if (res.status === 401) {
            // Genuine session revocation or missing refresh cookie
            activeUser = null;
            broadcastAuthEvent("REFRESH_FAILED", {
              role: expectedRole,
              reason: "revoked_or_expired",
            });
            return null;
          }

          // Temporary backend failure (503 / 5xx) - do not destroy session prematurely
          console.warn(`Auth refresh received HTTP ${res.status}; preserving session`);
          return null;
        } catch (netErr) {
          // Temporary network failure - do not destroy session
          console.warn("Network error during auth refresh; preserving session:", netErr);
          return null;
        }
      });
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
  let user = getStoredUser(role);
  if (!user) {
    user = await refreshPortalSession(role);
  }
  if (!user) {
    throw new SessionExpiredError(`Please sign in as a ${role}`);
  }

  const makeRequest = (token: string) => {
    const headers = new Headers(init.headers);
    headers.set("Authorization", `Bearer ${token}`);
    return fetch(input, { ...init, headers, credentials: "include" });
  };

  let response = await makeRequest(user.access_token);
  // Single-refresh-per-request guard: only attempt ONE refresh on 401
  if (response.status === 401) {
    const refreshedUser = await refreshPortalSession(role);
    if (refreshedUser) {
      response = await makeRequest(refreshedUser.access_token);
    }
  }
  return response;
}

export async function loginPortal(
  role: PortalRole,
  email: string,
  password: string
): Promise<PortalUser> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/portal/auth/${role}/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });
  } catch (netErr) {
    throw new AuthApiError("Network connection error", 503);
  }
  const user = await readUserResponse(res);
  savePortalUser(role, user);
  broadcastAuthEvent("SESSION_UPDATED", { role });
  return user;
}

export async function registerPortal(
  role: PortalRole,
  payload: RegisterPayload
): Promise<PortalUser> {
  if (role === "admin") throw new Error("Public admin registration is disabled");
  let res: Response;
  try {
    res = await fetch(`${API_BASE}/portal/auth/${role}/register`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
  } catch (netErr) {
    throw new AuthApiError("Network connection error", 503);
  }
  const user = await readUserResponse(res);
  savePortalUser(role, user);
  broadcastAuthEvent("SESSION_UPDATED", { role });
  return user;
}

export async function fetchPortalProfile(role: PortalRole): Promise<PortalUser> {
  let user = getStoredUser(role);
  if (!user) {
    user = await refreshPortalSession(role);
  }
  if (!user) {
    throw new SessionExpiredError("Session expired");
  }

  let res: Response;
  try {
    res = await authorizedFetch(role, `${API_BASE}/portal/auth/me`);
  } catch (err: any) {
    if (err instanceof SessionExpiredError || err?.isSessionExpired) {
      throw err;
    }
    // Temporary network or fetch error: preserve current user state
    console.warn("authorizedFetch failed for /auth/me; retaining current session:", err);
    return user;
  }

  if (res.status === 200) {
    const profile = await res.json();
    const updated: PortalUser = {
      ...user,
      role: profile.role,
      user_id: profile.user_id,
      name: profile.name,
      email: profile.email,
      first_name: profile.first_name,
      last_name: profile.last_name,
      profile_image: profile.profile_image,
    };
    activeUser = updated;
    return updated;
  }

  if (res.status === 401) {
    // Attempt ONE refresh
    const refreshed = await refreshPortalSession(role);
    if (!refreshed) {
      clearPortalUser(role);
      throw new SessionExpiredError("Session expired");
    }
    // Retry /auth/me once with refreshed token
    try {
      const retryRes = await fetch(`${API_BASE}/portal/auth/me`, {
        headers: { Authorization: `Bearer ${refreshed.access_token}` },
        credentials: "include",
      });
      if (retryRes.status === 200) {
        const profile = await retryRes.json();
        const updated: PortalUser = {
          ...refreshed,
          role: profile.role,
          user_id: profile.user_id,
          name: profile.name,
          email: profile.email,
          first_name: profile.first_name,
          last_name: profile.last_name,
          profile_image: profile.profile_image,
        };
        activeUser = updated;
        return updated;
      }
      if (retryRes.status === 401) {
        clearPortalUser(role);
        throw new SessionExpiredError("Session expired");
      }
      // If retry is 503 or transient failure, keep refreshed user
      return refreshed;
    } catch {
      return refreshed;
    }
  }

  if (res.status === 503 || res.status >= 500) {
    // DB or backend temporarily unavailable: DO NOT logout, keep current authenticated client state
    console.warn(`Portal profile /auth/me returned HTTP ${res.status}; retaining active session`);
    return user;
  }

  // Any other status: if we have stored user, return it rather than destroying session
  return user;
}

export async function logoutPortal(role: PortalRole): Promise<void> {
  try {
    await fetch(`${API_BASE}/portal/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  } catch (err) {
    console.warn("Logout API call failed:", err);
  } finally {
    clearPortalUser(role);
    broadcastAuthEvent("LOGGED_OUT", { role });
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
