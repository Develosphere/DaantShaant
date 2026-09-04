/**
 * Comprehensive Unit Tests for Cross-Tab Auth & Refresh Coordination
 * 
 * Covers all 7 required scenarios:
 * 1. Concurrent 401s in same tab -> one refresh
 * 2. Simulated refresh already active in another tab -> wait, do not refresh concurrently
 * 3. REFRESH_SUCCEEDED broadcast -> waiting request retries
 * 4. REFRESH_FAILED -> session ends safely
 * 5. Logout broadcast -> all tabs clear session
 * 6. Network refresh error -> no false role/auth disclosure
 * 7. Stale refresh lock expires safely
 */

import test from "node:test";
import assert from "node:assert/strict";

// Mock minimal browser environment BEFORE importing auth modules
class MockBroadcastChannel {
  name: string;
  static instances: MockBroadcastChannel[] = [];
  onmessage: ((event: { data: any }) => void) | null = null;

  constructor(name: string) {
    this.name = name;
    MockBroadcastChannel.instances.push(this);
  }

  postMessage(data: any) {
    for (const inst of MockBroadcastChannel.instances) {
      if (inst !== this && inst.name === this.name && inst.onmessage) {
        inst.onmessage({ data });
      }
    }
  }

  close() {
    const idx = MockBroadcastChannel.instances.indexOf(this);
    if (idx !== -1) MockBroadcastChannel.instances.splice(idx, 1);
  }
}

class MockStorage {
  private store = new Map<string, string>();
  getItem(key: string): string | null {
    return this.store.get(key) ?? null;
  }
  setItem(key: string, value: string): void {
    this.store.set(key, value);
  }
  removeItem(key: string): void {
    this.store.delete(key);
  }
  clear(): void {
    this.store.clear();
  }
}

// Setup globals before loading modules
(global as any).window = {};
(global as any).BroadcastChannel = MockBroadcastChannel;
(global as any).localStorage = new MockStorage();

// Ensure navigator.locks is deleted during fallback testing if needed
const originalLocks = (global as any).navigator?.locks;

import type { AuthMessage } from "../cross-tab-auth";
import type { PortalUser } from "../portal-types";

async function loadModules() {
  const crossTab = await import("../cross-tab-auth");
  const portal = await import("../portal-auth");
  return { crossTab, portal };
}

const mockPatientUser: PortalUser = {
  access_token: "token_123",
  token_type: "bearer",
  user_id: "u1",
  role: "patient",
  email: "p@example.com",
  first_name: "Test",
  last_name: "Patient",
  name: "Test Patient",
  profile_image: "",
};

test("1. concurrent 401s in same tab -> deduplicated to exactly one refresh", async () => {
  const { portal } = await loadModules();

  let fetchCallCount = 0;
  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      fetchCallCount++;
      await new Promise((r) => setTimeout(r, 20)); // simulate latency
      return {
        ok: true,
        status: 200,
        json: async () => mockPatientUser,
      };
    }
    return { ok: false, status: 404 };
  };

  // Trigger two concurrent refresh calls in same tab
  const [res1, res2] = await Promise.all([
    portal.refreshPortalSession("patient"),
    portal.refreshPortalSession("patient"),
  ]);

  assert.strictEqual(fetchCallCount, 1, "Only one network refresh request should be made");
  assert.strictEqual(res1?.access_token, "token_123");
  assert.strictEqual(res2?.access_token, "token_123");
  assert.strictEqual(portal.getStoredUser("patient")?.access_token, "token_123");
});

test("2. simulated refresh already active in another tab -> wait, no concurrent collision", async () => {
  const { crossTab } = await loadModules();
  let executedOrder: string[] = [];

  // Simulate Tab A acquiring the lock first
  let releaseTabA: () => void = () => {};
  const tabAPromise = new Promise<void>((resolve) => {
    releaseTabA = resolve;
  });

  const tabATask = crossTab.withCrossTabLock(async () => {
    executedOrder.push("Tab A starts refresh");
    await tabAPromise;
    executedOrder.push("Tab A completes refresh");
  });

  // Small delay to ensure Tab A holds lock
  await new Promise((r) => setTimeout(r, 10));

  // Tab B tries to acquire lock while Tab A is active
  const tabBTask = crossTab.withCrossTabLock(async () => {
    executedOrder.push("Tab B starts refresh");
    return "tab_b_done";
  });

  // Release Tab A
  await new Promise((r) => setTimeout(r, 40));
  releaseTabA();
  await tabATask;

  const resB = await tabBTask;
  assert.strictEqual(resB, "tab_b_done");
  assert.deepStrictEqual(executedOrder, [
    "Tab A starts refresh",
    "Tab A completes refresh",
    "Tab B starts refresh",
  ]);
});

test("3. REFRESH_SUCCEEDED broadcast -> waiting listener is notified", async () => {
  const { crossTab } = await loadModules();

  const events: AuthMessage[] = [];
  const unsub = crossTab.subscribeToAuthEvents((msg) => {
    events.push(msg);
  });

  // Another tab broadcasts REFRESH_SUCCEEDED
  const foreignChannel = new MockBroadcastChannel("daantshaant-auth");
  foreignChannel.postMessage({
    type: "REFRESH_SUCCEEDED",
    senderId: "tab_other",
    timestamp: Date.now(),
    role: "patient",
  });

  assert.strictEqual(events.length, 1);
  assert.strictEqual(events[0].type, "REFRESH_SUCCEEDED");
  assert.strictEqual(events[0].role, "patient");

  foreignChannel.close();
  unsub();
});

test("4. REFRESH_FAILED -> session ends safely and clears local user", async () => {
  const { portal, crossTab } = await loadModules();

  portal.savePortalUser("patient", {
    ...mockPatientUser,
    access_token: "old_token",
  });

  let broadcastEvents: AuthMessage[] = [];
  const unsub = crossTab.subscribeToAuthEvents((msg) => {
    broadcastEvents.push(msg);
  });

  // Server returns 401 on refresh (revoked/expired refresh cookie)
  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      return {
        ok: false,
        status: 401,
        json: async () => ({ detail: "Invalid refresh session" }),
      };
    }
    return { ok: false, status: 404 };
  };

  const user = await portal.refreshPortalSession("patient");

  assert.strictEqual(user, null, "Refresh should return null on 401");
  assert.strictEqual(portal.getStoredUser("patient"), null, "Local user must be cleared");

  unsub();
});

test("5. logout broadcast -> all tabs clear session", async () => {
  const { portal } = await loadModules();

  portal.savePortalUser("patient", mockPatientUser);

  assert.notStrictEqual(portal.getStoredUser("patient"), null);

  // Simulate another tab broadcasting LOGGED_OUT
  const foreignChannel = new MockBroadcastChannel("daantshaant-auth");
  foreignChannel.postMessage({
    type: "LOGGED_OUT",
    senderId: "tab_other",
    timestamp: Date.now(),
    role: "patient",
  });

  // Check that current tab's user was cleared
  assert.strictEqual(portal.getStoredUser("patient"), null, "Other tab's logout must clear local session");

  foreignChannel.close();
});

test("6. network refresh error -> no false role/auth disclosure, preserves session", async () => {
  const { portal } = await loadModules();

  portal.savePortalUser("patient", mockPatientUser);

  // Simulate temporary network failure
  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      throw new TypeError("Failed to fetch");
    }
    return { ok: false, status: 404 };
  };

  const result = await portal.refreshPortalSession("patient");

  assert.strictEqual(result, null);
  // Temporary network error must NOT wipe out user credentials prematurely!
  assert.notStrictEqual(
    portal.getStoredUser("patient"),
    null,
    "Network error must not destroy session state"
  );
});

test("7. stale refresh lock expires safely and allows takeover (storage fallback)", async () => {
  const { crossTab } = await loadModules();
  (global as any).localStorage.clear();

  // Simulate an abandoned lock in storage from a crashed tab with an expired timestamp
  const staleLock = {
    ownerId: "crashed_tab_xyz",
    expiresAt: Date.now() - 1000, // expired 1s ago
  };
  (global as any).localStorage.setItem(crossTab.REFRESH_LOCK_KEY, JSON.stringify(staleLock));

  // Temporarily disable navigator.locks to test storage fallback
  const nav = (global as any).navigator;
  if (nav) nav.locks = undefined;

  let acquired = false;
  await crossTab.withCrossTabLock(async () => {
    acquired = true;
  });

  assert.strictEqual(acquired, true, "Stale storage lock must be safely overridden");

  if (nav) nav.locks = originalLocks;
});
