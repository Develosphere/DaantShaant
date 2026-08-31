import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Patient Portal — DantShaant",
  description: "Patient sign in, registration, and dashboard",
};

export default function PatientLayout({ children }: { children: React.ReactNode }) {
  return children;
}
