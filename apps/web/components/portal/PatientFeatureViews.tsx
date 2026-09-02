"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useLanguage } from "@/i18n";
import { CameraPanel } from "@/components/CameraPanel";
import { ChatInterface } from "@/components/ChatInterface";
import { getStoredUser } from "@/lib/portal-auth";
import { getPatientConversationStorageKey } from "@/lib/user-id";
import { PortalDashboard } from "./PortalDashboard";
import feature from "./patient-feature.module.css";

export function PatientScanView() {
  const { t } = useLanguage();
  return (
    <PortalDashboard role="patient" maxWidth={1200}>
      <div className={feature.featureMain}>
        <section className={feature.intro}>
          <p className={feature.eyebrow}>{t("common.tagline")}</p>
          <h1 className={feature.title}>{t("scan.title")}</h1>
          <p className={feature.desc}>
            {t("scan.subtitle")}
          </p>
        </section>
        <div className={`demo-grid ${feature.featureGrid}`}>
          <CameraPanel />
        </div>
      </div>
    </PortalDashboard>
  );
}

export function PatientChatView() {
  const { t } = useLanguage();
  return (
    <PortalDashboard role="patient" maxWidth={960}>
      <div className={feature.featureMain} style={{ maxWidth: 960 }}>
        <section className={feature.intro}>
          <p className={feature.eyebrow}>{t("common.tagline")}</p>
          <h1 className={feature.title}>{t("chat.title")}</h1>
          <p className={feature.desc}>
            {t("chat.subtitle")}
          </p>
        </section>
        <ChatInterface conversationStorageKey={getPatientConversationStorageKey()} />
      </div>
    </PortalDashboard>
  );
}

export function PatientDashboardHome() {
  const { t } = useLanguage();
  const [firstName, setFirstName] = useState("");

  useEffect(() => {
    const u = getStoredUser("patient");
    if (u?.first_name) setFirstName(u.first_name);
  }, []);

  return (
    <PortalDashboard role="patient" maxWidth={960}>
      <section className={feature.intro}>
        <p className={feature.eyebrow}>{t("dashboard.welcome_eyebrow")}</p>
        <h1 className={feature.title}>
          {firstName ? `${t("dashboard.welcome_back")}, ${firstName}!` : t("dashboard.welcome_back")}
        </h1>
        <p className={feature.desc}>
          {t("dashboard.welcome_desc")}
        </p>
        <div className={feature.dashboardCards}>
          <Link href="/patient/scan" className={feature.card}>
            <div className={feature.cardIcon}>📷</div>
            <div className={feature.cardTitle}>{t("dashboard.scan_title")}</div>
            <p className={feature.cardDesc}>
              {t("dashboard.scan_desc")}
            </p>
          </Link>
          <Link href="/patient/chat" className={feature.card}>
            <div className={feature.cardIcon}>💬</div>
            <div className={feature.cardTitle}>{t("dashboard.chat_title")}</div>
            <p className={feature.cardDesc}>
              {t("dashboard.chat_desc")}
            </p>
          </Link>
          <Link href="/patient/dentists" className={feature.card}>
            <div className={feature.cardIcon}>🗺️</div>
            <div className={feature.cardTitle}>{t("dashboard.dentists_title")}</div>
            <p className={feature.cardDesc}>{t("dashboard.dentists_desc")}</p>
          </Link>
        </div>
      </section>
    </PortalDashboard>
  );
}

