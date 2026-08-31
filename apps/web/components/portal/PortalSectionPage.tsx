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
          background: "rgba(18, 24, 38, 0.72)",
          border: "1px solid rgba(255, 255, 255, 0.08)",
          borderRadius: "24px",
          padding: "2rem",
          boxShadow: "0 24px 80px rgba(0, 0, 0, 0.55)",
        }}
      >
        <h1 style={{ margin: "0 0 0.75rem", fontSize: "1.5rem" }}>{title}</h1>
        <p style={{ margin: 0, color: "#8b9bb8" }}>{description}</p>
      </section>
    </PortalDashboard>
  );
}
