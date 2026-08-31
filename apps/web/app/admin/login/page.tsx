import type { Metadata } from "next";
import { LoginPage } from "@/components/portal/LoginPage";

export const metadata: Metadata = {
  title: "Admin Sign In — DantShaant",
};

export default function AdminLoginPage() {
  return <LoginPage role="admin" />;
}
