import type { Metadata } from "next";
import { PortalSectionPage } from "@/components/portal/PortalSectionPage";

export const metadata: Metadata = {
  title: "My Scans — Patient Portal",
};

export default function PatientScansPage() {
  return (
    <PortalSectionPage
      role="patient"
      title="My scans"
      description="Your saved teeth scans will appear here. This section is coming soon."
    />
  );
}
