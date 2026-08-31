"use client";

import { useEffect, useRef, useState } from "react";
import { getCurrentLocationLabel, type PickedLocation } from "@/lib/google-maps";
import {
  loadGooglePlacePickerLibrary,
  placeToLocation,
  type GmpPlacePickerElement,
} from "@/lib/google-place-picker";
import styles from "./location-picker.module.css";

type Props = {
  open: boolean;
  onClose: () => void;
  onConfirm: (location: PickedLocation) => void;
  title?: string;
  subtitle?: string;
};

function GpsIcon({ spinning }: { spinning?: boolean }) {
  return (
    <svg
      className={spinning ? styles.gpsSpin : undefined}
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden
    >
      <path
        d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7z"
        stroke="currentColor"
        strokeWidth="1.75"
        strokeLinejoin="round"
      />
      <circle cx="12" cy="9" r="2.5" stroke="currentColor" strokeWidth="1.75" />
    </svg>
  );
}

export function LocationPickerModal({
  open,
  onClose,
  onConfirm,
  title = "Where are you located?",
  subtitle = "Type your city or address, pick a suggestion, or use GPS so we can find dentists near you.",
}: Props) {
  const pickerHostRef = useRef<HTMLDivElement>(null);
  const pickerRef = useRef<GmpPlacePickerElement | null>(null);
  const gpsAbortRef = useRef(false);

  const [pickerReady, setPickerReady] = useState(false);
  const [picked, setPicked] = useState<PickedLocation | null>(null);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!open) {
      gpsAbortRef.current = true;
      setPicked(null);
      setGpsLoading(false);
      setPickerReady(false);
      setError("");
      pickerRef.current = null;
      if (pickerHostRef.current) pickerHostRef.current.innerHTML = "";
      return;
    }

    gpsAbortRef.current = false;
    let cancelled = false;

    loadGooglePlacePickerLibrary()
      .then(async () => {
        if (cancelled || !pickerHostRef.current) return;

        pickerHostRef.current.innerHTML = "";
        const picker = document.createElement("gmpx-place-picker") as GmpPlacePickerElement;
        picker.setAttribute("placeholder", "e.g. Karachi, Pakistan");
        picker.className = styles.placePicker;

        const onPlaceChange = () => {
          const loc = placeToLocation(picker.value);
          if (!loc) {
            setError("Pick an address from the suggestions list");
            setPicked(null);
            return;
          }
          setError("");
          setPicked(loc);
        };

        picker.addEventListener("gmpx-placechange", onPlaceChange);
        pickerHostRef.current.appendChild(picker);
        pickerRef.current = picker;
        setPickerReady(true);
      })
      .catch((err) => {
        if (!cancelled) {
          setPickerReady(false);
          setError(
            err instanceof Error
              ? err.message
              : "Could not load address search — use GPS instead"
          );
        }
      });

    return () => {
      cancelled = true;
      pickerRef.current = null;
      if (pickerHostRef.current) pickerHostRef.current.innerHTML = "";
    };
  }, [open]);

  async function handleGps() {
    if (gpsLoading) return;

    setGpsLoading(true);
    setError("");
    gpsAbortRef.current = false;

    try {
      const loc = await getCurrentLocationLabel();
      if (gpsAbortRef.current) return;
      setPicked(loc);
      setError("");
    } catch (err) {
      if (gpsAbortRef.current) return;
      setError(
        err instanceof Error
          ? err.message
          : "Could not get your location — type your address instead"
      );
    } finally {
      if (!gpsAbortRef.current) setGpsLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>{title}</h2>
        <p className={styles.sub}>{subtitle}</p>

        <span className={styles.label}>Your location</span>
        <div className={styles.inputRow}>
          <div className={styles.inputWrap} ref={pickerHostRef} />
          <button
            type="button"
            className={styles.gpsBtn}
            title="Use current location"
            aria-label="Use current location"
            disabled={gpsLoading}
            onClick={handleGps}
          >
            <GpsIcon spinning={gpsLoading} />
          </button>
        </div>

        <p className={styles.hint}>
          {pickerReady
            ? "Start typing for Google address suggestions, or use the pin for GPS."
            : "Loading address search… You can use the pin for GPS while waiting."}
        </p>

        {picked && <p className={styles.selected}>Selected: {picked.label}</p>}
        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button type="button" className={styles.btnGhost} onClick={onClose} disabled={gpsLoading}>
            Cancel
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            disabled={!picked || gpsLoading}
            onClick={() => picked && onConfirm(picked)}
          >
            Find dentists
          </button>
        </div>
      </div>
    </div>
  );
}
