"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { getStoredUser, authorizedFetch, API_BASE } from "@/lib/portal-auth";
import { listMyProducts, type Product } from "@/lib/product-api";
import { useLanguage } from "@/i18n";
import styles from "./dentist-dashboard.module.css";

interface OrderItem {
  order_id: string;
  product_name: string;
  quantity: number;
  price: number;
  patient_name: string;
  status: string;
  created_at: string;
}

interface AppointmentItem {
  appointment_id: string;
  issue: string | null;
  status: string;
  created_at: string;
  patient_name?: string;
}

export function DentistDashboardHome() {
  const { t } = useLanguage();
  const [dentistName, setDentistName] = useState("");
  const [productsCount, setProductsCount] = useState(0);
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const user = getStoredUser("dentist");
    if (user?.first_name) {
      setDentistName(`Dr. ${user.first_name} ${user.last_name || ""}`.trim());
    }

    async function loadDashboardData() {
      setLoading(true);
      try {
        // Products
        const prodData = await listMyProducts().catch(() => [] as Product[]);
        setProductsCount(Array.isArray(prodData) ? prodData.length : 0);

        // Orders
        const ordersRes = await authorizedFetch("dentist", `${API_BASE}/portal/products/orders`).catch(() => null);
        if (ordersRes && ordersRes.ok) {
          const ordData = await ordersRes.json();
          if (Array.isArray(ordData)) {
            setOrders(ordData);
          }
        }

        // Appointments
        const appRes = await authorizedFetch("dentist", `${API_BASE}/portal/recommend/dentists/appointments`).catch(() => null);
        if (appRes && appRes.ok) {
          const appData = await appRes.json();
          if (Array.isArray(appData)) {
            setAppointments(appData);
          }
        }
      } catch (err) {
        console.warn("Error loading dentist dashboard data:", err);
      } finally {
        setLoading(false);
      }
    }

    loadDashboardData();
  }, []);

  const pendingOrders = orders.filter(
    (o) => (o.status || "").toLowerCase() === "pending" || (o.status || "").toLowerCase() === "placed"
  ).length;

  const totalSales = orders.reduce((sum, o) => sum + (Number(o.price) || 0), 0);

  return (
    <PortalDashboard role="dentist" maxWidth={1180}>
      <div className={styles.dashboard}>
        {/* Welcome Hero */}
        <section className={styles.hero}>
          <div className={styles.heroContent}>
            <div className={styles.heroBadge}>
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
                <polyline points="9 12 11 14 15 10" />
              </svg>
              <span>{t("dentist_dashboard.verified_partner")}</span>
            </div>
            <h1 className={styles.heroTitle}>
              {dentistName ? `${t("dashboard.welcome")}, ${dentistName}` : t("dentist_dashboard.welcome")}
            </h1>
            <p className={styles.heroDesc}>
              {t("dentist_dashboard.subtitle")}
            </p>
          </div>
        </section>

        {/* Quick Stats Grid */}
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M20.59 13.41l-7.17 7.17a2 2 0 0 1-2.83 0L2 12V2h10l8.59 8.59a2 2 0 0 1 0 2.82z" />
                <line x1="7" y1="7" x2="7.01" y2="7" />
              </svg>
            </div>
            <div>
              <div className={styles.statVal}>{productsCount}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_products")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
            </div>
            <div>
              <div className={styles.statVal}>{appointments.length}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_appointments")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
                <polyline points="3.29 7 12 12 20.71 7" />
                <line x1="12" y1="22" x2="12" y2="12" />
              </svg>
            </div>
            <div>
              <div className={styles.statVal}>{pendingOrders}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_pending_orders")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>
              <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="1" y="4" width="22" height="16" rx="2" ry="2" />
                <line x1="1" y1="10" x2="23" y2="10" />
              </svg>
            </div>
            <div>
              <div className={styles.statVal}>${totalSales.toFixed(2)}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_total_sales")}</div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <section>
          <h2 className={styles.sectionTitle}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
            </svg>
            <span>{t("dentist_dashboard.quick_actions")}</span>
          </h2>

          <div className={styles.actionsGrid}>
            <Link href="/dentist/products" className={`${styles.actionCard} ${styles.actionCardPrimary}`}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <circle cx="12" cy="12" r="10" />
                  <line x1="12" y1="8" x2="12" y2="16" />
                  <line x1="8" y1="12" x2="16" y2="12" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dentist_dashboard.action_add_product")}</h3>
              <p className={styles.actionDesc}>{t("products_mgmt.subtitle")}</p>
            </Link>

            <Link href="/dentist/orders" className={styles.actionCard}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
                  <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
                  <path d="M9 12h6M9 16h6" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dentist_dashboard.action_view_orders")}</h3>
              <p className={styles.actionDesc}>{t("orders.subtitle")}</p>
            </Link>

            <Link href="/dentist/appointments" className={styles.actionCard}>
              <div className={styles.actionIcon}>
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                  <polyline points="9 16 11 18 15 14" />
                </svg>
              </div>
              <h3 className={styles.actionTitle}>{t("dentist_dashboard.action_appointments")}</h3>
              <p className={styles.actionDesc}>{t("appointments.subtitle")}</p>
            </Link>
          </div>
        </section>

        {/* Two-column Previews */}
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
                <span>{t("dentist_dashboard.recent_orders_title")}</span>
              </h3>
              <Link href="/dentist/orders" className={styles.cardLink}>
                {t("common.view_details")}
              </Link>
            </div>

            {orders.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", margin: "1rem 0" }}>
                {t("dentist_dashboard.no_orders_yet")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {orders.slice(0, 4).map((order) => (
                  <div key={order.order_id} className={styles.previewItem}>
                    <div className={styles.previewInfo}>
                      <span className={styles.previewTitle}>{order.product_name}</span>
                      <span className={styles.previewSub}>
                        {order.patient_name || "Patient"} • Qty: {order.quantity} • ${Number(order.price || 0).toFixed(2)}
                      </span>
                    </div>
                    <span className={`${styles.statusPill} ${order.status === "confirmed" ? styles.statusConfirmed : styles.statusPending}`}>
                      {order.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Upcoming Appointments Preview */}
          <div className={styles.cardBlock}>
            <div className={styles.cardHead}>
              <h3>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                  <line x1="16" y1="2" x2="16" y2="6" />
                  <line x1="8" y1="2" x2="8" y2="6" />
                  <line x1="3" y1="10" x2="21" y2="10" />
                </svg>
                <span>{t("dentist_dashboard.upcoming_appointments_title")}</span>
              </h3>
              <Link href="/dentist/appointments" className={styles.cardLink}>
                {t("common.view_details")}
              </Link>
            </div>

            {appointments.length === 0 ? (
              <p style={{ color: "var(--text-muted)", fontSize: "0.88rem", margin: "1rem 0" }}>
                {t("dentist_dashboard.no_appointments_yet")}
              </p>
            ) : (
              <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
                {appointments.slice(0, 4).map((app) => (
                  <div key={app.appointment_id} className={styles.previewItem}>
                    <div className={styles.previewInfo}>
                      <span className={styles.previewTitle}>{app.patient_name || "Patient Consultation"}</span>
                      <span className={styles.previewSub}>{app.issue || "General Dental Consultation"}</span>
                    </div>
                    <span className={`${styles.statusPill} ${app.status === "confirmed" ? styles.statusConfirmed : styles.statusPending}`}>
                      {app.status}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Practice Tip & Intake Banner */}
        <section className={styles.practiceBanner}>
          <div className={styles.practiceContent}>
            <h3 className={styles.practiceTitle}>
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#00A2F0" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <circle cx="12" cy="12" r="10" />
                <line x1="12" y1="16" x2="12" y2="12" />
                <line x1="12" y1="8" x2="12.01" y2="8" />
              </svg>
              <span>{t("dentist_dashboard.practice_tip_title")}</span>
            </h3>
            <p className={styles.practiceDesc}>
              {t("dentist_dashboard.practice_tip_desc")}
            </p>
          </div>
        </section>
      </div>
    </PortalDashboard>
  );
}
