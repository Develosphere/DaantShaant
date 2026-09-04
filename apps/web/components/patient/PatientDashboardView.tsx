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
              <span>🦷</span>
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
              <div className={styles.metricVal}>✓</div>
              <div className={styles.metricLabel}>{t("dashboard.wellness_good")}</div>
            </div>
          </div>
        </section>

        {/* Quick Actions */}
        <section>
          <h2 className={styles.sectionTitle}>
            <span>⚡</span>
            <span>{t("dashboard.quick_actions")}</span>
          </h2>

          <div className={styles.actionsGrid}>
            <Link href="/patient/scan" className={`${styles.actionCard} ${styles.actionCardPrimary}`}>
              <div className={styles.actionIcon}>📸</div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_scan")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_scan_desc")}</p>
            </Link>

            <Link href="/patient/chat" className={styles.actionCard}>
              <div className={styles.actionIcon}>💬</div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_chat")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_chat_desc")}</p>
            </Link>

            <Link href="/patient/dentists" className={styles.actionCard}>
              <div className={styles.actionIcon}>🗺️</div>
              <h3 className={styles.actionTitle}>{t("dashboard.action_dentists")}</h3>
              <p className={styles.actionDesc}>{t("dashboard.card_dentists_desc")}</p>
            </Link>

            <Link href="/patient/orders" className={styles.actionCard}>
              <div className={styles.actionIcon}>📦</div>
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
                <span>🔬</span>
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
                  ? "AI screening report active and verified"
                  : t("dashboard.no_scan_yet")}
              </div>
              <p className={styles.scanHint}>
                Screening evaluates visible enamel plaque, tartar deposits, and gum inflammation. Confirm concerns with a licensed dentist.
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
                }}
              >
                {latestScanDate ? "Run Updated Screening" : t("dashboard.action_scan")}
              </Link>
            </div>
          </div>

          {/* Recommended Products Card */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <span>🛍️</span>
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
                      🏥 {prod.dentist_name || "Partner Clinic"} • ${prod.price.toFixed(2)}
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
            <h3 className={styles.eduTitle}>
              <span>💡</span>
              <span>{t("dashboard.education_title")}</span>
            </h3>
            <p className={styles.eduDesc}>
              {t("dashboard.education_desc")}
            </p>
          </div>

          <Link href="/patient/dentists" className={styles.eduBtn}>
            {t("dashboard.book_visit")}
          </Link>
        </section>

        {/* Checkout Modal */}
        <CheckoutModal
          product={selectedProduct}
          isOpen={isCheckoutOpen}
          onClose={() => setIsCheckoutOpen(false)}
        />
      </div>
    </PortalDashboard>
  );
}
