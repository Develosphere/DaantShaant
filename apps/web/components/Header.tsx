"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";
import { useLanguage } from "@/i18n";
import { useTheme } from "@/theme";
import { DaantShaantLogo } from "@/components/common/DaantShaantLogo";

export function Header() {
  const pathname = usePathname();
  const { t, locale, toggleLanguage } = useLanguage();
  const { theme, toggleTheme } = useTheme();
  const [cartCount, setCartCount] = useState(0);

  useEffect(() => {
    const updateCart = () => {
      try {
        const cart = JSON.parse(localStorage.getItem("dantshaant-cart") || "[]");
        setCartCount(cart.length);
      } catch (e) {}
    };
    updateCart();
    window.addEventListener("storage", updateCart);
    window.addEventListener("cart-updated", updateCart);
    return () => {
      window.removeEventListener("storage", updateCart);
      window.removeEventListener("cart-updated", updateCart);
    };
  }, []);

  const navLink = (active: boolean) => ({
    padding: "0.5rem 1rem",
    fontSize: "0.85rem",
    fontWeight: active ? "600" : "500",
    color: active ? "var(--accent)" : "var(--text-muted)",
    textDecoration: "none",
    transition: "color 0.2s ease",
  } as const);

  return (
    <header className="site-header">
      <div className="brand">
        <Link href="/" style={{ display: "flex", alignItems: "center", gap: "0.85rem", textDecoration: "none", color: "inherit" }}>
          <DaantShaantLogo href="" priority />
          <div>
            <span className="brand-tag">{t("common.tagline")}</span>
          </div>
        </Link>
      </div>

      <nav style={{ display: "flex", alignItems: "center", gap: "0.75rem", flexWrap: "wrap" }}>
        <Link href="/scan" style={navLink(pathname === "/scan")}>
          {t("nav.scan")}
        </Link>
        <Link href="/chat" style={navLink(pathname === "/chat")}>
          {t("nav.chat")}
        </Link>
        <Link href="/portal" style={navLink(pathname === "/portal" || pathname.startsWith("/products"))}>
          {t("nav.products")}
        </Link>
        {cartCount > 0 && (
          <div className="header-cart-badge" style={{
            background: "rgba(2, 132, 199, 0.15)",
            border: "1px solid rgba(2, 132, 199, 0.3)",
            color: "var(--accent)",
            padding: "0.2rem 0.6rem",
            borderRadius: "9999px",
            fontSize: "0.75rem",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            gap: "0.3rem",
            marginRight: "0.25rem"
          }}>
            🛒 <span>{cartCount}</span>
          </div>
        )}

        <div style={{ display: "flex", alignItems: "center", gap: "0.4rem" }}>
          <button
            type="button"
            onClick={toggleLanguage}
            title={locale === "en" ? "اردو میں دیکھیں" : "Switch to English"}
            aria-label="Toggle language"
            style={{
              padding: "0.4rem 0.65rem",
              fontSize: "0.8rem",
              fontWeight: 700,
              fontFamily: "inherit",
              color: "var(--text-primary)",
              background: "var(--bg-surface-raised)",
              border: "1px solid var(--border-default)",
              borderRadius: "8px",
              cursor: "pointer",
            }}
          >
            {locale === "en" ? "اردو" : "EN"}
          </button>

          <button
            type="button"
            onClick={toggleTheme}
            title={theme === "light" ? "Switch to dark mode" : "Switch to light mode"}
            aria-label="Toggle theme"
            style={{
              padding: "0.4rem 0.65rem",
              fontSize: "0.8rem",
              color: "var(--text-primary)",
              background: "var(--bg-surface-raised)",
              border: "1px solid var(--border-default)",
              borderRadius: "8px",
              cursor: "pointer",
            }}
          >
            {theme === "light" ? "🌙" : "☀️"}
          </button>
        </div>

        <div className="header-badge">
          <span className="pulse-dot" />
          {t("nav.demo_ready")}
        </div>
      </nav>
    </header>
  );
}

