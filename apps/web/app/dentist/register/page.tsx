import type { Metadata } from "next";
import { RegisterPage } from "@/components/portal/RegisterPage";

export const metadata: Metadata = {
  title: "Dentist Register — DantShaant",
};

export default function DentistRegisterPage() {
  return <RegisterPage role="dentist" />;
}
