"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { PortalRole } from "@/lib/portal-types";
import { getActivePortalRole } from "@/lib/portal-auth";

/** Redirect if any portal session is already active (same role → dashboard, other → that portal). */
export function usePortalGuestGuard(role: PortalRole) {
  const router = useRouter();

  useEffect(() => {
    const active = getActivePortalRole();
    if (!active) return;
    router.replace(active === role ? `/${role}/dashboard` : `/${active}/dashboard`);
  }, [role, router]);
}
