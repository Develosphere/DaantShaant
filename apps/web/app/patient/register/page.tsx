import type { Metadata } from "next";
import { RegisterPage } from "@/components/portal/RegisterPage";

export const metadata: Metadata = {
  title: "Patient Register — DantShaant",
};

export default function PatientRegisterPage() {
  return <RegisterPage role="patient" />;
}
