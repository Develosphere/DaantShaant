"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { authorizedFetch, API_BASE } from "@/lib/portal-auth";
import { useLanguage } from "@/i18n";
import styles from "./patient-orders.module.css";

export interface PatientOrder {
  order_id: string;
  product_id?: string;
  product_name: string;
  dentist_name: string;
  seller_name?: string;
  quantity: number;
  price: number;
  status: string;
  created_at: string;
}

export function PatientOrdersView() {
  const { t } = useLanguage();
  const [orders, setOrders] = useState<PatientOrder[]>([]);
  const [loading, setLoading] = useState(true);

  const loadOrders = async () => {
    setLoading(true);
    let remoteOrders: PatientOrder[] = [];

    try {
      const res = await authorizedFetch("patient", `${API_BASE}/portal/products/patient/orders`);
      if (res.ok) {
        const data = await res.json();
        if (Array.isArray(data)) {
          remoteOrders = data;
        }
      }
    } catch (err) {
      console.warn("Could not fetch remote patient orders:", err);
    }

    // Merge with any locally saved simulated/offline orders
    try {
      const local = JSON.parse(localStorage.getItem("daantshaant_patient_orders") || "[]");
      if (Array.isArray(local)) {
        const remoteIds = new Set(remoteOrders.map((o) => o.order_id));
        const missingLocal = local.filter((o) => !remoteIds.has(o.order_id));
        setOrders([...remoteOrders, ...missingLocal]);
      } else {
        setOrders(remoteOrders);
      }
    } catch {
      setOrders(remoteOrders);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadOrders();
    const handleOrderPlaced = () => loadOrders();
    window.addEventListener("daantshaant_order_placed", handleOrderPlaced);
    return () => window.removeEventListener("daantshaant_order_placed", handleOrderPlaced);
  }, []);

  const getStatusClass = (status: string) => {
    const s = (status || "").toLowerCase();
    if (s === "confirmed") return styles.statusConfirmed;
    if (s === "processing") return styles.statusProcessing;
    if (s === "completed" || s === "shipped") return styles.statusCompleted;
    if (s === "cancelled") return styles.statusCancelled;
    return styles.statusPlaced;
  };

  const getStatusLabel = (status: string) => {
    const s = (status || "").toLowerCase();
    if (s === "confirmed") return t("orders.status_confirmed");
    if (s === "processing") return t("orders.status_processing");
    if (s === "completed") return t("orders.status_completed");
    if (s === "shipped") return t("orders.status_shipped");
    if (s === "cancelled") return t("orders.status_cancelled");
    return t("orders.status_placed");
  };

  const totalSpent = orders.reduce((acc, o) => acc + (Number(o.price) || 0), 0);
  const activeOrdersCount = orders.filter(
    (o) => !["completed", "cancelled"].includes((o.status || "").toLowerCase())
  ).length;

  return (
    <PortalDashboard role="patient" maxWidth={1120}>
      <div className={styles.container}>
        <div className={styles.header}>
          <h1 className={styles.title}>{t("orders.patient_title")}</h1>
          <p className={styles.subtitle}>{t("orders.patient_subtitle")}</p>
        </div>

        {/* Stats row */}
        <div className={styles.statsGrid}>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>📦</div>
            <div>
              <div className={styles.statValue}>{orders.length}</div>
              <div className={styles.statLabel}>{t("orders.quantity")}</div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>⏳</div>
            <div>
              <div className={styles.statValue}>{activeOrdersCount}</div>
              <div className={styles.statLabel}>{t("orders.status_processing")}</div>
            </div>
          </div>
          <div className={styles.statCard}>
            <div className={styles.statIcon}>💳</div>
            <div>
              <div className={styles.statValue}>${totalSpent.toFixed(2)}</div>
              <div className={styles.statLabel}>{t("orders.amount")}</div>
            </div>
          </div>
        </div>

        {/* Orders list card */}
        <div className={styles.tableCard}>
          {loading ? (
            <div style={{ padding: "3rem", textAlign: "center", color: "var(--text-muted)" }}>
              {t("common.loading")}
            </div>
          ) : orders.length === 0 ? (
            <div className={styles.emptyState}>
              <div className={styles.emptyIcon}>🛍️</div>
              <h3 className={styles.emptyTitle}>{t("orders.empty")}</h3>
              <p className={styles.emptyDesc}>{t("orders.no_patient_orders")}</p>
              <Link href="/patient/scan" className={styles.actionBtn}>
                {t("orders.browse_products")}
              </Link>
            </div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table className={styles.table}>
                <thead>
                  <tr>
                    <th>{t("orders.product")}</th>
                    <th>{t("orders.seller")}</th>
                    <th>{t("orders.date")}</th>
                    <th>{t("orders.quantity")}</th>
                    <th>{t("orders.amount")}</th>
                    <th>{t("orders.status")}</th>
                  </tr>
                </thead>
                <tbody>
                  {orders.map((order) => {
                    const formattedDate = order.created_at
                      ? new Date(order.created_at).toLocaleDateString(undefined, {
                          month: "short",
                          day: "numeric",
                          year: "numeric",
                        })
                      : "Recently";

                    return (
                      <tr key={order.order_id}>
                        <td>
                          <span className={styles.productName}>{order.product_name}</span>
                          <span className={styles.orderId}>#{order.order_id.slice(0, 8)}</span>
                        </td>
                        <td>
                          <div className={styles.sellerName}>
                            <span>🏥</span>
                            <span>{order.dentist_name || order.seller_name || "Partner Dental Clinic"}</span>
                          </div>
                        </td>
                        <td style={{ color: "var(--text-muted)", fontSize: "0.82rem" }}>
                          {formattedDate}
                        </td>
                        <td style={{ fontWeight: 600 }}>{order.quantity || 1}</td>
                        <td className={styles.priceCol}>${Number(order.price || 0).toFixed(2)}</td>
                        <td>
                          <span className={`${styles.statusPill} ${getStatusClass(order.status)}`}>
                            {getStatusLabel(order.status)}
                          </span>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </PortalDashboard>
  );
}
