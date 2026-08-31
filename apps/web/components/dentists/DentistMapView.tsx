"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { LocationPickerModal } from "@/components/dentists/LocationPickerModal";
import {
  bookConsultation,
  fetchDentistRecommendations,
  type DentistPin,
} from "@/lib/dentist-recommend";
import { loadGoogleMaps, type PickedLocation } from "@/lib/google-maps";
import styles from "./dentist-map.module.css";

function pinIcon(isBest: boolean): google.maps.Icon {
  const color = isBest ? "#22c55e" : "#94a3b8";
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="32" height="42" viewBox="0 0 32 42">
    <path fill="${color}" stroke="#fff" stroke-width="1.5" d="M16 0C7.2 0 0 7.2 0 16c0 12 16 26 16 26s16-14 16-26C32 7.2 24.8 0 16 0z"/>
    <circle cx="16" cy="16" r="6" fill="#fff"/>
  </svg>`;
  return {
    url: `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`,
    scaledSize: new google.maps.Size(32, 42),
    anchor: new google.maps.Point(16, 42),
  };
}

function parseCoord(value: string | null): number | undefined {
  if (!value) return undefined;
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : undefined;
}

export function DentistMapView() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const issue = searchParams.get("issue") ?? "dental checkup";
  const scanId = searchParams.get("scan_id") ?? undefined;
  const severity = searchParams.get("severity") ?? "moderate";
  const locationLabel = searchParams.get("location") ?? "";
  const urlLat = parseCoord(searchParams.get("lat"));
  const urlLng = parseCoord(searchParams.get("lng"));
  const hasCoords = urlLat !== undefined && urlLng !== undefined;

  const mapRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<google.maps.Map | null>(null);
  const markersRef = useRef<google.maps.Marker[]>([]);

  const [dentists, setDentists] = useState<DentistPin[]>([]);
  const [sessionId, setSessionId] = useState<string>("");
  const [loading, setLoading] = useState(hasCoords);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<DentistPin | null>(null);
  const [booking, setBooking] = useState(false);
  const [bookMsg, setBookMsg] = useState("");
  const [locationModalOpen, setLocationModalOpen] = useState(!hasCoords);

  const renderMap = useCallback(
    (center: { lat: number; lng: number }, pins: DentistPin[]) => {
      if (!mapRef.current || !window.google?.maps) {
        console.error("Map container or Google Maps not available");
        return;
      }

      try {
        if (!mapInstance.current) {
          mapInstance.current = new google.maps.Map(mapRef.current, {
            center,
            zoom: 12,
            mapTypeControl: false,
            streetViewControl: false,
            fullscreenControl: true,
            zoomControl: true,
            styles: [
              {
                featureType: "poi",
                elementType: "labels",
                stylers: [{ visibility: "off" }],
              },
            ],
          });
          console.log("Map initialized successfully");
        } else {
          mapInstance.current.setCenter(center);
        }

        markersRef.current.forEach((m) => m.setMap(null));
        markersRef.current = [];

        const patientMarker = new google.maps.Marker({
          position: center,
          map: mapInstance.current,
          title: "You",
          icon: {
            path: google.maps.SymbolPath.CIRCLE,
            scale: 10,
            fillColor: "#00a2f0",
            fillOpacity: 1,
            strokeColor: "#fff",
            strokeWeight: 2,
          },
          zIndex: 1000,
        });
        markersRef.current.push(patientMarker);

        pins.forEach((d) => {
          const marker = new google.maps.Marker({
            position: { lat: d.lat, lng: d.lng },
            map: mapInstance.current!,
            title: d.name,
            icon: pinIcon(d.is_best),
          });
          marker.addListener("click", () => setSelected(d));
          markersRef.current.push(marker);
        });

        if (pins.length > 0) {
          const bounds = new google.maps.LatLngBounds();
          bounds.extend(center);
          pins.forEach((d) => bounds.extend({ lat: d.lat, lng: d.lng }));
          mapInstance.current.fitBounds(bounds, 48);
        }
      } catch (err) {
        console.error("Error rendering map:", err);
      }
    },
    []
  );

  const loadRecommendations = useCallback(
    async (lat: number, lng: number) => {
      setLoading(true);
      setError("");
      try {
        console.log("Loading Google Maps...");
        await loadGoogleMaps();
        console.log("Google Maps loaded, fetching dentists...");
        const data = await fetchDentistRecommendations({
          issue,
          lat,
          lng,
          severity,
          scan_id: scanId,
        });
        console.log("Dentists fetched:", data.dentists.length);
        setDentists(data.dentists);
        setSessionId(data.session_id);
        console.log("Rendering map...");
        renderMap({ lat: data.patient_lat, lng: data.patient_lng }, data.dentists);
      } catch (err) {
        console.error("Error loading recommendations:", err);
        setError(err instanceof Error ? err.message : "Could not load recommendations");
      } finally {
        setLoading(false);
      }
    },
    [issue, scanId, severity, renderMap]
  );

  useEffect(() => {
    if (!hasCoords || urlLat === undefined || urlLng === undefined) return;
    loadRecommendations(urlLat, urlLng);
  }, [hasCoords, urlLat, urlLng, loadRecommendations]);

  function handleLocationConfirm(loc: PickedLocation) {
    setLocationModalOpen(false);
    const params = new URLSearchParams(searchParams.toString());
    params.set("lat", String(loc.lat));
    params.set("lng", String(loc.lng));
    params.set("location", loc.label);
    router.replace(`/patient/dentists?${params.toString()}`);
  }

  async function handleBook() {
    if (!selected?.dentist_id) return;
    setBooking(true);
    setBookMsg("");
    try {
      const res = await bookConsultation({
        dentist_id: selected.dentist_id,
        issue,
        scan_id: scanId,
        session_id: sessionId,
      });
      setBookMsg(res.message);
    } catch (err) {
      setBookMsg(err instanceof Error ? err.message : "Booking failed");
    } finally {
      setBooking(false);
    }
  }

  return (
    <PortalDashboard role="patient" maxWidth={1200}>
      <LocationPickerModal
        open={locationModalOpen}
        onClose={() => {
          if (!hasCoords) router.push("/patient/scan");
          else setLocationModalOpen(false);
        }}
        onConfirm={handleLocationConfirm}
      />

      <div className={styles.layout}>
        <div className={styles.header}>
          <h1 className={styles.title}>Recommended dentists</h1>
          <p className={styles.sub}>
            Based on your scan: <strong>{issue.replace(/_/g, " ")}</strong>
            {locationLabel && (
              <>
                {" "}
                · Near <strong>{locationLabel}</strong>
              </>
            )}
          </p>
          {hasCoords && (
            <button
              type="button"
              className={styles.changeLocation}
              onClick={() => setLocationModalOpen(true)}
            >
              📍 Change location
            </button>
          )}
          <div className={styles.legend}>
            <span className={styles.legendItem}>
              <span className={styles.legendDotBest} /> Best match for your scan
            </span>
            <span className={styles.legendItem}>
              <span className={styles.legendDotOther} /> Other recommendations
            </span>
          </div>
        </div>

        {loading && (
          <div className={styles.loadingContainer}>
            <div className={styles.spinner} />
            <p className={styles.loading}>Finding dentists near you…</p>
          </div>
        )}

        {error && (
          <div className={styles.errorContainer}>
            <p className={styles.error}>⚠️ {error}</p>
            <button
              type="button"
              className={styles.btnRetry}
              onClick={() => setLocationModalOpen(true)}
            >
              Try different location
            </button>
          </div>
        )}

        {!loading && !error && hasCoords && dentists.length === 0 && (
          <div className={styles.emptyContainer}>
            <p className={styles.empty}>
              No dentists found in this area yet. Try expanding your search radius or contact
              support.
            </p>
          </div>
        )}

        {!loading && !error && hasCoords && dentists.length > 0 && (
          <div className={styles.sidebar}>
            <div className={styles.mapWrap}>
              {!mapInstance.current && (
                <div className={styles.mapPlaceholder}>
                  <div className={styles.mapSpinner} />
                  <p>Loading map...</p>
                </div>
              )}
              <div ref={mapRef} className={styles.mapCanvas} />
            </div>

            <div className={styles.list}>
              {dentists.map((d) => (
                <button
                  key={`${d.tier}-${d.dentist_id ?? d.place_id}-${d.rank}`}
                  type="button"
                  className={`${styles.listItem} ${d.is_best ? styles.listItemBest : ""} ${
                    selected?.rank === d.rank ? styles.listItemActive : ""
                  }`}
                  onClick={() => setSelected(d)}
                >
                  {d.is_best && <span className={styles.badgeBest}>Best match</span>}
                  {d.tier === "platform" && (
                    <span className={styles.badgePartner}>Partner</span>
                  )}
                  <div className={styles.listName}>{d.name}</div>
                  <div className={styles.listMeta}>
                    {d.clinic_name || d.address} · {d.distance_km.toFixed(1)} km
                    {d.rating ? ` · ★ ${d.rating}` : ""}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {selected && (
          <div className={styles.modalOverlay} onClick={() => setSelected(null)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              {selected.is_best && <span className={styles.badgeBest}>Best match</span>}
              <h3>{selected.name}</h3>
              <p className={styles.modalClinic}>{selected.clinic_name || selected.address}</p>
              <p className={styles.modalReason}>{selected.recommendation_reason}</p>
              <p className={styles.modalRow}>
                {selected.distance_km.toFixed(1)} km away
                {selected.rating ? ` · ★ ${selected.rating}` : ""}
              </p>
              {selected.address && <p className={styles.modalRow}>{selected.address}</p>}
              {selected.phone && <p className={styles.modalRow}>📞 {selected.phone}</p>}

              <div className={styles.modalActions}>
                {selected.tier === "platform" && selected.dentist_id ? (
                  <button
                    type="button"
                    className={styles.btnPrimary}
                    disabled={booking}
                    onClick={handleBook}
                  >
                    {booking ? "Sending…" : "Book consultation"}
                  </button>
                ) : selected.phone ? (
                  <a href={`tel:${selected.phone}`} className={styles.btnPrimary}>
                    Contact dentist
                  </a>
                ) : (
                  <span className={styles.modalRow}>Phone not available</span>
                )}
              </div>
              {bookMsg && <p className={styles.bookMessage}>{bookMsg}</p>}
              <button type="button" className={styles.btnClose} onClick={() => setSelected(null)}>
                Close
              </button>
            </div>
          </div>
        )}
      </div>
    </PortalDashboard>
  );
}
