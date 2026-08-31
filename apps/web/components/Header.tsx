"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, useEffect } from "react";

export function Header() {
  const pathname = usePathname();
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
          <div className="brand-mark" aria-hidden>
            <svg viewBox="0 0 32 32" fill="none">
              <path
                d="M8 14c0-4 2.5-7 6-7s5 2 6 4c1-2 3-4 6-4 3.5 0 6 3 6 7v6c0 2-1 4-3 4-2.5 0-4-2-5-3.5-.5 1-2 3.5-4.5 3.5S10 27 9 25.5C8 27 6 29 3.5 29 1.5 29 0 27 0 25V14z"
                stroke="currentColor"
                strokeWidth="1.5"
                strokeLinecap="round"
              />
            </svg>
          </div>
          <div>
            <span className="brand-name">DantShaant</span>
            <span className="brand-tag">Autonomous dental AI</span>
          </div>
        </Link>
      </div>
      
      <nav style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
        <Link href="/scan" style={navLink(pathname === "/scan")}>
          Analyzer
        </Link>
        <Link href="/chat" style={navLink(pathname === "/chat")}>
          Chat
        </Link>
        <Link href="/portal" style={navLink(pathname === "/portal" || pathname.startsWith("/products"))}>
          Products
        </Link>
        {cartCount > 0 && (
          <div className="header-cart-badge" style={{
            background: "rgba(0, 242, 254, 0.15)",
            border: "1px solid rgba(0, 242, 254, 0.3)",
            color: "var(--accent)",
            padding: "0.2rem 0.6rem",
            borderRadius: "9999px",
            fontSize: "0.75rem",
            fontWeight: 700,
            display: "flex",
            alignItems: "center",
            gap: "0.3rem",
            marginRight: "0.5rem"
          }}>
            🛒 <span>{cartCount}</span>
          </div>
        )}
        <div className="header-badge">
          <span className="pulse-dot" />
          Demo ready
        </div>
      </nav>
    </header>
  );
}
