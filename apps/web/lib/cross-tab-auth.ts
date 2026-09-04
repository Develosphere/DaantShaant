/**
 * Cross-Tab Session & Refresh Coordination for DaantShaant
 * 
 * Solves single-use refresh token rotation race across multiple browser tabs:
 * - Only ONE tab acquires the refresh lock and rotates the cookie.
 * - Other tabs wait for the active refresh to complete.
 * - BroadcastChannel notifies tabs of refresh start/success/failure and logout.
 * - NEVER broadcasts access tokens or refresh tokens (cookie-only security).
 */

import type { PortalRole, PortalUser } from "./portal-types";

export const AUTH_CHANNEL_NAME = "daantshaant-auth";
export const REFRESH_LOCK_KEY = "daantshaant_refresh_lock";
export const LOCK_STALE_MS = 8000; // Stale lock timeout (8s)

export type AuthEventType =
  | "REFRESH_STARTED"
  | "REFRESH_SUCCEEDED"
  | "REFRESH_FAILED"
  | "LOGGED_OUT"
  | "SESSION_UPDATED";

export interface AuthMessage {
  type: AuthEventType;
  senderId: string;
  timestamp: number;
  role?: PortalRole;
  reason?: string;
}

// Generate unique tab identifier
export const currentTabId =
  typeof window !== "undefined"
    ? Math.random().toString(36).substring(2, 9) + "_" + Date.now().toString(36)
    : "ssr";

let authChannel: BroadcastChannel | null = null;

function getAuthChannel(): BroadcastChannel | null {
  if (typeof window === "undefined" || typeof BroadcastChannel === "undefined") {
    return null;
  }
  if (!authChannel) {
    try {
      authChannel = new BroadcastChannel(AUTH_CHANNEL_NAME);
    } catch {
      authChannel = null;
    }
  }
  return authChannel;
}

/**
 * Broadcast an authentication event to all other tabs.
 */
export function broadcastAuthEvent(
  type: AuthEventType,
  payload?: { role?: PortalRole; reason?: string }
): void {
  const channel = getAuthChannel();
  if (!channel) return;
  try {
    const msg: AuthMessage = {
      type,
      senderId: currentTabId,
      timestamp: Date.now(),
      role: payload?.role,
      reason: payload?.reason,
    };
    channel.postMessage(msg);
  } catch {
    // Graceful fallback if broadcast fails
  }
}

export type AuthMessageListener = (msg: AuthMessage) => void;
const listeners = new Set<AuthMessageListener>();

if (typeof window !== "undefined") {
  const channel = getAuthChannel();
  if (channel) {
    channel.onmessage = (event) => {
      const msg = event.data as AuthMessage;
      if (!msg || msg.senderId === currentTabId) return;
      listeners.forEach((listener) => {
        try {
          listener(msg);
        } catch (e) {
          console.error("Error in auth message listener:", e);
        }
      });
    };
  }
}

/**
 * Subscribe to cross-tab auth events. Returns unsubscribe function.
 */
export function subscribeToAuthEvents(listener: AuthMessageListener): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

/**
 * Fallback localStorage-based lock implementation with stale takeover.
 */
interface StorageLockRecord {
  ownerId: string;
  expiresAt: number;
}

async function acquireStorageLock(timeoutMs = 6000): Promise<() => void> {
  const start = Date.now();
  const pollInterval = 40;

  while (Date.now() - start < timeoutMs) {
    const now = Date.now();
    let lockRecord: StorageLockRecord | null = null;
    try {
      const raw = localStorage.getItem(REFRESH_LOCK_KEY);
      if (raw) lockRecord = JSON.parse(raw);
    } catch {
      lockRecord = null;
    }

    // If lock is held by another active tab and not expired, wait
    if (lockRecord && lockRecord.ownerId !== currentTabId && lockRecord.expiresAt > now) {
      await new Promise((r) => setTimeout(r, pollInterval));
      continue;
    }

    // Try to acquire lock
    const newRecord: StorageLockRecord = {
      ownerId: currentTabId,
      expiresAt: now + LOCK_STALE_MS,
    };
    try {
      localStorage.setItem(REFRESH_LOCK_KEY, JSON.stringify(newRecord));
      // Verify our write was not overwritten
      const checkRaw = localStorage.getItem(REFRESH_LOCK_KEY);
      const checkRecord = checkRaw ? JSON.parse(checkRaw) : null;
      if (checkRecord?.ownerId === currentTabId) {
        // Acquired lock! Return release callback
        return () => {
          try {
            const current = localStorage.getItem(REFRESH_LOCK_KEY);
            if (current) {
              const parsed = JSON.parse(current);
              if (parsed.ownerId === currentTabId) {
                localStorage.removeItem(REFRESH_LOCK_KEY);
              }
            }
          } catch {}
        };
      }
    } catch {}

    await new Promise((r) => setTimeout(r, pollInterval));
  }

  // If timed out, proceed anyway with safety warning to not permanently block tab
  console.warn("Cross-tab lock acquisition timed out; continuing with fallback");
  return () => {
    try {
      localStorage.removeItem(REFRESH_LOCK_KEY);
    } catch {}
  };
}

/**
 * Execute an async operation with a cross-tab lock.
 * Uses navigator.locks when available, with bulletproof localStorage fallback.
 */
export async function withCrossTabLock<T>(fn: () => Promise<T>): Promise<T> {
  // If in SSR or no window, execute directly
  if (typeof window === "undefined") {
    return await fn();
  }

  // Primary: Web Locks API
  if (typeof navigator !== "undefined" && navigator.locks?.request) {
    return await new Promise<T>((resolve, reject) => {
      navigator.locks.request(
        "daantshaant_refresh_mutex",
        { mode: "exclusive" },
        async () => {
          try {
            const res = await fn();
            resolve(res);
          } catch (err) {
            reject(err);
          }
        }
      );
    });
  }

  // Fallback: localStorage mutex
  const release = await acquireStorageLock();
  try {
    return await fn();
  } finally {
    release();
  }
}
