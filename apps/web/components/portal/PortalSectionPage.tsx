import { PortalDashboard } from "@/components/portal/PortalDashboard";
import type { PortalRole } from "@/lib/portal-types";

type Props = {
  role: PortalRole;
  title: string;
  description: string;
};

export function PortalSectionPage({ role, title, description }: Props) {
  return (
    <PortalDashboard role={role}>
      <section
        style={{
          background: "var(--bg-surface-raised)",
          border: "1px solid var(--border-default)",
          borderRadius: "24px",
          padding: "2rem",
          boxShadow: "var(--shadow-card)",
        }}
      >
        <h1 style={{ margin: "0 0 0.75rem", fontSize: "1.5rem", color: "var(--text-primary)" }}>{title}</h1>
        <p style={{ margin: 0, color: "var(--text-muted)" }}>{description}</p>
      </section>
    </PortalDashboard>
  );
}

