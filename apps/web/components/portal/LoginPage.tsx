"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { useLanguage } from "@/i18n";
import type { PortalRole } from "@/lib/portal-types";
import { loginPortal } from "@/lib/portal-auth";
import { PortalAuthShell } from "./PortalAuthShell";
import { usePortalGuestGuard } from "./usePortalGuestGuard";
import styles from "./portal-auth.module.css";

type Props = { role: PortalRole };

export function LoginPage({ role }: Props) {
  usePortalGuestGuard(role);
  const router = useRouter();
  const { t } = useLanguage();
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
      setError(err instanceof Error ? err.message : t("auth.login_failed"));
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
          <label htmlFor={`${role}-email`}>{t("auth.email")}</label>
          <input
            id={`${role}-email`}
            type="email"
            required
            autoComplete="email"
            placeholder={t("auth.email_placeholder")}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-password`}>{t("auth.password")}</label>
          <input
            id={`${role}-password`}
            type="password"
            required
            autoComplete="current-password"
            placeholder={t("auth.password_placeholder")}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
        </div>

        <button type="submit" className={styles.submit} disabled={loading}>
          {loading ? t("auth.signing_in") : t("auth.sign_in")}
        </button>
      </form>
    </PortalAuthShell>
  );
}

