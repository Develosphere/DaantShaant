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
              <span>⚕️</span>
              <span>✓ Verified Dental Partner</span>
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
            <div className={styles.statIcon}>🛍️</div>
            <div>
              <div className={styles.statVal}>{productsCount}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_products")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>📅</div>
            <div>
              <div className={styles.statVal}>{appointments.length}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_appointments")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>📦</div>
            <div>
              <div className={styles.statVal}>{pendingOrders}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_pending_orders")}</div>
            </div>
          </div>

          <div className={styles.statCard}>
            <div className={styles.statIcon}>💳</div>
            <div>
              <div className={styles.statVal}>${totalSales.toFixed(2)}</div>
              <div className={styles.statLabel}>{t("dentist_dashboard.stat_total_sales")}</div>
            </div>
          </div>
        </div>

        {/* Quick Actions */}
        <section>
          <h2 className={styles.sectionTitle}>
            <span>⚡</span>
            <span>{t("dentist_dashboard.quick_actions")}</span>
          </h2>

          <div className={styles.actionsGrid}>
            <Link href="/dentist/products" className={`${styles.actionCard} ${styles.actionCardPrimary}`}>
              <div className={styles.actionIcon}>➕</div>
              <h3 className={styles.actionTitle}>{t("dentist_dashboard.action_add_product")}</h3>
              <p className={styles.actionDesc}>{t("products_mgmt.subtitle")}</p>
            </Link>

            <Link href="/dentist/orders" className={styles.actionCard}>
              <div className={styles.actionIcon}>📋</div>
              <h3 className={styles.actionTitle}>{t("dentist_dashboard.action_view_orders")}</h3>
              <p className={styles.actionDesc}>{t("orders.subtitle")}</p>
            </Link>

            <Link href="/dentist/appointments" className={styles.actionCard}>
              <div className={styles.actionIcon}>🗓️</div>
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
                <span>📦</span>
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
                <span>📅</span>
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
              <span>✨</span>
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
