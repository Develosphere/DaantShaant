import type { Metadata } from "next";
import { PatientOrdersView } from "@/components/patient/PatientOrdersView";

export const metadata: Metadata = {
  title: "My Orders — Patient Portal",
  description: "View your purchased oral care products and order history.",
};

export default function PatientOrdersPage() {
  return <PatientOrdersView />;
}
