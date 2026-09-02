"use client";

import { useEffect, useRef, useState } from "react";
import { getCurrentLocationLabel, type PickedLocation } from "@/lib/geo-location";
import { fetchAddressSuggestions, resolveAddressSuggestion, type AddressSuggestion } from "@/lib/location-autocomplete";
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
  subtitle = "Type your city or area (e.g. Karachi, Lahore, Dubai) or use GPS to find recommended dentists nearby.",
}: Props) {
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [picked, setPicked] = useState<PickedLocation | null>(null);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [error, setError] = useState("");
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setSuggestions([]);
      setPicked(null);
      setGpsLoading(false);
      setError("");
      if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
      return;
    }
  }, [open]);

  function handleQueryChange(e: React.ChangeEvent<HTMLInputElement>) {
    const val = e.target.value;
    setQuery(val);
    setError("");

    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);

    if (val.trim().length < 2) {
      setSuggestions([]);
      return;
    }

    setLoadingSuggestions(true);
    debounceTimerRef.current = setTimeout(async () => {
      try {
        const results = await fetchAddressSuggestions(val);
        setSuggestions(results);
      } catch {
        setSuggestions([]);
      } finally {
        setLoadingSuggestions(false);
      }
    }, 350);
  }

  async function handleSelectSuggestion(s: AddressSuggestion) {
    setError("");
    if (s.lat != null && s.lng != null) {
      const loc: PickedLocation = {
        lat: s.lat,
        lng: s.lng,
        label: s.label,
      };
      setPicked(loc);
      setQuery(s.label);
      setSuggestions([]);
      return;
    }

    try {
      const resolved = await resolveAddressSuggestion(s.label, s.place_id);
      if (resolved) {
        setPicked(resolved);
        setQuery(resolved.label);
        setSuggestions([]);
      } else {
        setError("Could not resolve location coordinates. Try another suggestion or GPS.");
      }
    } catch {
      setError("Could not resolve location coordinates.");
    }
  }

  async function handleGps() {
    if (gpsLoading) return;
    setGpsLoading(true);
    setError("");

    try {
      const loc = await getCurrentLocationLabel();
      setPicked(loc);
      setQuery(loc.label);
      setSuggestions([]);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Could not get your GPS location — type your city or address instead."
      );
    } finally {
      setGpsLoading(false);
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
          <div style={{ flex: 1, position: "relative" }}>
            <input
              type="text"
              className="input-field"
              placeholder="e.g. Clifton, Karachi or Dubai Marina"
              value={query}
              onChange={handleQueryChange}
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid var(--color-border, #334155)",
                background: "var(--color-bg-secondary, #1e293b)",
                color: "#fff",
                fontSize: "0.95rem",
              }}
            />
            {suggestions.length > 0 && (
              <div
                style={{
                  position: "absolute",
                  top: "105%",
                  left: 0,
                  right: 0,
                  zIndex: 2000,
                  background: "#1e293b",
                  border: "1px solid #334155",
                  borderRadius: "8px",
                  maxHeight: "220px",
                  overflowY: "auto",
                  boxShadow: "0 10px 25px rgba(0,0,0,0.5)",
                }}
              >
                {suggestions.map((s, idx) => (
                  <div
                    key={`${s.place_id}-${idx}`}
                    onClick={() => handleSelectSuggestion(s)}
                    style={{
                      padding: "0.6rem 0.85rem",
                      cursor: "pointer",
                      borderBottom: "1px solid #334155",
                      fontSize: "0.85rem",
                      color: "#e2e8f0",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "#334155")}
                    onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                  >
                    📍 {s.label}
                  </div>
                ))}
              </div>
            )}
          </div>
          <button
            type="button"
            className={styles.gpsBtn}
            title="Use current GPS location"
            aria-label="Use current GPS location"
            disabled={gpsLoading}
            onClick={handleGps}
          >
            <GpsIcon spinning={gpsLoading} />
          </button>
        </div>

        <p className={styles.hint}>
          {loadingSuggestions
            ? "Searching OpenStreetMap locations…"
            : "Type for OSM address suggestions, or tap GPS to use current position."}
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
