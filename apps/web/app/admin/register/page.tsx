import type { Metadata } from "next";
import { RegisterPage } from "@/components/portal/RegisterPage";

export const metadata: Metadata = {
  title: "Admin Register — DantShaant",
};

export default function AdminRegisterPage() {
  return <RegisterPage role="admin" />;
}
