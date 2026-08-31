import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Admin Portal — DantShaant",
  description: "Platform administration for DantShaant",
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return children;
}
