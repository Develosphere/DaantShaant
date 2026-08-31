"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PortalRole } from "@/lib/portal-types";
import { loginPortal } from "@/lib/portal-auth";
import { PortalAuthShell } from "./PortalAuthShell";
import { usePortalGuestGuard } from "./usePortalGuestGuard";
import styles from "./portal-auth.module.css";

type Props = { role: PortalRole };

export function LoginPage({ role }: Props) {
  usePortalGuestGuard(role);
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await loginPortal(role, email.trim(), password);
      router.push(`/${role}/dashboard`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalAuthShell role={role} mode="login">
      <form className={styles.form} onSubmit={handleSubmit}>
        {error && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-email`}>Email address</label>
          <input
            id={`${role}-email`}
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-password`}>Password</label>
          <input
            id={`${role}-password`}
            type="password"
            required
            autoComplete="current-password"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className={styles.submit} disabled={loading}>
          {loading ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </PortalAuthShell>
  );
}
