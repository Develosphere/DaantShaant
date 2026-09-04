"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { getStoredUser, API_BASE } from "@/lib/portal-auth";
import { useLanguage } from "@/i18n";
import { CheckoutModal } from "@/components/CheckoutModal";
import styles from "./patient-dashboard.module.css";

interface ProductItem {
  product_id: string;
  name: string;
  price: number;
  category?: string;
  dentist_name?: string;
}

const DEFAULT_RECOMMENDED_PRODUCTS: ProductItem[] = [
  {
    product_id: "prod-fluoride-pro",
    name: "Enamel Shield Fluoride Toothpaste",
    price: 12.50,
    category: "toothpaste",
    dentist_name: "Al-Shifa Dental Clinic",
  },
  {
    product_id: "prod-sonic-brush",
    name: "Ultra-Soft Periodontal Toothbrush",
    price: 8.99,
    category: "toothbrush",
    dentist_name: "Karachi Dental Specialists",
  },
  {
    product_id: "prod-floss-care",
    name: "Micro-Woven Interdental Floss (50m)",
    price: 5.50,
    category: "floss",
    dentist_name: "Dr. Tariq Dental Surgery",
  },
];

export function PatientDashboardView() {
  const { t } = useLanguage();
  const [userName, setUserName] = useState("");
  const [ordersCount, setOrdersCount] = useState(0);
  const [latestScanDate, setLatestScanDate] = useState<string | null>(null);
  const [selectedProduct, setSelectedProduct] = useState<ProductItem | null>(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);
  const [products, setProducts] = useState<ProductItem[]>(DEFAULT_RECOMMENDED_PRODUCTS);

  useEffect(() => {
    const user = getStoredUser("patient");
    if (user?.first_name) {
      setUserName(user.first_name);
    }

    // Load orders count
    try {
      const local = JSON.parse(localStorage.getItem("daantshaant_patient_orders") || "[]");
      if (Array.isArray(local)) {
        setOrdersCount(local.length);
      }
    } catch {}

    // Check recent scan
    try {
      const scan = localStorage.getItem("daantshaant_latest_report");
      if (scan) {
        setLatestScanDate("Recently");
      }
    } catch {}

    // Optionally fetch store products
    fetch(`${API_BASE}/portal/products/?limit=3`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        if (Array.isArray(data) && data.length > 0) {
          setProducts(
            data.slice(0, 3).map((p: any) => ({
              product_id: p.product_id,
              name: p.name,
              price: Number(p.price) || 9.99,
              category: p.category,
              dentist_name: "Registered Clinic",
            }))
          );
        }
      })
      .catch(() => {});
  }, []);

  const handleBuy = (product: ProductItem) => {
    setSelectedProduct(product);
    setIsCheckoutOpen(true);
  };

  return (
    <PortalDashboard role="patient" maxWidth={1180}>
      <div className={styles.dashboard}>
        {/* Welcome Hero */}
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <div className={styles.heroBadge}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2C9.24 2 7 4.24 7 7C7 8.72 7.88 10.23 9.2 11.1C7.28 11.88 6 13.8 6 16C6 16.55 6.45 17 7 17H17C17.55 17 18 16.55 18 16C18 13.8 16.72 11.88 14.8 11.1C16.12 10.23 17 8.72 17 7C17 4.24 14.76 2 12 2Z" />
                <path d="M9 17V20C9 21.1 9.9 22 11 22H13C14.1 22 15 21.1 15 20V17H9Z" />
              </svg>
              <span>{t("dashboard.oral_wellness")}</span>
            </div>
            <h1 className={styles.heroTitle}>
              {userName
                ? `${t("dashboard.welcome_back")}, ${userName}!`
                : t("dashboard.welcome_back")}
            </h1>
            <p className={styles.heroDesc}>
              {t("dashboard.welcome_desc")}
            </p>
          </div>

          <div className={styles.heroMetrics}>
            <div className={styles.metricItem}>
              <div className={styles.metricVal}>{latestScanDate ? "1" : "0"}</div>
              <div className={styles.metricLabel}>{t("nav.scan")}</div>
            </div>
            <div className={styles.metricItem}>
              <div className={styles.metricVal}>{ordersCount}</div>
              <div className={styles.metricLabel}>{t("nav.orders")}</div>
            </div>
            <div className={styles.metricItem}>
              <div className={styles.metricVal} style={{ color: "#00A2F0" }}>✓</div>
              <div className={styles.metricLabel}>{t("dashboard.wellness_good")}</div>
            </div>
          </div>
        </section>

        {/* Quick Actions */}
        <section>
          <h2 className={styles.sectionTitle}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>{t("dashboard.quick_actions")}</span>
          </h2>

          <div className={styles.actionsGrid}>
            <Link href="/patient/scan" className={`${styles.actionCard} ${styles.actionCardPrimary}`}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" />
                  <circle cx="12" cy="13" r="4" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_scan")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_scan_desc")}</p>
            </Link>

            <Link href="/patient/chat" className={styles.actionCard}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_chat")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_chat_desc")}</p>
            </Link>

            <Link href="/patient/dentists" className={styles.actionCard}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z" />
                  <circle cx="12" cy="10" r="3" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_dentists")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_dentists_desc")}</p>
            </Link>

            <Link href="/patient/orders" className={styles.actionCard}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M16.5 9.4 7.55 4.24M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <polyline points="3.29 7 12 12 20.71 7" />
                  <line x1="12" y1="22" x2="12" y2="12" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_orders")}</h3>
              <p className={styles.actionDesc}>{t("orders.patient_subtitle")}</p>
            </Link>
          </div>
        </section>

        {/* Two-column Content Area */}
        <div className={styles.twoColGrid}>
          {/* Latest Screening Card */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
                </svg>
                <span>{t("dashboard.recent_scan")}</span>
              </h3>
              <Link href="/patient/scans" className={styles.cardLink}>
                {t("nav.my_scans")}
              </Link>
            </div>

            <div className={styles.scanCard}>
              <div className={styles.scanStatusPill}>
                <span>✓</span>
                <span>{t("dashboard.wellness_good")}</span>
              </div>
              <div className={styles.scanFinding}>
                {latestScanDate
                  ? t("dashboard.scan_verified")
                  : t("dashboard.no_scan_yet")}
              </div>
              <p className={styles.scanHint}>
                {t("dashboard.screening_disclaimer_hint")}
              </p>
              <Link
                href="/patient/scan"
                style={{
                  alignSelf: "flex-start",
                  background: "#00A2F0",
                  color: "#ffffff",
                  fontSize: "0.82rem",
                  fontWeight: 700,
                  padding: "0.5rem 1rem",
                  borderRadius: "6px",
                  textDecoration: "none",
                  marginTop: "0.25rem",
                  transition: "background 0.2s ease",
                }}
              >
                {latestScanDate ? t("dashboard.action_update_scan") : t("dashboard.action_scan")}
              </Link>
            </div>
          </div>

          {/* Recommended Products Card */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z" />
                  <line x1="3" y1="6" x2="21" y2="6" />
                  <path d="M16 10a4 4 0 0 1-8 0" />
                </svg>
                <span>{t("dashboard.recommended_products_title")}</span>
              </h3>
              <Link href="/patient/orders" className={styles.cardLink}>
                {t("orders.patient_title")}
              </Link>
            </div>

            <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
              {products.map((prod) => (
                <div key={prod.product_id} className={styles.productItem}>
                  <div className={styles.productInfo}>
                    <span className={styles.productName}>{prod.name}</span>
                    <span className={styles.productSeller}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ display: "inline", verticalAlign: "middle", marginRight: "4px" }}>
                        <path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-3" />
                      </svg>
                      {prod.dentist_name || "Partner Clinic"} • ${prod.price.toFixed(2)}
                    </span>
                  </div>
                  <button
                    type="button"
                    className={styles.productBuyBtn}
                    onClick={() => handleBuy(prod)}
                  >
                    {t("report.buy_now")}
                  </button>
                </div>
              ))}
            </div>
          </div>
        </div>

        {/* Education / Prevention Banner */}
        <section className={styles.educationBanner}>
          <div className={styles.eduContent}>
            <div className={styles.eduIcon}>
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 2C9.24 2 7 4.24 7 7C7 8.72 7.88 10.23 9.2 11.1C7.28 11.88 6 13.8 6 16C6 16.55 6.45 17 7 17H17C17.55 17 18 16.55 18 16C18 13.8 16.72 11.88 14.8 11.1C16.12 10.23 17 8.72 17 7C17 4.24 14.76 2 12 2Z" />
                <path d="M9 17V20C9 21.1 9.9 22 11 22H13C14.1 22 15 21.1 15 20V17H9Z" />
              </svg>
            </div>
            <div>
              <h3 className={styles.eduTitle}>{t("dashboard.education_title")}</h3>
              <p className={styles.eduDesc}>{t("dashboard.education_desc")}</p>
            </div>
          </div>
        </section>
      </div>

      {selectedProduct && (
        <CheckoutModal
          isOpen={isCheckoutOpen}
          product={selectedProduct}
          onClose={() => {
            setIsCheckoutOpen(false);
            setSelectedProduct(null);
          }}
          onSuccess={() => {
            setOrdersCount((prev) => prev + 1);
          }}
        />
      )}
    </PortalDashboard>
  );
}
