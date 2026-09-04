import type { Metadata } from "next";
import { DentistDashboardHome } from "@/components/dentist/DentistDashboardHome";

export const metadata: Metadata = {
  title: "Dashboard — Dentist Portal",
  description: "Dentist practice dashboard, products, appointments, and orders overview.",
};

export default function DentistDashboardPage() {
  return <DentistDashboardHome />;
}
