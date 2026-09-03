"use client";

import { useEffect, useRef, useState } from "react";
import { useLanguage } from "@/i18n";
import { getCurrentPosition, reverseGeocode, type PickedLocation } from "@/lib/geo-location";
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
  title,
  subtitle,
}: Props) {
  const { t, locale } = useLanguage();
  const [query, setQuery] = useState("");
  const [suggestions, setSuggestions] = useState<AddressSuggestion[]>([]);
  const [loadingSuggestions, setLoadingSuggestions] = useState(false);
  const [picked, setPicked] = useState<PickedLocation | null>(null);
  const [gpsLoading, setGpsLoading] = useState(false);
  const [error, setError] = useState("");
  const debounceTimerRef = useRef<NodeJS.Timeout | null>(null);

  const displayTitle = title || t("location.title");
  const displaySubtitle = subtitle || t("location.subtitle");

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
        const results = await fetchAddressSuggestions(val, locale);
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
      onConfirm(loc);
      return;
    }

    try {
      const resolved = await resolveAddressSuggestion(s.label, s.place_id, undefined, undefined, locale);
      if (resolved) {
        setPicked(resolved);
        setQuery(resolved.label);
        setSuggestions([]);
        onConfirm(resolved);
      } else {
        setError(t("dentists.location_timeout"));
      }
    } catch {
      setError(t("common.error"));
    }
  }

  function handleKeyDown(e: React.KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Enter") {
      e.preventDefault();
      if (suggestions.length > 0) {
        handleSelectSuggestion(suggestions[0]);
      } else if (picked) {
        onConfirm(picked);
      }
    }
  }

  async function handleGps() {
    if (gpsLoading) return;
    setGpsLoading(true);
    setError("");

    try {
      const pos = await getCurrentPosition();
      const lat = pos.coords.latitude;
      const lng = pos.coords.longitude;

      // Reverse geocode for display label with a fast timeout (so discovery is not blocked)
      let displayLabel = `${lat.toFixed(4)}, ${lng.toFixed(4)}`;
      try {
        const timeoutPromise = new Promise<string>((_, reject) =>
          setTimeout(() => reject(new Error("timeout")), 1200)
        );
        const fetchedLabel = await Promise.race([
          reverseGeocode(lat, lng, locale),
          timeoutPromise,
        ]);
        if (fetchedLabel) {
          displayLabel = fetchedLabel;
        }
      } catch {
        // Fallback to coordinates label
      }

      const loc: PickedLocation = {
        lat,
        lng,
        label: displayLabel,
      };
      setPicked(loc);
      // Immediately pass exact browser coordinates to discovery callback
      onConfirm(loc);
    } catch (err) {
      const msg = err instanceof Error ? err.message.toLowerCase() : "";
      if (msg.includes("denied") || msg.includes("permission")) {
        setError(t("dentists.location_denied"));
      } else if (msg.includes("timed out") || msg.includes("timeout")) {
        setError(t("dentists.location_timeout"));
      } else {
        setError(t("dentists.location_denied"));
      }
    } finally {
      setGpsLoading(false);
    }
  }

  if (!open) return null;

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
        <h2 className={styles.title}>{displayTitle}</h2>
        <p className={styles.sub}>{displaySubtitle}</p>

        <button
          type="button"
          disabled={gpsLoading}
          onClick={handleGps}
          style={{
            width: "100%",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            gap: "0.6rem",
            padding: "0.9rem 1.25rem",
            marginBottom: "1rem",
            borderRadius: "10px",
            background: "linear-gradient(135deg, #00a2f0, #073564)",
            color: "#ffffff",
            fontWeight: 700,
            fontSize: "0.95rem",
            border: "none",
            cursor: gpsLoading ? "wait" : "pointer",
            boxShadow: "0 4px 14px rgba(0, 162, 240, 0.28)",
          }}
        >
          <GpsIcon spinning={gpsLoading} />
          <span>{gpsLoading ? t("common.loading") : t("dentists.use_gps")}</span>
        </button>

        <div style={{ display: "flex", alignItems: "center", margin: "0.5rem 0 1.25rem", color: "var(--text-muted)", fontSize: "0.82rem" }}>
          <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
          <span style={{ padding: "0 0.75rem", textTransform: "uppercase", letterSpacing: "0.05em", fontWeight: 600 }}>{t("common.or")}</span>
          <div style={{ flex: 1, height: 1, background: "var(--border-default)" }} />
        </div>

        <span className={styles.label}>{t("location.label")}</span>
        <div className={styles.inputRow}>
          <div style={{ flex: 1, position: "relative" }}>
            <input
              type="text"
              className="input-field"
              placeholder={t("location.placeholder")}
              value={query}
              onChange={handleQueryChange}
              onKeyDown={handleKeyDown}
              style={{
                width: "100%",
                padding: "0.75rem 1rem",
                borderRadius: "8px",
                border: "1px solid var(--border-default)",
                background: "var(--bg-surface-raised)",
                color: "var(--text-primary)",
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
                  background: "var(--bg-surface)",
                  border: "1px solid var(--border-strong)",
                  borderRadius: "8px",
                  maxHeight: "220px",
                  overflowY: "auto",
                  boxShadow: "var(--shadow-card)",
                }}
              >
                {suggestions.map((s, idx) => (
                  <div
                    key={`${s.place_id}-${idx}`}
                    onClick={() => handleSelectSuggestion(s)}
                    style={{
                      padding: "0.6rem 0.85rem",
                      cursor: "pointer",
                      borderBottom: "1px solid var(--border-default)",
                      fontSize: "0.85rem",
                      color: "var(--text-primary)",
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = "var(--bg-surface-raised)")}
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
            title={t("dentists.use_gps")}
            aria-label={t("dentists.use_gps")}
            disabled={gpsLoading}
            onClick={handleGps}
          >
            <GpsIcon spinning={gpsLoading} />
          </button>
        </div>

        <p className={styles.hint}>
          {loadingSuggestions
            ? t("dentists.searching_locations")
            : t("location.helper")}
        </p>

        {picked && <p className={styles.selected}>{picked.label}</p>}
        {error && <p className={styles.error}>{error}</p>}

        <div className={styles.actions}>
          <button type="button" className={styles.btnGhost} onClick={onClose} disabled={gpsLoading}>
            {t("location.cancel")}
          </button>
          <button
            type="button"
            className={styles.btnPrimary}
            disabled={!picked || gpsLoading}
            onClick={() => picked && onConfirm(picked)}
          >
            {t("location.find")}
          </button>
        </div>
      </div>
    </div>
  );
}

