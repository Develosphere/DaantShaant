import type { Metadata } from "next";
import { PortalSectionPage } from "@/components/portal/PortalSectionPage";

export const metadata: Metadata = {
  title: "Orders — Dentist Portal",
};

export default function DentistOrdersPage() {
  return (
    <PortalSectionPage
      role="dentist"
      title="Orders"
      description="Patient orders and notifications will appear here. Coming soon."
    />
  );
}
