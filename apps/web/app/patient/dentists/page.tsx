import type { Metadata } from "next";
import { Suspense } from "react";
import { DentistMapView } from "@/components/dentists/DentistMapView";

export const metadata: Metadata = {
  title: "Find Dentists — Patient Portal",
};

export default function PatientDentistsPage() {
  return (
    <Suspense fallback={<p style={{ padding: "2rem", color: "#8b9bb8" }}>Loading map…</p>}>
      <DentistMapView />
    </Suspense>
  );
}
