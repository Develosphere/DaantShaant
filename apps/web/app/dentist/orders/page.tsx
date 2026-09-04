import type { Metadata } from "next";
import { OrdersManager } from "@/components/dentist/OrdersManager";

export const metadata: Metadata = {
  title: "Orders — Dentist Portal",
};

export default function DentistOrdersPage() {
  return <OrdersManager />;
}
