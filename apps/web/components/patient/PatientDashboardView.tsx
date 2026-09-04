"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { getStoredUser } from "@/lib/portal-auth";
import {
  getPatientDashboard,
  type DashboardProductItem,
  type PatientDashboardResponse,
} from "@/lib/dashboard-api";
import { useLanguage } from "@/i18n";
import { CheckoutModal } from "@/components/CheckoutModal";
import styles from "./patient-dashboard.module.css";

export function PatientDashboardView() {
  const { t } = useLanguage();
  const [userName, setUserName] = useState("");
  const [dashboardData, setDashboardData] = useState<PatientDashboardResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [selectedProduct, setSelectedProduct] = useState<DashboardProductItem | null>(null);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);

  async function loadData() {
    setLoading(true);
    setError(null);
    try {
      const data = await getPatientDashboard();
      setDashboardData(data);
    } catch (err: any) {
      console.warn("Error loading patient dashboard:", err);
      setError(t("dashboard.error_loading"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    const user = getStoredUser("patient");
    if (user?.first_name) {
      setUserName(user.first_name);
    }
    loadData();
  }, []);

  const handleBuy = (product: DashboardProductItem) => {
    setSelectedProduct(product);
    setIsCheckoutOpen(true);
  };

  // Derive status badge, icon, and colors
  const oralStatus = dashboardData?.stats.oral_status;
  let statusIcon = "—";
  let statusLabel = t("dashboard.status_no_screening");
  let statusColor = "var(--text-muted, #64748b)";
  let statusPillClass = styles.statusNeutral;

  if (oralStatus === "routine") {
    statusIcon = "✓";
    statusLabel = t("dashboard.status_routine");
    statusColor = "#10b981";
    statusPillClass = styles.statusRoutine;
  } else if (oralStatus === "soon") {
    statusIcon = "⚡";
    statusLabel = t("dashboard.status_soon");
    statusColor = "#f59e0b";
    statusPillClass = styles.statusSoon;
  } else if (oralStatus === "urgent") {
    statusIcon = "!";
    statusLabel = t("dashboard.status_urgent");
    statusColor = "#ef4444";
    statusPillClass = styles.statusUrgent;
  } else if (oralStatus === "emergency") {
    statusIcon = "⚠️";
    statusLabel = t("dashboard.status_emergency");
    statusColor = "#dc2626";
    statusPillClass = styles.statusUrgent;
  }

  const latestScreening = dashboardData?.latest_screening;
  const recommendedProducts = dashboardData?.recommended_products || [];
  const recentOrders = dashboardData?.recent_orders || [];
  const recentActivity = dashboardData?.recent_activity || [];

  return (
    <PortalDashboard role="patient" maxWidth={1180}>
      <div className={styles.dashboard}>
        {error && (
          <div className={styles.errorNotice} role="alert">
            <span>{error}</span>
            <button type="button" className={styles.retryBtn} onClick={loadData}>
              {t("dashboard.retry")}
            </button>
          </div>
        )}

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
              <div className={styles.metricVal}>
                {loading ? <span className={styles.skeletonPulse}>···</span> : (dashboardData?.stats.scan_count ?? 0)}
              </div>
              <div className={styles.metricLabel}>{t("nav.scan")}</div>
            </div>
            <div className={styles.metricItem}>
              <div className={styles.metricVal}>
                {loading ? <span className={styles.skeletonPulse}>···</span> : (dashboardData?.stats.order_count ?? 0)}
              </div>
              <div className={styles.metricLabel}>{t("nav.orders")}</div>
            </div>
            <div className={styles.metricItem}>
              <div className={styles.metricVal} style={{ color: statusColor }}>
                {loading ? <span className={styles.skeletonPulse}>···</span> : statusIcon}
              </div>
              <div className={styles.metricLabel}>
                {loading ? "···" : statusLabel}
              </div>
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

        {/* Two-column Content Area: Latest Screening & Recommended Products */}
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
              <Link href="/patient/scan" className={styles.cardLink}>
                {latestScreening ? t("dashboard.view_all_scans") : t("dashboard.action_scan")}
              </Link>
            </div>

            {loading ? (
              <div className={styles.scanCard}>
                <div className={styles.skeletonBlock} style={{ width: "40%" }} />
                <div className={styles.skeletonBlock} style={{ width: "70%" }} />
                <div className={styles.skeletonBlock} style={{ width: "90%" }} />
              </div>
            ) : latestScreening ? (
              <div className={styles.scanCard}>
                <div className={statusPillClass}>
                  <span>{statusIcon}</span>
                  <span>{statusLabel}</span>
                </div>
                <div className={styles.scanFinding}>
                  {latestScreening.verdict}
                </div>
                <p className={styles.scanHint}>
                  {latestScreening.summary}
                </p>
                <div style={{ fontSize: "0.82rem", color: "var(--text-muted)", display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                  <div>
                    <strong style={{ color: "var(--text-secondary)" }}>{t("dashboard.recommended_specialist")}:</strong>{" "}
                    {latestScreening.recommended_specialist}
                  </div>
                  {latestScreening.major_concerns.length > 0 && (
                    <div>
                      <strong style={{ color: "var(--text-secondary)" }}>Observations:</strong>{" "}
                      {latestScreening.major_concerns.join(", ")}
                    </div>
                  )}
                  <div>
                    <strong style={{ color: "var(--text-secondary)" }}>Date:</strong>{" "}
                    {new Date(latestScreening.created_at).toLocaleDateString()}
                  </div>
                </div>
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
                  {t("dashboard.action_update_scan")}
                </Link>
              </div>
            ) : (
              <div className={styles.scanCard}>
                <div className={styles.statusNeutral}>
                  <span>—</span>
                  <span>{t("dashboard.status_no_screening")}</span>
                </div>
                <div className={styles.scanFinding}>
                  {t("dashboard.no_scan_yet")}
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
                  {t("dashboard.action_scan")}
                </Link>
              </div>
            )}
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

            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div className={styles.skeletonBlock} style={{ height: "48px" }} />
                <div className={styles.skeletonBlock} style={{ height: "48px" }} />
              </div>
            ) : recommendedProducts.length === 0 ? (
              <p className={styles.emptyNotice}>
                {t("dashboard.no_recommendations_yet")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {recommendedProducts.map((prod) => (
                  <div key={prod.product_id} className={styles.productItem}>
                    <div className={styles.productInfo}>
                      <span className={styles.productName}>{prod.name}</span>
                      <span className={styles.productSeller}>
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={{ display: "inline", verticalAlign: "middle", marginRight: "4px" }}>
                          <path d="M3 21h18M5 21V7l8-4v18M19 21V11l-6-3" />
                        </svg>
                        {prod.dentist_name} • ${prod.price.toFixed(2)}
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
            )}
          </div>
        </div>

        {/* Two-column Preview Area: Recent Orders & Recent Activity */}
        <div className={styles.twoColGrid}>
          {/* Recent Orders Preview */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M16.5 9.4 7.55 4.24M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                  <polyline points="3.29 7 12 12 20.71 7" />
                  <line x1="12" y1="22" x2="12" y2="12" />
                </svg>
                <span>{t("dashboard.recent_orders_title")}</span>
              </h3>
              <Link href="/patient/orders" className={styles.cardLink}>
                {t("dashboard.view_all_orders")}
              </Link>
            </div>

            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div className={styles.skeletonBlock} style={{ height: "42px" }} />
                <div className={styles.skeletonBlock} style={{ height: "42px" }} />
              </div>
            ) : recentOrders.length === 0 ? (
              <p className={styles.emptyNotice}>
                {t("dashboard.no_orders_yet")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {recentOrders.map((ord) => (
                  <div key={ord.order_id} className={styles.previewItem}>
                    <div className={styles.previewInfo}>
                      <span className={styles.previewTitle}>{ord.product_name}</span>
                      <span className={styles.previewSub}>
                        {ord.seller_name || "Partner Dental Clinic"} • Qty: {ord.quantity} • ${ord.price.toFixed(2)}
                      </span>
                    </div>
                    <span className={`${styles.statusPill} ${ord.status === "confirmed" || ord.status === "completed" ? styles.statusRoutine : styles.statusSoon}`}>
                      {ord.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent Activity Timeline */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <polyline points="12 6 12 12 16 14" />
                </svg>
                <span>{t("dashboard.recent_activity_title")}</span>
              </h3>
            </div>

            {loading ? (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                <div className={styles.skeletonBlock} style={{ height: "42px" }} />
                <div className={styles.skeletonBlock} style={{ height: "42px" }} />
              </div>
            ) : recentActivity.length === 0 ? (
              <p className={styles.emptyNotice}>
                {t("dashboard.no_activity_yet")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {recentActivity.map((act) => (
                  <div key={act.id} className={styles.previewItem}>
                    <div className={styles.previewInfo}>
                      <span className={styles.previewTitle}>{act.title}</span>
                      <span className={styles.previewSub}>{act.description}</span>
                    </div>
                    <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", whiteSpace: "nowrap" }}>
                      {act.created_at ? new Date(act.created_at).toLocaleDateString() : ""}
                    </span>
                  </div>
                ))}
              </div>
            )}
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
          product={{
            product_id: selectedProduct.product_id,
            name: selectedProduct.name,
            price: selectedProduct.price,
            dentist_name: selectedProduct.dentist_name,
          }}
          onClose={() => {
            setIsCheckoutOpen(false);
            setSelectedProduct(null);
          }}
          onSuccess={() => {
            loadData();
          }}
        />
      )}
    </PortalDashboard>
  );
}
