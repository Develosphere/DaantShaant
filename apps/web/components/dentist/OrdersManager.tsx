"use client";

import { useEffect, useState } from "react";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { authorizedFetch, API_BASE } from "@/lib/portal-auth";
import { useLanguage } from "@/i18n";
import styles from "./orders-manager.module.css";

interface OrderItem {
  order_id: string;
  product_id: string;
  product_name: string;
  quantity: number;
  price: number;
  patient_email: string;
  patient_name: string;
  status: string;
  created_at: string;
}

export function OrdersManager() {
  const { t } = useLanguage();
  const [orders, setOrders] = useState<OrderItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    loadOrders();
  }, []);

  async function loadOrders() {
    setLoading(true);
    setError("");
    try {
      const res = await authorizedFetch("dentist", `${API_BASE}/portal/products/orders`);
      if (!res.ok) {
        throw new Error("Failed to load orders");
      }
      const data = (await res.json()) as OrderItem[];
      setOrders(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load orders");
    } finally {
      setLoading(false);
    }
  }

  function getStatusClass(status: string) {
    const s = status.toLowerCase();
    if (s === "pending") return styles.statusPending;
    if (s === "confirmed") return styles.statusConfirmed;
    if (s === "shipped" || s === "completed") return styles.statusCompleted;
    if (s === "cancelled") return styles.statusCancelled;
    return styles.statusPending;
  }

  return (
    <PortalDashboard role="dentist" maxWidth={1200}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>{t("orders.title")}</h1>
            <p className={styles.subtitle}>{t("orders.subtitle")}</p>
          </div>
        </div>

        {error && (
          <div className={styles.error}>
            <span>⚠️ {error}</span>
            <button onClick={() => setError("")} style={{ background: "none", border: "none", cursor: "pointer", color: "inherit", fontSize: "1.2rem" }}>×</button>
          </div>
        )}

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <p>{t("common.loading")}</p>
          </div>
        ) : orders.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>🛍️</div>
            <h3>{t("orders.empty")}</h3>
            <p>{t("orders.subtitle")}</p>
          </div>
        ) : (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t("orders.order_id")}</th>
                  <th>{t("orders.date")}</th>
                  <th>{t("orders.product")}</th>
                  <th>{t("orders.quantity")}</th>
                  <th>{t("orders.customer")}</th>
                  <th>{t("orders.amount")}</th>
                  <th>{t("orders.status")}</th>
                </tr>
              </thead>
              <tbody>
                {orders.map((o) => (
                  <tr key={o.order_id}>
                    <td>
                      <span className={styles.orderId}>{o.order_id.slice(0, 8)}…</span>
                    </td>
                    <td>
                      {new Date(o.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </td>
                    <td>
                      <span className={styles.productName}>{o.product_name}</span>
                    </td>
                    <td>{o.quantity || 1}</td>
                    <td>
                      <div>
                        <div>{o.patient_name || "Patient"}</div>
                        {o.patient_email && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {o.patient_email}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={styles.amount}>${o.price.toFixed(2)}</span>
                    </td>
                    <td>
                      <span className={`${styles.statusBadge} ${getStatusClass(o.status)}`}>
                        {o.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </PortalDashboard>
  );
}
