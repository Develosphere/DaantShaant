"use client";

import { useEffect, useState } from "react";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { authorizedFetch, API_BASE } from "@/lib/portal-auth";
import { useLanguage } from "@/i18n";
import styles from "./orders-manager.module.css";

interface AppointmentItem {
  appointment_id: string;
  patient_user_id: string;
  dentist_id: string;
  scan_id: string | null;
  issue: string | null;
  message: string | null;
  preferred_time: string | null;
  status: string;
  created_at: string;
  patient_name?: string;
  patient_email?: string;
  patient_phone?: string;
}

export function AppointmentsManager() {
  const { t } = useLanguage();
  const [appointments, setAppointments] = useState<AppointmentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [actionLoadingId, setActionLoadingId] = useState<string | null>(null);

  useEffect(() => {
    loadAppointments();
  }, []);

  async function loadAppointments() {
    setLoading(true);
    setError("");
    try {
      const res = await authorizedFetch("dentist", `${API_BASE}/portal/recommend/dentists/appointments`);
      if (!res.ok) {
        throw new Error("Failed to load appointments");
      }
      const data = (await res.json()) as AppointmentItem[];
      setAppointments(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load appointments");
    } finally {
      setLoading(false);
    }
  }

  async function updateStatus(appointmentId: string, newStatus: string) {
    setActionLoadingId(appointmentId);
    try {
      const res = await authorizedFetch(
        "dentist",
        `${API_BASE}/portal/recommend/dentists/appointments/${appointmentId}/status`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: newStatus }),
        }
      );
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || "Failed to update appointment status");
      }
      setAppointments((prev) =>
        prev.map((app) =>
          app.appointment_id === appointmentId ? { ...app, status: newStatus } : app
        )
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    } finally {
      setActionLoadingId(null);
    }
  }

  function getStatusClass(status: string) {
    const s = status.toLowerCase();
    if (s === "pending") return styles.statusPending;
    if (s === "confirmed" || s === "accepted") return styles.statusConfirmed;
    if (s === "completed") return styles.statusCompleted;
    if (s === "cancelled" || s === "rejected") return styles.statusCancelled;
    return styles.statusPending;
  }

  return (
    <PortalDashboard role="dentist" maxWidth={1200}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>{t("appointments.title")}</h1>
            <p className={styles.subtitle}>{t("appointments.subtitle")}</p>
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
        ) : appointments.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>📅</div>
            <h3>{t("appointments.empty")}</h3>
            <p>{t("appointments.subtitle")}</p>
          </div>
        ) : (
          <div className={styles.tableContainer}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t("orders.order_id")}</th>
                  <th>{t("appointments.date")}</th>
                  <th>{t("appointments.patient")}</th>
                  <th>{t("appointments.issue")}</th>
                  <th>{t("appointments.status")}</th>
                  <th>{t("appointments.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {appointments.map((a) => (
                  <tr key={a.appointment_id}>
                    <td>
                      <span className={styles.orderId}>{a.appointment_id.slice(0, 8)}…</span>
                    </td>
                    <td>
                      {new Date(a.created_at).toLocaleDateString(undefined, {
                        month: "short",
                        day: "numeric",
                        year: "numeric",
                      })}
                    </td>
                    <td>
                      <div>
                        <div style={{ fontWeight: 600 }}>{a.patient_name || "Patient"}</div>
                        {a.patient_email && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {a.patient_email}
                          </div>
                        )}
                        {a.patient_phone && (
                          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            {a.patient_phone}
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      <div>
                        <div style={{ fontWeight: 500 }}>{a.issue || "General Consultation"}</div>
                        {a.message && (
                          <div style={{ fontSize: "0.78rem", color: "var(--text-muted)", marginTop: "0.2rem", maxWidth: "260px" }}>
                            "{a.message}"
                          </div>
                        )}
                      </div>
                    </td>
                    <td>
                      <span className={`${styles.statusBadge} ${getStatusClass(a.status)}`}>
                        {a.status}
                      </span>
                    </td>
                    <td>
                      <div style={{ display: "flex", gap: "0.4rem", flexWrap: "wrap" }}>
                        {a.status === "pending" && (
                          <button
                            type="button"
                            disabled={actionLoadingId === a.appointment_id}
                            onClick={() => updateStatus(a.appointment_id, "confirmed")}
                            style={{
                              background: "#00A2F0",
                              color: "#fff",
                              border: "none",
                              borderRadius: "6px",
                              padding: "0.35rem 0.65rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              cursor: "pointer",
                            }}
                          >
                            {t("appointments.accept")}
                          </button>
                        )}
                        {a.status === "confirmed" && (
                          <button
                            type="button"
                            disabled={actionLoadingId === a.appointment_id}
                            onClick={() => updateStatus(a.appointment_id, "completed")}
                            style={{
                              background: "#10b981",
                              color: "#fff",
                              border: "none",
                              borderRadius: "6px",
                              padding: "0.35rem 0.65rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              cursor: "pointer",
                            }}
                          >
                            {t("appointments.complete")}
                          </button>
                        )}
                        {a.status !== "cancelled" && a.status !== "completed" && (
                          <button
                            type="button"
                            disabled={actionLoadingId === a.appointment_id}
                            onClick={() => updateStatus(a.appointment_id, "cancelled")}
                            style={{
                              background: "rgba(239, 68, 68, 0.12)",
                              color: "#ef4444",
                              border: "1px solid rgba(239, 68, 68, 0.3)",
                              borderRadius: "6px",
                              padding: "0.35rem 0.65rem",
                              fontSize: "0.75rem",
                              fontWeight: 700,
                              cursor: "pointer",
                            }}
                          >
                            {t("appointments.cancel")}
                          </button>
                        )}
                      </div>
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
