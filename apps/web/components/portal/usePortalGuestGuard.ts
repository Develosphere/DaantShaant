"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import type { PortalRole } from "@/lib/portal-types";
import { refreshPortalSession } from "@/lib/portal-auth";

/** Redirect if any portal session is already active (same role → dashboard, other → that portal). */
export function usePortalGuestGuard(role: PortalRole) {
  const router = useRouter();

  useEffect(() => {
    refreshPortalSession().then((user) => {
      if (!user) return;
      router.replace(
        user.role === role ? `/${role}/dashboard` : `/${user.role}/dashboard`
      );
    });
  }, [role, router]);
}
