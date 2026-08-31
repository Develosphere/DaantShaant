import type { Metadata } from "next";
import { PatientChatView } from "@/components/portal/PatientFeatureViews";

export const metadata: Metadata = {
  title: "AI Chat — Patient Portal",
};

export default function PatientChatPage() {
  return <PatientChatView />;
}
