"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/i18n";
import { useTheme } from "@/theme";
import type { PortalRole, PortalUser } from "@/lib/portal-types";
import { PORTAL_META } from "@/lib/portal-types";
import styles from "./portal-header.module.css";

type NavItemKey = "dashboard" | "scan" | "chat" | "dentists" | "products" | "orders" | "users";
type NavItem = { href: string; key: NavItemKey; defaultLabel: string; authOnly?: boolean };

const PORTAL_NAV: Record<PortalRole, NavItem[]> = {
  patient: [
    { href: "/patient/dashboard", key: "dashboard", defaultLabel: "Dashboard", authOnly: true },
    { href: "/patient/scan", key: "scan", defaultLabel: "Oral scan", authOnly: true },
    { href: "/patient/chat", key: "chat", defaultLabel: "Chat assistant", authOnly: true },
    { href: "/patient/dentists", key: "dentists", defaultLabel: "Find dentists", authOnly: true },
  ],
  dentist: [
    { href: "/dentist/dashboard", key: "dashboard", defaultLabel: "Dashboard", authOnly: true },
    { href: "/dentist/products", key: "products", defaultLabel: "Products", authOnly: true },
    { href: "/dentist/orders", key: "orders", defaultLabel: "Orders", authOnly: true },
  ],
  admin: [
    { href: "/admin/dashboard", key: "dashboard", defaultLabel: "Dashboard", authOnly: true },
    { href: "/admin/users", key: "users", defaultLabel: "Users", authOnly: true },
  ],
};

type Props = {
  role: PortalRole;
  user?: PortalUser | null;
  onLogout?: () => void;
};

export function PortalHeader({ role, user, onLogout }: Props) {
  const pathname = usePathname();
  const { t, locale, toggleLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const meta = PORTAL_META[role];
  const navItems = PORTAL_NAV[role].filter((item) => !item.authOnly || user);

  const getLabel = (key: NavItemKey, fallback: string) => {
    switch (key) {
      case "dashboard":
        return t("nav.dashboard");
      case "scan":
        return t("nav.scan");
      case "chat":
        return t("nav.chat");
      case "dentists":
        return t("nav.dentists");
      case "products":
        return t("nav.products");
      case "orders":
        return t("nav.orders");
      case "users":
        return t("nav.users");
      default:
        return fallback;
    }
  };

  const avatar =
    user?.profile_image?.startsWith("data:") || user?.profile_image?.startsWith("/")
      ? user.profile_image
      : "/default-avatar.svg";

  return (
    <header className={styles.header} data-role={role}>
      <div>
        <Link href={user ? `/${role}/dashboard` : `/${role}/login`} className={styles.brand}>
          <div className={styles.mark} aria-hidden>
            <svg viewBox="0 0 32 32" fill="none">
              <path
                d="M8 14c0-4 2.5-7 6-7s5 2 6 4c1-2 3-4 6-4 3.5 0 6 3 6 7v6c0 2-1 4-3 4-2.5 0-4-2-5-3.5-.5 1-2 3.5-4.5 3.5S10 27 9 25.5C8 27 6 29 3.5 29 1.5 29 0 27 0 25V14z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div className={styles.brandText}>
            <span className={styles.brandName}>DaantShaant</span>
            <span className={styles.brandTag}>{role === "patient" ? t("common.tagline") : meta.eyebrow}</span>
          </div>
        </Link>

        <nav className={styles.nav}>
          {navItems.map((item) => {
            const active =
              pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`${styles.navLink} ${active ? styles.navLinkActive : ""}`}
              >
                {getLabel(item.key, item.defaultLabel)}
              </Link>
            );
          })}

          <div className={styles.controlGroup}>
            <button
              type="button"
              className={styles.langToggle}
              onClick={toggleLanguage}
              title={locale === "en" ? "اردو میں دیکھیں" : "Switch to English"}
              aria-label="Toggle language"
            >
              {locale === "en" ? "اردو" : "EN"}
            </button>

            <button
              type="button"
              className={styles.themeToggle}
              onClick={toggleTheme}
              title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
              aria-label="Toggle theme"
            >
              {theme === "light" ? "🌙" : "☀️"}
            </button>
          </div>

          {user ? (
            <div className={styles.userBlock}>
              <img src={avatar} alt="" className={styles.avatar} />
              <div className={styles.userMeta}>
                <strong>{user.name}</strong>
                <span>{user.email}</span>
              </div>
              <button type="button" className={styles.logoutBtn} onClick={onLogout}>
                {t("nav.logout")}
              </button>
            </div>
          ) : (
            <>
              <Link
                href={`/${role}/login`}
                className={`${styles.navLink} ${pathname === `/${role}/login` ? styles.navLinkActive : ""}`}
              >
                {t("nav.login")}
              </Link>
              {role !== "admin" && (
                <Link
                  href={`/${role}/register`}
                  className={`${styles.navLink} ${pathname === `/${role}/register` ? styles.navLinkActive : ""}`}
                >
                  {t("nav.register")}
                </Link>
              )}
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
