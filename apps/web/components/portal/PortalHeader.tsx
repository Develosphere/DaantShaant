"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { PortalRole, PortalUser } from "@/lib/portal-types";
import { PORTAL_META } from "@/lib/portal-types";
import styles from "./portal-header.module.css";

type NavItem = { href: string; label: string; authOnly?: boolean };

const PORTAL_NAV: Record<PortalRole, NavItem[]> = {
  patient: [
    { href: "/patient/dashboard", label: "Dashboard", authOnly: true },
    { href: "/patient/scan", label: "AI scan", authOnly: true },
    { href: "/patient/chat", label: "AI chat", authOnly: true },
    { href: "/patient/dentists", label: "Find dentists", authOnly: true },
    // { href: "/patient/scans", label: "My scans", authOnly: true }, // Hidden from navbar but route still accessible
  ],
  dentist: [
    { href: "/dentist/dashboard", label: "Dashboard", authOnly: true },
    { href: "/dentist/products", label: "Products", authOnly: true },
    { href: "/dentist/orders", label: "Orders", authOnly: true },
  ],
  admin: [
    { href: "/admin/dashboard", label: "Dashboard", authOnly: true },
    { href: "/admin/users", label: "Users", authOnly: true },
  ],
};

type Props = {
  role: PortalRole;
  user?: PortalUser | null;
  onLogout?: () => void;
};

export function PortalHeader({ role, user, onLogout }: Props) {
  const pathname = usePathname();
  const meta = PORTAL_META[role];
  const navItems = PORTAL_NAV[role].filter((item) => !item.authOnly || user);

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
            <span className={styles.brandName}>DaantShant</span>
            <span className={styles.brandTag}>{meta.eyebrow}</span>
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
                {item.label}
              </Link>
            );
          })}

          {user ? (
            <div className={styles.userBlock}>
              <img src={avatar} alt="" className={styles.avatar} />
              <div className={styles.userMeta}>
                <strong>{user.name}</strong>
                <span>{user.email}</span>
              </div>
              <button type="button" className={styles.logoutBtn} onClick={onLogout}>
                Log out
              </button>
            </div>
          ) : (
            <>
              <Link
                href={`/${role}/login`}
                className={`${styles.navLink} ${pathname === `/${role}/login` ? styles.navLinkActive : ""}`}
              >
                Sign in
              </Link>
              {role !== "admin" && (
                <Link
                  href={`/${role}/register`}
                  className={`${styles.navLink} ${pathname === `/${role}/register` ? styles.navLinkActive : ""}`}
                >
                  Register
                </Link>
              )}
            </>
          )}
        </nav>
      </div>
    </header>
  );
}
