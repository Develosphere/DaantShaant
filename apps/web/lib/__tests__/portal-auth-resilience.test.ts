/**
 * Unit Tests for Portal Auth Resilience:
 * - /auth/me 503 does NOT logout (preserves current authenticated user)
 * - refresh 503 does NOT logout (preserves session)
 * - refresh 401 DOES logout
 * - only one refresh request for simultaneous 401s
 * - no refresh recursion
 * - login 503 throws AuthApiError with status 503
 */

import test from "node:test";
import assert from "node:assert/strict";

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

(global as any).window = {};
(global as any).BroadcastChannel = MockBroadcastChannel;
(global as any).localStorage = new MockStorage();

import type { PortalUser } from "../portal-types";
import {
  savePortalUser,
  getStoredUser,
  clearAllPortalSessions,
  fetchPortalProfile,
  refreshPortalSession,
  authorizedFetch,
  loginPortal,
  SessionExpiredError,
  AuthApiError,
} from "../portal-auth";

const testUser: PortalUser = {
  access_token: "mock-token-abc",
  token_type: "bearer",
  role: "patient",
  user_id: "u-123",
  name: "Jane Doe",
  email: "jane@example.com",
  first_name: "Jane",
  last_name: "Doe",
  profile_image: "",
};

test("1. /auth/me 503 does NOT logout and preserves existing authenticated user state", async () => {
  clearAllPortalSessions();
  savePortalUser("patient", testUser);

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/me")) {
      return new Response(JSON.stringify({ detail: "Database temporarily unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  const user = await fetchPortalProfile("patient");
  assert.equal(user.user_id, "u-123");
  assert.equal(getStoredUser("patient")?.user_id, "u-123");
});

test("2. refresh 503 does NOT logout and preserves active session", async () => {
  clearAllPortalSessions();
  savePortalUser("patient", testUser);

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      return new Response(JSON.stringify({ detail: "Database unavailable" }), {
        status: 503,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  const refreshed = await refreshPortalSession("patient");
  assert.equal(refreshed, null);
  // Session must still be preserved in memory
  assert.equal(getStoredUser("patient")?.user_id, "u-123");
});

test("3. refresh 401 DOES logout and clear local user session", async () => {
  clearAllPortalSessions();
  savePortalUser("patient", testUser);

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      return new Response(JSON.stringify({ detail: "Invalid refresh session" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  const refreshed = await refreshPortalSession("patient");
  assert.equal(refreshed, null);
  assert.equal(getStoredUser("patient"), null);
});

test("4. only ONE refresh request is sent for simultaneous 401s", async () => {
  clearAllPortalSessions();
  savePortalUser("patient", testUser);

  let refreshCallCount = 0;
  const newUser: PortalUser = { ...testUser, access_token: "new-rotated-token" };

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      refreshCallCount++;
      await new Promise((r) => setTimeout(r, 20));
      return new Response(JSON.stringify(newUser), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  const [u1, u2, u3] = await Promise.all([
    refreshPortalSession("patient"),
    refreshPortalSession("patient"),
    refreshPortalSession("patient"),
  ]);

  assert.equal(refreshCallCount, 1, "Expected deduplicated single refresh call");
  assert.equal(u1?.access_token, "new-rotated-token");
  assert.equal(u2?.access_token, "new-rotated-token");
  assert.equal(u3?.access_token, "new-rotated-token");
});

test("5. authorizedFetch has single-refresh guard with no infinite recursion", async () => {
  clearAllPortalSessions();
  savePortalUser("patient", testUser);

  let apiCallCount = 0;
  let refreshCallCount = 0;

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/refresh")) {
      refreshCallCount++;
      return new Response(
        JSON.stringify({ ...testUser, access_token: "second-token" }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      );
    }
    if (url.includes("/api/protected")) {
      apiCallCount++;
      // Always returns 401 even with refreshed token
      return new Response(JSON.stringify({ detail: "Still unauthorized" }), {
        status: 401,
        headers: { "Content-Type": "application/json" },
      });
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  const res = await authorizedFetch("patient", "http://127.0.0.1:8000/api/protected");
  // Expected: 1 initial call -> 401 -> 1 refresh -> 1 retry call -> stops with 401
  assert.equal(apiCallCount, 2);
  assert.equal(refreshCallCount, 1);
  assert.equal(res.status, 401);
});

test("6. loginPortal on 503 throws AuthApiError with status 503", async () => {
  clearAllPortalSessions();

  (global as any).fetch = async (url: string) => {
    if (url.includes("/portal/auth/patient/login")) {
      return new Response(
        JSON.stringify({ detail: "Authentication service is temporarily unavailable" }),
        { status: 503, headers: { "Content-Type": "application/json" } }
      );
    }
    throw new Error(`Unexpected fetch: ${url}`);
  };

  await assert.rejects(
    async () => {
      await loginPortal("patient", "patient@example.com", "Password123");
    },
    (err: any) => {
      assert.ok(err instanceof AuthApiError);
      assert.equal(err.status, 503);
      return true;
    }
  );
});
