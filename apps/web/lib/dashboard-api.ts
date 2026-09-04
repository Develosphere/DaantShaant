import { API_BASE, authorizedFetch } from "./portal-auth";

export interface PatientDashboardStats {
  scan_count: number;
  order_count: number;
  oral_status: "routine" | "soon" | "urgent" | "emergency" | null;
}

export interface LatestScreeningSummary {
  scan_id: string;
  created_at: string;
  verdict: string;
  summary: string;
  urgency: "routine" | "soon" | "urgent" | "emergency";
  confidence: number;
  recommended_specialist: string;
  major_concerns: string[];
}

export interface DashboardProductItem {
  product_id: string;
  name: string;
  category: string;
  price: number;
  dentist_name: string;
}

export interface DashboardOrderItem {
  order_id: string;
  product_id: string;
  product_name: string;
  dentist_name?: string;
  seller_name?: string;
  quantity: number;
  price: number;
  status: string;
  created_at: string;
}

export interface DashboardActivityItem {
  id: string;
  type: "scan" | "order" | "appointment";
  title: string;
  description: string;
  created_at: string;
}

export interface PatientDashboardResponse {
  stats: PatientDashboardStats;
  latest_screening: LatestScreeningSummary | null;
  recommended_products: DashboardProductItem[];
  recent_orders: DashboardOrderItem[];
  recent_activity: DashboardActivityItem[];
}

export interface DentistDashboardStats {
  product_count: number;
  order_count: number;
  pending_order_count: number;
  completed_order_count: number;
  appointment_count: number;
  pending_appointment_count: number;
}

export interface DentistDashboardOrderItem {
  order_id: string;
  product_id?: string;
  product_name: string;
  quantity: number;
  price: number;
  patient_name: string;
  patient_email?: string;
  status: string;
  created_at: string;
}

export interface DentistDashboardAppointmentItem {
  appointment_id: string;
  issue: string | null;
  status: string;
  preferred_time?: string | null;
  patient_name: string;
  patient_email?: string;
  created_at: string;
}

export interface DentistDashboardResponse {
  stats: DentistDashboardStats;
  recent_orders: DentistDashboardOrderItem[];
  recent_appointments: DentistDashboardAppointmentItem[];
}

export async function getPatientDashboard(): Promise<PatientDashboardResponse> {
  const res = await authorizedFetch("patient", `${API_BASE}/portal/patient/dashboard`);
  if (!res.ok) {
    throw new Error(`Failed to load patient dashboard: ${res.statusText}`);
  }
  return res.json();
}

export async function getDentistDashboard(): Promise<DentistDashboardResponse> {
  const res = await authorizedFetch("dentist", `${API_BASE}/portal/dentist/dashboard`);
  if (!res.ok) {
    throw new Error(`Failed to load dentist dashboard: ${res.statusText}`);
  }
  return res.json();
}
