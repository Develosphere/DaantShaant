import type { Metadata } from "next";
import { LoginPage } from "@/components/portal/LoginPage";

export const metadata: Metadata = {
  title: "Dentist Sign In — DantShaant",
};

export default function DentistLoginPage() {
  return <LoginPage role="dentist" />;
}
