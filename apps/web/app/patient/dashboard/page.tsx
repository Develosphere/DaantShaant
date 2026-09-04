import type { Metadata } from "next";
import { PatientDashboardView } from "@/components/patient/PatientDashboardView";

export const metadata: Metadata = {
  title: "Dashboard — Patient Portal",
};

export default function PatientDashboardPage() {
  return <PatientDashboardView />;
}
