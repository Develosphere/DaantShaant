"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useLanguage } from "@/i18n";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import { LocationPickerModal } from "@/components/dentists/LocationPickerModal";
import {
  bookConsultation,
  fetchDentistRecommendations,
  type DentistPin,
} from "@/lib/dentist-recommend";
import { type PickedLocation } from "@/lib/geo-location";
import { ensureMapLibreCSS, maplibregl, OPENFREEMAP_LIBERTY_STYLE } from "@/lib/maplibre";
import styles from "./dentist-map.module.css";

function parseCoord(value: string | null): number | undefined {
  if (!value) return undefined;
  const n = parseFloat(value);
  return Number.isFinite(n) ? n : undefined;
}

function createGeoJsonCircle(center: [number, number], radiusKm: number, points = 64) {
  const coords: [number, number][] = [];
  const distanceX = radiusKm / (111.32 * Math.cos((center[1] * Math.PI) / 180));
  const distanceY = radiusKm / 110.574;

  for (let i = 0; i < points; i++) {
    const theta = (i / points) * (2 * Math.PI);
    const x = distanceX * Math.cos(theta);
    const y = distanceY * Math.sin(theta);
    coords.push([center[0] + x, center[1] + y]);
  }
  coords.push(coords[0]);
  return {
    type: "Feature" as const,
    geometry: {
      type: "Polygon" as const,
      coordinates: [coords],
    },
    properties: {},
  };
}

export function DentistMapView() {
  const { t, locale } = useLanguage();
  const router = useRouter();
  const searchParams = useSearchParams();
  const issue = searchParams.get("issue") ?? "dental checkup";
  const rawScanId = searchParams.get("scan_id");
  const scanId =
    rawScanId && rawScanId.trim() && rawScanId !== "undefined" && rawScanId !== "null"
      ? rawScanId.trim()
      : undefined;
  const severity = searchParams.get("severity") ?? "moderate";
  const locationLabel = searchParams.get("location") ?? "";
  const urlLat = parseCoord(searchParams.get("lat"));
  const urlLng = parseCoord(searchParams.get("lng"));
  const hasCoords = urlLat !== undefined && urlLng !== undefined;

  const mapContainerRef = useRef<HTMLDivElement>(null);
  const mapInstance = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);

  const [dentists, setDentists] = useState<DentistPin[]>([]);
  const [pickedLocation, setPickedLocation] = useState<PickedLocation | null>(
    hasCoords && urlLat !== undefined && urlLng !== undefined
      ? { label: locationLabel, lat: urlLat, lng: urlLng }
      : null
  );
  const [patientCoords, setPatientCoords] = useState<{ lat: number; lng: number } | null>(
    hasCoords && urlLat !== undefined && urlLng !== undefined
      ? { lat: urlLat, lng: urlLng }
      : null
  );
  const [searchRadiusKm, setSearchRadiusKm] = useState<number | null>(null);
  const [sessionId, setSessionId] = useState<string>("");
  const [loading, setLoading] = useState(hasCoords);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<DentistPin | null>(null);
  const [booking, setBooking] = useState(false);
  const [bookMsg, setBookMsg] = useState("");
  const [locationModalOpen, setLocationModalOpen] = useState(!hasCoords);

  const renderMap = useCallback(
    (center: { lat: number; lng: number }, pins: DentistPin[], radiusKm?: number) => {
      if (!mapContainerRef.current) return;
      ensureMapLibreCSS();

      try {
        if (!mapInstance.current) {
          mapInstance.current = new maplibregl.Map({
            container: mapContainerRef.current,
            style: OPENFREEMAP_LIBERTY_STYLE,
            center: [center.lng, center.lat],
            zoom: 12,
            attributionControl: false,
          });

          mapInstance.current.addControl(
            new maplibregl.AttributionControl({
              customAttribution:
                '© <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noreferrer">OpenStreetMap</a> contributors | Style: <a href="https://openfreemap.org" target="_blank" rel="noreferrer">OpenFreeMap</a>',
            }),
            "bottom-right"
          );

          mapInstance.current.addControl(new maplibregl.NavigationControl(), "top-right");
        } else {
          mapInstance.current.flyTo({ center: [center.lng, center.lat], zoom: 12 });
        }

        // Clean existing markers
        markersRef.current.forEach((m) => m.remove());
        markersRef.current = [];

        // 1. User / Patient Marker
        const userEl = document.createElement("div");
        userEl.className = "user-pulse-marker";
        userEl.style.width = "18px";
        userEl.style.height = "18px";
        userEl.style.borderRadius = "50%";
        userEl.style.backgroundColor = "#00a2f0";
        userEl.style.border = "3px solid #ffffff";
        userEl.style.boxShadow = "0 0 10px rgba(0, 162, 240, 0.8)";
        userEl.title = "Your location";

        const patientMarker = new maplibregl.Marker({ element: userEl })
          .setLngLat([center.lng, center.lat])
          .addTo(mapInstance.current);
        markersRef.current.push(patientMarker);

        // 2. Search Radius Circle Visualization
        if (radiusKm && radiusKm > 0) {
          const circleFeature = createGeoJsonCircle([center.lng, center.lat], radiusKm);
          const drawCircle = () => {
            if (!mapInstance.current) return;
            const existingSource = mapInstance.current.getSource("search-radius") as maplibregl.GeoJSONSource | undefined;
            if (existingSource) {
              existingSource.setData(circleFeature);
            } else if (mapInstance.current.isStyleLoaded()) {
              try {
                mapInstance.current.addSource("search-radius", {
                  type: "geojson",
                  data: circleFeature,
                });
                mapInstance.current.addLayer({
                  id: "search-radius-fill",
                  type: "fill",
                  source: "search-radius",
                  paint: {
                    "fill-color": "#00a2f0",
                    "fill-opacity": 0.08,
                  },
                });
                mapInstance.current.addLayer({
                  id: "search-radius-stroke",
                  type: "line",
                  source: "search-radius",
                  paint: {
                    "line-color": "#00a2f0",
                    "line-width": 1.5,
                    "line-dasharray": [2, 2],
                    "line-opacity": 0.5,
                  },
                });
              } catch (e) {
                // Ignore layer addition collision
              }
            }
          };

          if (mapInstance.current.isStyleLoaded()) {
            drawCircle();
          } else {
            mapInstance.current.once("load", drawCircle);
          }
        }

        // 3. Dentist Pins
        pins.forEach((d) => {
          const pinEl = document.createElement("div");
          pinEl.style.cursor = "pointer";
          pinEl.style.transform = "translate(-50%, -100%)";

          const color = d.is_best ? "#22c55e" : d.tier === "platform" ? "#3b82f6" : "#64748b";
          pinEl.innerHTML = `
            <svg width="28" height="36" viewBox="0 0 32 42" fill="none" xmlns="http://www.w3.org/2000/svg">
              <path d="M16 0C7.2 0 0 7.2 0 16c0 12 16 26 16 26s16-14 16-26C32 7.2 24.8 0 16 0z" fill="${color}" stroke="#ffffff" stroke-width="2"/>
              <circle cx="16" cy="16" r="6" fill="#ffffff"/>
            </svg>
          `;

          pinEl.addEventListener("click", () => setSelected(d));

          const marker = new maplibregl.Marker({ element: pinEl })
            .setLngLat([d.lng, d.lat])
            .addTo(mapInstance.current!);
          markersRef.current.push(marker);
        });

        // 4. Fit bounds locally to patient and returned pins
        if (pins.length > 0) {
          const bounds = new maplibregl.LngLatBounds();
          bounds.extend([center.lng, center.lat]);
          pins.forEach((d) => bounds.extend([d.lng, d.lat]));
          mapInstance.current.fitBounds(bounds, { padding: 48, maxZoom: 14 });
        }
      } catch (err) {
        console.error("Error initializing MapLibre map:", err);
      }
    },
    []
  );

  const loadRecommendations = useCallback(
    async (lat: number, lng: number, currentLabel?: string) => {
      setLoading(true);
      setError("");
      const effectiveLabel = currentLabel || locationLabel;
      console.log(`[DENTIST_UI] lat=${lat} lng=${lng} issue=${issue} location=${effectiveLabel}`);
      try {
        const data = await fetchDentistRecommendations({
          issue,
          lat,
          lng,
          severity,
          scan_id: scanId,
          location_label: effectiveLabel || undefined,
        });
        console.log(`[DENTIST_UI] response received count=${data.dentists?.length ?? 0} radius=${data.search_radius_km ?? 10}km`);
        setDentists(data.dentists);
        setSessionId(data.session_id);
        const rad = data.search_radius_km || 10.0;
        setSearchRadiusKm(rad);
        setPatientCoords({ lat: data.patient_lat, lng: data.patient_lng });
        renderMap({ lat: data.patient_lat, lng: data.patient_lng }, data.dentists, rad);
      } catch (err) {
        console.error("Error loading recommendations:", err);
        const msg = err instanceof Error ? err.message : "";
        if (msg.includes("Location access was denied") || msg.includes("denied")) {
          setError(t("dentists.location_denied"));
        } else {
          setError(t("dentists.no_results"));
        }
      } finally {
        setLoading(false);
      }
    },
    [issue, scanId, severity, renderMap, t, locationLabel]
  );

  useEffect(() => {
    if (!hasCoords || urlLat === undefined || urlLng === undefined) return;
    loadRecommendations(urlLat, urlLng, locationLabel);
  }, [hasCoords, urlLat, urlLng, locationLabel, loadRecommendations]);

  function handleLocationConfirm(loc: PickedLocation) {
    setLocationModalOpen(false);
    setPickedLocation(loc);
    setPatientCoords({ lat: loc.lat, lng: loc.lng });
    const params = new URLSearchParams(searchParams.toString());
    params.set("lat", String(loc.lat));
    params.set("lng", String(loc.lng));
    params.set("location", loc.label);
    router.replace(`/patient/dentists?${params.toString()}`);
    loadRecommendations(loc.lat, loc.lng, loc.label);
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
      setBookMsg(err instanceof Error ? err.message : t("common.error"));
    } finally {
      setBooking(false);
    }
  }

  function getDirectionsUrl(d: DentistPin): string {
    if (patientCoords) {
      return `https://www.openstreetmap.org/directions?engine=fossgis_osrm_car&route=${patientCoords.lat}%2C${patientCoords.lng}%3B${d.lat}%2C${d.lng}`;
    }
    return `https://www.openstreetmap.org/?mlat=${d.lat}&mlon=${d.lng}#map=16/${d.lat}/${d.lng}`;
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
          <h1 className={styles.title}>{t("dentists.title")}</h1>
          <p className={styles.sub}>
            {issue.replace(/_/g, " ")}
            {(pickedLocation?.label || locationLabel) && (
              <>
                {" "}
                · <strong>{pickedLocation?.label || locationLabel}</strong>
              </>
            )}
          </p>
          {hasCoords && (
            <button
              type="button"
              className={styles.changeLocation}
              onClick={() => setLocationModalOpen(true)}
            >
              📍 {t("dentists.change_location")}
            </button>
          )}
          <div className={styles.legend}>
            <span className={styles.legendItem}>
              <span className={styles.legendDotBest} /> {t("dentists.best_specialist_match")}
            </span>
            <span className={styles.legendItem}>
              <span style={{ display: "inline-block", width: 10, height: 10, borderRadius: "50%", background: "#3b82f6", marginRight: 6 }} /> {t("dentists.verified_clinic")}
            </span>
            <span className={styles.legendItem}>
              <span className={styles.legendDotOther} /> {t("dentists.external_clinic")}
            </span>
          </div>
          {searchRadiusKm && dentists.length > 0 && (
            <div style={{ marginTop: "0.75rem", fontSize: "0.88rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "0.4rem", fontWeight: 600 }}>
              <span>🎯</span>
              <span>
                {locale.startsWith("ur")
                  ? `${dentists.length} ڈینٹل کلینکس ${searchRadiusKm} کلومیٹر کے دائرے میں ملے`
                  : `${dentists.length} dental clinics found within ${searchRadiusKm} km`}
              </span>
            </div>
          )}
        </div>

        {loading && (
          <div className={styles.loadingContainer}>
            <div className={styles.spinner} />
            <p className={styles.loading}>{t("dentists.searching_nearby")}</p>
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
              {t("common.retry")}
            </button>
          </div>
        )}

        {!loading && !error && hasCoords && dentists.length === 0 && (
          <div className={styles.emptyContainer}>
            <p className={styles.empty}>
              {t("dentists.no_results")}
            </p>
          </div>
        )}

        {!loading && !error && hasCoords && dentists.length > 0 && (
          <div className={styles.sidebar}>
            <div className={styles.mapWrap}>
              <div ref={mapContainerRef} className={styles.mapCanvas} style={{ width: "100%", height: "100%", minHeight: "380px" }} />
            </div>

            <div className={styles.list}>
              {dentists.map((d) => (
                <button
                  key={`${d.tier}-${d.dentist_id ?? d.place_id}-${d.rank}`}
                  type="button"
                  className={`${styles.listItem} ${d.is_best ? styles.listItemBest : ""} ${
                    selected?.rank === d.rank ? styles.listItemActive : ""
                  }`}
                  onClick={() => {
                    setSelected(d);
                    if (mapInstance.current) {
                      mapInstance.current.flyTo({ center: [d.lng, d.lat], zoom: 14, essential: true });
                    }
                  }}
                >
                  {d.is_best && <span className={styles.badgeBest}>{t("dentists.best_specialist_match")}</span>}
                  {d.tier === "platform" && (
                    <span className={styles.badgePartner}>
                      {d.is_partner ? t("dentists.verified_clinic") : t("dentists.verified_clinic")}
                    </span>
                  )}
                  {d.tier !== "platform" && (
                    <span style={{ fontSize: "0.72rem", padding: "2px 7px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-default)", color: "var(--text-secondary)", borderRadius: 4, marginLeft: 4, fontWeight: 500 }}>
                      {t("dentists.external_clinic")}
                    </span>
                  )}
                  <div className={styles.listName}>{d.name}</div>
                  <div className={styles.listMeta}>
                    {d.clinic_name || d.address} · {t("dentists.distance_km", { km: d.distance_km.toFixed(1) })}
                    {d.rating != null ? ` · ★ ${d.rating}${d.review_count ? ` (${d.review_count})` : ""}` : ""}
                  </div>
                </button>
              ))}
            </div>
          </div>
        )}

        {selected && (
          <div className={styles.modalOverlay} onClick={() => setSelected(null)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              {selected.is_best && <span className={styles.badgeBest}>{t("dentists.best_specialist_match")}</span>}
              {selected.tier === "platform" ? (
                <span className={styles.badgePartner} style={{ marginLeft: 6 }}>{t("dentists.verified_clinic")}</span>
              ) : (
                <span style={{ fontSize: "0.75rem", padding: "3px 8px", background: "rgba(100,116,139,0.25)", color: "#cbd5e1", borderRadius: 4, marginLeft: 6 }}>
                  {t("dentists.external_clinic")}
                </span>
              )}

              <h3 style={{ marginTop: "0.75rem" }}>{selected.name}</h3>
              <p className={styles.modalClinic}>{selected.clinic_name || selected.address}</p>
              <p className={styles.modalReason}>{selected.recommendation_reason}</p>
              
              <p className={styles.modalRow}>
                📍 <strong>{t("dentists.distance_km", { km: selected.distance_km.toFixed(1) })}</strong>
                {selected.rating != null ? ` · ★ ${selected.rating}${selected.review_count ? ` (${selected.review_count})` : ""}` : ""}
              </p>
              {selected.address && <p className={styles.modalRow}>{selected.address}</p>}
              {selected.phone && <p className={styles.modalRow}>📞 {selected.phone}</p>}
              {selected.website && (
                <p className={styles.modalRow}>
                  🌐 <a href={selected.website} target="_blank" rel="noreferrer" style={{ color: "#38bdf8" }}>{selected.website}</a>
                </p>
              )}

              <div className={styles.modalActions} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", marginTop: "1rem" }}>
                {selected.phone && (
                  <a href={`tel:${selected.phone}`} className={styles.btnPrimary} style={{ textDecoration: "none", textAlign: "center", flex: "1 1 auto" }}>
                    📞 {t("dentists.call")}
                  </a>
                )}
                
                <a
                  href={getDirectionsUrl(selected)}
                  target="_blank"
                  rel="noreferrer"
                  className={styles.btnPrimary}
                  style={{ textDecoration: "none", textAlign: "center", background: "#334155", color: "#fff", flex: "1 1 auto" }}
                >
                  🗺️ {t("dentists.directions")}
                </a>

                {selected.tier === "platform" && selected.dentist_id ? (
                  <button
                    type="button"
                    className={styles.btnPrimary}
                    style={{ background: "#059669", flex: "1 1 100%" }}
                    disabled={booking}
                    onClick={handleBook}
                  >
                    {booking ? t("common.loading") : `📅 ${t("dentists.book_consultation")}`}
                  </button>
                ) : (
                  <p style={{ fontSize: "0.8rem", color: "var(--text-muted)", width: "100%", textAlign: "center", marginTop: "0.25rem" }}>
                    ℹ️ {t("dentists.external_clinic")}
                  </p>
                )}
              </div>

              {bookMsg && <p className={styles.bookMessage}>{bookMsg}</p>}
              
              <button type="button" className={styles.btnClose} onClick={() => setSelected(null)}>
                {t("common.close")}
              </button>
            </div>
          </div>
        )}
      </div>
    </PortalDashboard>
  );
}

