"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useLanguage } from "@/i18n";
import { useTheme } from "@/theme";
import { DaantShaantLogo } from "@/components/common/DaantShaantLogo";
import styles from "./role-selection.module.css";

export function RoleSelection() {
  const router = useRouter();
  const { t, locale, toggleLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();

  const roles = [
    {
      id: "patient",
      title: t("get_started.role_patient"),
      description: t("get_started.patient_desc"),
      icon: (
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
          <circle cx="12" cy="7" r="4" />
        </svg>
      ),
      registerPath: "/patient/register",
      loginPath: "/patient/login",
      color: "blue",
    },
    {
      id: "dentist",
      title: t("get_started.role_dentist"),
      description: t("get_started.dentist_desc"),
      icon: (
        <svg width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 2C9.24 2 7 4.24 7 7C7 8.72 7.88 10.23 9.2 11.1C7.28 11.88 6 13.8 6 16C6 16.55 6.45 17 7 17H17C17.55 17 18 16.55 18 16C18 13.8 16.72 11.88 14.8 11.1C16.12 10.23 17 8.72 17 7C17 4.24 14.76 2 12 2Z" />
          <path d="M9 17V20C9 21.1 9.9 22 11 22H13C14.1 22 15 21.1 15 20V17H9Z" />
        </svg>
      ),
      registerPath: "/dentist/register",
      loginPath: "/dentist/login",
      color: "navy",
    },
  ];

  return (
    <div className={styles.page}>
      {/* Navbar — Header chrome locked LTR so logo is left and controls are right */}
      <header className={styles.nav}>
        <div className={styles.navInner}>
          <DaantShaantLogo href="/" priority />

          <div className={styles.navControls}>
            <button
              type="button"
              onClick={toggleLanguage}
              title={locale === "en" ? "اردو میں دیکھیں" : "Switch to English"}
              aria-label="Toggle language"
              className={styles.controlBtn}
            >
              {locale === "en" ? "اردو" : "EN"}
            </button>
            <button
              type="button"
              onClick={toggleTheme}
              title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
              aria-label="Toggle theme"
              className={styles.controlBtn}
            >
              {theme === "light" ? "🌙" : "☀️"}
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className={styles.main}>
        <div className={styles.content}>
          {/* Heading */}
          <div className={styles.header}>
            <h1 className={styles.title}>{t("get_started.title")}</h1>
            <p className={styles.subtitle}>
              {t("get_started.subtitle")}
            </p>
          </div>

          {/* Role Cards */}
          <div className={styles.cardsGrid} style={{ gridTemplateColumns: "repeat(2, minmax(280px, 440px))", justifyContent: "center" }}>
            {roles.map((role, index) => (
              <div
                key={role.id}
                className={`${styles.card} ${styles[`card${role.color.charAt(0).toUpperCase() + role.color.slice(1)}`]} ${styles.animateIn}`}
                style={{ transitionDelay: `${index * 0.1}s`, cursor: "pointer" }}
                onClick={() => router.push(role.registerPath)}
              >
                <div className={styles.cardIcon}>{role.icon}</div>
                <h2 className={styles.cardTitle}>{role.title}</h2>
                <p className={styles.cardDescription}>{role.description}</p>
                
                <div className={styles.cardActions} onClick={(e) => e.stopPropagation()}>
                  <Link href={role.registerPath} className={styles.btnPrimary}>
                    {t("get_started.sign_up")}
                  </Link>
                  <Link href={role.loginPath} className={styles.btnSecondary}>
                    {t("get_started.log_in")}
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
              {t("common.back")}
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
