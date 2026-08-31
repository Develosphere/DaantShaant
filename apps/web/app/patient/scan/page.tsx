import type { Metadata } from "next";
import { PatientScanView } from "@/components/portal/PatientFeatureViews";

export const metadata: Metadata = {
  title: "AI Scan — Patient Portal",
};

export default function PatientScanPage() {
  return <PatientScanView />;
}
