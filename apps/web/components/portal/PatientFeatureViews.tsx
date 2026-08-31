"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { CameraPanel } from "@/components/CameraPanel";
import { ChatInterface } from "@/components/ChatInterface";
import { getStoredUser } from "@/lib/portal-auth";
import { getPatientConversationStorageKey } from "@/lib/user-id";
import { PortalDashboard } from "./PortalDashboard";
import feature from "./patient-feature.module.css";

export function PatientScanView() {
  return (
    <PortalDashboard role="patient" maxWidth={1200}>
      <div className={feature.featureMain}>
        <section className={feature.intro}>
          <p className={feature.eyebrow}>Vision AI · Clinical rules</p>
          <h1 className={feature.title}>AI teeth scan</h1>
          <p className={feature.desc}>
            Capture a photo, run live video, or upload an image — DantShaant analyzes
            your teeth and returns a diagnosis report saved to your patient account.
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
  return (
    <PortalDashboard role="patient" maxWidth={960}>
      <div className={feature.featureMain} style={{ maxWidth: 960 }}>
        <section className={feature.intro}>
          <p className={feature.eyebrow}>Conversational AI · Persistent memory</p>
          <h1 className={feature.title}>AI chat session</h1>
          <p className={feature.desc}>
            Ask about oral health, share photos for analysis, and get personalized
            recommendations — your conversation is tied to your patient account.
          </p>
        </section>
        <ChatInterface conversationStorageKey={getPatientConversationStorageKey()} />
      </div>
    </PortalDashboard>
  );
}

export function PatientDashboardHome() {
  const [firstName, setFirstName] = useState("");

  useEffect(() => {
    const u = getStoredUser("patient");
    if (u?.first_name) setFirstName(u.first_name);
  }, []);

  return (
    <PortalDashboard role="patient" maxWidth={960}>
      <section className={feature.intro}>
        <p className={feature.eyebrow}>Patient access</p>
        <h1 className={feature.title}>
          {firstName ? `Welcome, ${firstName}!` : "Welcome back"}
        </h1>
        <p className={feature.desc}>
          Run an AI teeth scan or start a chat session with your dental AI assistant.
        </p>
        <div className={feature.dashboardCards}>
          <Link href="/patient/scan" className={feature.card}>
            <div className={feature.cardIcon}>📷</div>
            <div className={feature.cardTitle}>AI scan</div>
            <p className={feature.cardDesc}>
              Snapshot, live video, or upload — get an instant diagnosis report.
            </p>
          </Link>
          <Link href="/patient/chat" className={feature.card}>
            <div className={feature.cardIcon}>💬</div>
            <div className={feature.cardTitle}>AI chat</div>
            <p className={feature.cardDesc}>
              Chat with DantShaant AI about your oral health and treatment options.
            </p>
          </Link>
          <Link href="/patient/scans" className={feature.card}>
            <div className={feature.cardIcon}>🗂️</div>
            <div className={feature.cardTitle}>My scans</div>
            <p className={feature.cardDesc}>Review your saved scan history.</p>
          </Link>
        </div>
      </section>
    </PortalDashboard>
  );
}
