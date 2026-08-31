"use client";

import Link from "next/link";
import type { PortalRole } from "@/lib/portal-types";
import { PORTAL_META } from "@/lib/portal-types";
import { PortalHeader } from "./PortalHeader";
import styles from "./portal-auth.module.css";

type Props = {
  role: PortalRole;
  mode: "login" | "register";
  children: React.ReactNode;
};

export function PortalAuthShell({ role, mode, children }: Props) {
  const meta = PORTAL_META[role];
  const isLogin = mode === "login";

  return (
    <div className={styles.shell} data-role={role}>
      <div className={styles.orbA} aria-hidden />
      <div className={styles.orbB} aria-hidden />
      <div className={styles.grid} aria-hidden />
      <div className={styles.orbRole} aria-hidden />

      <PortalHeader role={role} />

      <main className={styles.layout}>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>{meta.eyebrow}</p>
          <h1 className={styles.heroTitle}>
            {meta.title}
            <span className={styles.heroGradient}>{meta.heroLine}</span>
          </h1>
          <p className={styles.heroDesc}>{meta.subtitle}</p>
          <ul className={styles.pills}>
            {meta.features.map((f) => (
              <li key={f}>{f}</li>
            ))}
          </ul>
        </section>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <div className={styles.panelIcon} aria-hidden>
              {role === "patient" && "🦷"}
              {role === "dentist" && "⚕️"}
              {role === "admin" && "🛡️"}
            </div>
            <div>
              <h2>{isLogin ? "Welcome back" : "Create account"}</h2>
              <p>
                {isLogin
                  ? `Sign in to your ${role} dashboard`
                  : `Register as a ${role} on DantShaant`}
              </p>
            </div>
          </div>

          <div className={styles.tabs}>
            <Link
              href={`/${role}/login`}
              className={`${styles.tab} ${isLogin ? styles.tabActive : ""}`}
            >
              Sign in
            </Link>
            <Link
              href={`/${role}/register`}
              className={`${styles.tab} ${!isLogin ? styles.tabActive : ""}`}
            >
              Register
            </Link>
          </div>

          {children}
        </section>
      </main>

      <footer className={styles.footer}>
        <span>DantShaant © 2026</span>
        <span className={styles.footerDot} />
        <Link href="/">Public website</Link>
      </footer>
    </div>
  );
}
