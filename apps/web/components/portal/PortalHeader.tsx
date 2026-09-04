"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useLanguage } from "@/i18n";
import { useTheme } from "@/theme";
import type { PortalRole, PortalUser } from "@/lib/portal-types";
import { PORTAL_META } from "@/lib/portal-types";
import { DaantShaantLogo } from "@/components/common/DaantShaantLogo";
import styles from "./portal-header.module.css";

type NavItemKey = "dashboard" | "scan" | "chat" | "dentists" | "products" | "orders" | "appointments" | "users";
type NavItem = { href: string; key: NavItemKey; defaultLabel: string; authOnly?: boolean };

const PORTAL_NAV: Record<PortalRole, NavItem[]> = {
  patient: [
    { href: "/patient/dashboard", key: "dashboard", defaultLabel: "Dashboard", authOnly: true },
    { href: "/patient/scan", key: "scan", defaultLabel: "Oral scan", authOnly: true },
    { href: "/patient/chat", key: "chat", defaultLabel: "Chat assistant", authOnly: true },
    { href: "/patient/dentists", key: "dentists", defaultLabel: "Find dentists", authOnly: true },
    { href: "/patient/orders", key: "orders", defaultLabel: "Orders", authOnly: true },
  ],
  dentist: [
    { href: "/dentist/dashboard", key: "dashboard", defaultLabel: "Dashboard", authOnly: true },
    { href: "/dentist/products", key: "products", defaultLabel: "Products", authOnly: true },
    { href: "/dentist/orders", key: "orders", defaultLabel: "Orders", authOnly: true },
    { href: "/dentist/appointments", key: "appointments", defaultLabel: "Appointments", authOnly: true },
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
      case "appointments":
        return t("nav.appointments");
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
        <Link href={user ? `/${role}/dashboard` : "/"} className={styles.brand}>
          <DaantShaantLogo href="" priority />
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
