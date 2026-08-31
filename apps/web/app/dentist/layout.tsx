import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Dentist Portal — DantShaant",
  description: "Dentist sign in, registration, and practice dashboard",
};

export default function DentistLayout({ children }: { children: React.ReactNode }) {
  return children;
}
