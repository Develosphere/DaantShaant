import type { Metadata } from "next";
import { ProductsManager } from "@/components/dentist/ProductsManager";

export const metadata: Metadata = {
  title: "Products — Dentist Portal",
};

export default function DentistProductsPage() {
  return <ProductsManager />;
}
