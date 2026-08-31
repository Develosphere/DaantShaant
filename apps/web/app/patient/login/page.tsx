import type { Metadata } from "next";
import { LoginPage } from "@/components/portal/LoginPage";

export const metadata: Metadata = {
  title: "Patient Sign In — DantShaant",
};

export default function PatientLoginPage() {
  return <LoginPage role="patient" />;
}
