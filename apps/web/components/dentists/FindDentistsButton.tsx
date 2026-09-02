"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { getStoredUser } from "@/lib/portal-auth";
import type { PickedLocation } from "@/lib/geo-location";
import { LocationPickerModal } from "./LocationPickerModal";

type Props = {
  issue: string;
  scanId: string;
  severity: string;
  className?: string;
  style?: React.CSSProperties;
};

export function FindDentistsButton({ issue, scanId, severity, className, style }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const isLoggedIn = !!getStoredUser("patient");

  function buildUrl(loc: PickedLocation) {
    const params = new URLSearchParams({
      issue,
      scan_id: scanId,
      severity,
      lat: String(loc.lat),
      lng: String(loc.lng),
      location: loc.label,
    });
    return `/patient/dentists?${params.toString()}`;
  }

  function handleConfirm(loc: PickedLocation) {
    setOpen(false);
    router.push(buildUrl(loc));
  }

  if (!isLoggedIn) {
    return (
      <a
        href="/patient/login"
        className={className ?? "btn btn-secondary"}
        style={{ display: "block", textAlign: "center", textDecoration: "none", ...style }}
      >
        Sign in to find recommended dentists
      </a>
    );
  }

  return (
    <>
      <button
        type="button"
        className={className ?? "btn btn-glow"}
        style={{
          display: "inline-flex",
          alignItems: "center",
          gap: "0.5rem",
          width: "100%",
          justifyContent: "center",
          ...style,
        }}
        onClick={() => setOpen(true)}
      >
        🗺️ Find recommended dentists
      </button>
      <LocationPickerModal
        open={open}
        onClose={() => setOpen(false)}
        onConfirm={handleConfirm}
      />
    </>
  );
}
