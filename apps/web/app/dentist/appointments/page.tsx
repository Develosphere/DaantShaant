import type { Metadata } from "next";
import { AppointmentsManager } from "@/components/dentist/AppointmentsManager";

export const metadata: Metadata = {
  title: "Appointments — Dentist Portal",
};

export default function DentistAppointmentsPage() {
  return <AppointmentsManager />;
}
