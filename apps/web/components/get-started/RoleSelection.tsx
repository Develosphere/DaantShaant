"use client";

import Link from "next/link";
import Image from "next/image";
import { useRouter } from "next/navigation";
import styles from "./role-selection.module.css";

const ROLES = [
  {
    id: "patient",
    title: "PATIENT",
    description: "Get AI-powered dental insights and connect with trusted dentists",
    icon: (
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
        <circle cx="12" cy="7" r="4" />
      </svg>
    ),
    registerPath: "/patient/register",
    loginPath: "/patient/login",
    color: "blue",
    hidden: false,
  },
  {
    id: "dentist",
    title: "DENTIST",
    description: "Manage your practice, recommend products, and reach more patients",
    icon: (
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2C9.24 2 7 4.24 7 7C7 8.72 7.88 10.23 9.2 11.1C7.28 11.88 6 13.8 6 16C6 16.55 6.45 17 7 17H17C17.55 17 18 16.55 18 16C18 13.8 16.72 11.88 14.8 11.1C16.12 10.23 17 8.72 17 7C17 4.24 14.76 2 12 2Z" />
        <path d="M9 17V20C9 21.1 9.9 22 11 22H13C14.1 22 15 21.1 15 20V17H9Z" />
      </svg>
    ),
    registerPath: "/dentist/register",
    loginPath: "/dentist/login",
    color: "navy",
    hidden: false,
  },
  {
    id: "admin",
    title: "ADMIN",
    description: "Oversee platform operations, user management, and system analytics",
    icon: (
      <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2L2 7l10 5 10-5-10-5z" />
        <path d="M2 17l10 5 10-5" />
        <path d="M2 12l10 5 10-5" />
      </svg>
    ),
    registerPath: "/admin/login",
    loginPath: "/admin/login",
    color: "primary",
    hidden: true, // Hidden from UI but route still accessible
  },
];

export function RoleSelection() {
  const router = useRouter();

  return (
    <div className={styles.page}>
      {/* Navbar */}
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <Link href="/" className={styles.logoLink} aria-label="DaantShant home">
            <Image
              src="/landing/logo.png"
              alt="DaantShant"
              width={167}
              height={78}
              className={styles.logoImg}
              priority
            />
          </Link>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        <div className={styles.content}>
          {/* Heading */}
          <div className={styles.header}>
            <h1 className={styles.title}>WHO ARE YOU?</h1>
            <p className={styles.subtitle}>
              Choose your role to get started with DaantShant
            </p>
          </div>

          {/* Role Cards */}
          <div className={styles.cardsGrid}>
            {ROLES.filter(role => !role.hidden).map((role, index) => (
              <div
                key={role.id}
                className={`${styles.card} ${styles[`card${role.color.charAt(0).toUpperCase() + role.color.slice(1)}`]} ${styles.animateIn}`}
                style={{ transitionDelay: `${index * 0.1}s` }}
              >
                <div className={styles.cardIcon}>{role.icon}</div>
                <h2 className={styles.cardTitle}>{role.title}</h2>
                <p className={styles.cardDescription}>{role.description}</p>
                
                <div className={styles.cardActions}>
                  <Link href={role.registerPath} className={styles.btnPrimary}>
                    SIGN UP
                  </Link>
                  <Link href={role.loginPath} className={styles.btnSecondary}>
                    LOG IN
                  </Link>
                </div>
              </div>
            ))}
          </div>

          {/* Back to Home */}
          <div className={styles.backLink}>
            <Link href="/">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
              Back to Home
            </Link>
          </div>
        </div>
      </main>

      {/* Decorative Background Elements */}
      <div className={styles.bgDecoration} aria-hidden="true">
        <div className={styles.bgCircle1} />
        <div className={styles.bgCircle2} />
        <div className={styles.bgCircle3} />
      </div>
    </div>
  );
}
