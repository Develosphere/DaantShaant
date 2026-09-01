"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import type { PortalRole } from "@/lib/portal-types";
import { PORTAL_META } from "@/lib/portal-types";
import {
  fetchPortalProfile,
  getStoredUser,
  logoutPortal,
} from "@/lib/portal-auth";
import { PortalHeader } from "./PortalHeader";
import styles from "./portal-auth.module.css";

type Props = {
  role: PortalRole;
  children?: React.ReactNode;
  maxWidth?: number;
};

export function PortalDashboard({ role, children, maxWidth = 960 }: Props) {
  const router = useRouter();
  const meta = PORTAL_META[role];
  const [user, setUser] = useState(getStoredUser(role));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchPortalProfile(role)
      .then(setUser)
      .catch(() => {
        router.replace(`/${role}/login`);
      })
      .finally(() => setLoading(false));
  }, [role, router]);

  async function logout() {
    await logoutPortal(role);
    router.push(`/${role}/login`);
  }

  if (loading || !user) {
    return (
      <div className={styles.shell} data-role={role}>
        <div className={styles.orbA} aria-hidden />
        <div className={styles.orbB} aria-hidden />
        <PortalHeader role={role} />
        <main className={styles.layout} style={{ gridTemplateColumns: "1fr", placeItems: "center" }}>
          <p style={{ color: "#8b9bb8" }}>Loading dashboard…</p>
        </main>
      </div>
    );
  }

  return (
    <div className={styles.shell} data-role={role}>
      <div className={styles.orbA} aria-hidden />
      <div className={styles.orbB} aria-hidden />
      <div className={styles.grid} aria-hidden />

      <PortalHeader role={role} user={user} onLogout={logout} />

      <main
        className={styles.layout}
        style={{ gridTemplateColumns: "1fr", maxWidth, width: "100%", paddingBottom: "3rem" }}
      >
        {children ?? (
          <section className={styles.panel}>
            <p className={styles.eyebrow}>{meta.eyebrow}</p>
            <h1 className={styles.heroTitle} style={{ fontSize: "1.75rem" }}>
              Welcome, {user.first_name}!
            </h1>
            <p className={styles.heroDesc}>
              Your {role} dashboard is ready. Use the menu above to navigate.
            </p>
          </section>
        )}
      </main>
    </div>
  );
}
