import type { Metadata } from "next";
import { PatientDashboardHome } from "@/components/portal/PatientFeatureViews";

export const metadata: Metadata = {
  title: "Dashboard — Patient Portal",
};

export default function PatientDashboardPage() {
  return <PatientDashboardHome />;
}
