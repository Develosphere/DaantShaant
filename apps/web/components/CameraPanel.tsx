"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useLanguage } from "@/i18n";
import { analyzeSnapshot } from "@/lib/api";
import { fileToImagePayload, type ImagePayload } from "@/lib/image";
import { LiveSessionClient } from "@/lib/ws-live";
import type { PipelineResult } from "@/lib/types";
import { DiagnosisReport } from "./DiagnosisReport";

type Mode = "snapshot" | "live" | "upload";

const PROGRESS_STAGES_DEF = [
  { key: "stage_prep", thresholdSec: 0 },
  { key: "stage_relevance", thresholdSec: 3 },
  { key: "stage_findings", thresholdSec: 9 },
  { key: "stage_urgency", thresholdSec: 20 },
  { key: "stage_report", thresholdSec: 32 },
];

export function CameraPanel() {
  const { t } = useLanguage();
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const liveClientRef = useRef<LiveSessionClient | null>(null);

  const [mode, setMode] = useState<Mode>("snapshot");
  const [cameraOn, setCameraOn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [elapsedSec, setElapsedSec] = useState(0);
  const [currentStageIdx, setCurrentStageIdx] = useState(0);
  const [status, setStatus] = useState("");
  const [hint, setHint] = useState("");
  const [report, setReport] = useState<PipelineResult | null>(null);
  const [liveActive, setLiveActive] = useState(false);
  const [upload, setUpload] = useState<ImagePayload | null>(null);
  const [dragOver, setDragOver] = useState(false);

  // Timer effect for long analysis UX
  useEffect(() => {
    let timer: NodeJS.Timeout | null = null;
    if (loading) {
      setElapsedSec(0);
      setCurrentStageIdx(0);
      timer = setInterval(() => {
        setElapsedSec((prev) => {
          const next = prev + 1;
          for (let i = PROGRESS_STAGES_DEF.length - 1; i >= 0; i--) {
            if (next >= PROGRESS_STAGES_DEF[i].thresholdSec) {
              setCurrentStageIdx(i);
              break;
            }
          }
          return next;
        });
      }, 1000);
    } else {
      setElapsedSec(0);
      setCurrentStageIdx(0);
    }
    return () => {
      if (timer) clearInterval(timer);
    };
  }, [loading]);

  const captureBase64 = useCallback((): string | null => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2) return null;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (!w || !h) return null;
    canvas.width = w;
    canvas.height = h;
    const ctx = canvas.getContext("2d");
    if (!ctx) return null;
    ctx.drawImage(video, 0, 0, w, h);
    return canvas.toDataURL("image/jpeg", 0.75).split(",")[1] ?? null;
  }, []);

  const stopCamera = useCallback(() => {
    liveClientRef.current?.disconnect();
    liveClientRef.current = null;
    setLiveActive(false);
    streamRef.current?.getTracks().forEach((tTrack) => tTrack.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  }, []);

  const switchMode = (next: Mode) => {
    if (liveActive || loading) return;
    if (next === "upload") stopCamera();
    setMode(next);
    setHint("");
    if (next !== "upload") {
      setUpload(null);
      setStatus("");
    } else {
      setStatus("");
    }
  };

  const startCamera = async () => {
    setHint("");
    setStatus("Initializing camera…");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
        audio: false,
      });
      streamRef.current = stream;
      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play();
      }
      setCameraOn(true);
      setStatus("Camera active — align teeth in the guide");
    } catch {
      setStatus("Camera permission denied");
    }
  };

  useEffect(() => {
    return () => {
      liveClientRef.current?.disconnect();
      streamRef.current?.getTracks().forEach((tTrack) => tTrack.stop());
    };
  }, []);

  const runAnalysis = async (base64: string, mimeType: string, statusMsg: string) => {
    if (loading) return;
    setLoading(true);
    setHint("");
    setReport(null);
    setStatus(statusMsg);
    try {
      const result = await analyzeSnapshot(base64, mimeType);
      setReport(result);
      setStatus("Analysis complete");
    } catch (e) {
      setStatus("Screening note");
      setHint(e instanceof Error ? e.message : "We couldn't complete the screening. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  const handleTakePhoto = async () => {
    const b64 = captureBase64();
    if (!b64) {
      setHint("Wait for the camera to load, then try again.");
      return;
    }
    await runAnalysis(b64, "image/jpeg", "Analyzing oral snapshot…");
  };

  const handleUploadSelect = async (file: File) => {
    try {
      const payload = await fileToImagePayload(file);
      setUpload(payload);
      setHint("");
      setStatus(`Ready: ${payload.fileName}`);
    } catch (e) {
      setHint(e instanceof Error ? e.message : "Invalid image file");
    }
  };

  const handleFileInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleUploadSelect(file);
    e.target.value = "";
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file) void handleUploadSelect(file);
  };

  const handleAnalyzeUpload = async () => {
    if (!upload) {
      setHint("Choose a dental photo first.");
      return;
    }
    await runAnalysis(upload.base64, upload.mimeType, "Analyzing uploaded dental image…");
  };

  const handleLoadSample = async () => {
    try {
      setStatus("Loading sample dental image…");
      const res = await fetch("/landing/hero-teeth-white.png");
      const blob = await res.blob();
      const file = new File([blob], "sample-dental-scan.png", { type: "image/png" });
      const payload = await fileToImagePayload(file);
      setUpload(payload);
      setMode("upload");
      setStatus("Sample image loaded — click Analyze upload");
      setHint("");
    } catch {
      setHint("Could not load sample image. Please upload a photo.");
    }
  };

  const clearUpload = () => {
    if (loading) return;
    setUpload(null);
    setStatus("");
    setHint("");
  };

  const handleStartLive = async () => {
    if (!captureBase64()) {
      setHint("Start the camera first.");
      return;
    }
    setLoading(true);
    setHint("");
    setReport(null);
    setStatus("Connecting live session…");

    const client = new LiveSessionClient();
    liveClientRef.current = client;

    try {
      await client.connect({
        onReady: () => {
          client.startSendingFrames(() => captureBase64(), 1);
          setLiveActive(true);
          setLoading(false);
          setStatus("Live scan running");
        },
        onProgress: (step) => setStatus(`Processing: ${step}…`),
        onHint: (msg) => setHint(msg),
        onPartial: (result) => {
          setReport(result);
          setStatus("Updating screening report…");
        },
        onFinal: (result) => {
          setReport(result);
          setLiveActive(false);
          setLoading(false);
          setStatus("Session complete");
        },
        onError: (msg) => {
          setHint(msg);
          setLoading(false);
          setLiveActive(false);
        },
        onStatus: (s) => setStatus(s),
      });
    } catch {
      setLoading(false);
      setStatus("Could not connect to backend");
    }
  };

  const handleStopLive = () => {
    liveClientRef.current?.endSession();
    setLiveActive(false);
    setStatus("Finalizing report…");
  };

  return (
    <div className="demo-grid-inner">
      <section className="scan-panel glass">
        <div className="panel-top">
          <h2 className="panel-title">{t("nav.scan")}</h2>
          <div className="mode-switch mode-switch--three" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "snapshot"}
              className={mode === "snapshot" ? "active" : ""}
              onClick={() => switchMode("snapshot")}
              disabled={liveActive || loading}
            >
              {t("scan.tab_snapshot")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "live"}
              className={mode === "live" ? "active" : ""}
              onClick={() => switchMode("live")}
              disabled={liveActive || loading}
            >
              {t("scan.tab_live")}
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "upload"}
              className={mode === "upload" ? "active" : ""}
              onClick={() => switchMode("upload")}
              disabled={liveActive || loading}
            >
              {t("scan.tab_upload")}
            </button>
          </div>
        </div>

        {mode === "upload" ? (
          <div
            className={`upload-zone ${upload ? "upload-zone--filled" : ""} ${dragOver ? "upload-zone--drag" : ""} ${loading ? "upload-zone--busy" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              if (!loading) setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !upload && !loading && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              hidden
              disabled={loading}
              onChange={handleFileInput}
            />
            {upload ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={upload.previewUrl} alt="Uploaded teeth" className="upload-preview" />
                <div className="upload-meta">
                  <span className="upload-name">{upload.fileName}</span>
                  {!loading && (
                    <button
                      type="button"
                      className="upload-change"
                      onClick={(e) => {
                        e.stopPropagation();
                        fileInputRef.current?.click();
                      }}
                    >
                      {t("scan.change_image")}
                    </button>
                  )}
                </div>
              </>
            ) : (
              <div className="upload-empty">
                <div className="upload-icon">↑</div>
                <p className="upload-title">{t("scan.drop_title")}</p>
                <span className="upload-sub">{t("scan.drop_subtitle")}</span>
                <button
                  type="button"
                  className="btn btn-ghost btn-sm"
                  style={{ marginTop: "0.85rem", fontSize: "0.8rem" }}
                  onClick={(e) => {
                    e.stopPropagation();
                    void handleLoadSample();
                  }}
                >
                  ⚡ {t("scan.try_sample")}
                </button>
              </div>
            )}
          </div>
        ) : (
          <div
            className={`viewport ${cameraOn ? "viewport--on" : ""} ${liveActive ? "viewport--live" : ""} ${loading ? "viewport--busy" : ""}`}
          >
            <video ref={videoRef} playsInline muted />
            {!cameraOn && (
              <div className="viewport-placeholder">
                <div className="placeholder-icon">📷</div>
                <p>{t("scan.camera_off")}</p>
                <span>{t("scan.enable_camera")}</span>
              </div>
            )}
            {cameraOn && (
              <div className="viewport-overlay">
                <div className="scan-corners" />
                <div className="mouth-guide" />
                {liveActive && <div className="scan-line" />}
                {liveActive && (
                  <span className="viewport-live-badge">
                    <span className="live-dot" /> LIVE
                  </span>
                )}
              </div>
            )}
          </div>
        )}
        <canvas ref={canvasRef} hidden />

        {/* Long analysis reassurance & stage indicators */}
        {loading && (
          <div className="scan-progress-box" style={{ marginTop: "1rem", padding: "1rem", borderRadius: "12px", background: "var(--bg-surface-raised)", border: "1px solid var(--border-default)" }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.5rem" }}>
              <span style={{ fontSize: "0.82rem", fontWeight: 700, color: "var(--accent)" }}>
                {t("scan.screening_in_progress")}
              </span>
              <span style={{ fontSize: "0.75rem", padding: "2px 8px", borderRadius: "999px", background: "rgba(2, 132, 199, 0.15)", color: "var(--accent)", fontFamily: "monospace" }}>
                ⏱️ {elapsedSec}s
              </span>
            </div>

            <div className="progress-steps" style={{ display: "flex", flexDirection: "column", gap: "0.35rem", margin: "0.6rem 0" }}>
              {PROGRESS_STAGES_DEF.map((s, idx) => {
                const isCurrent = idx === currentStageIdx;
                const isDone = idx < currentStageIdx;
                return (
                  <div
                    key={s.key}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      fontSize: "0.78rem",
                      color: isCurrent ? "var(--accent)" : isDone ? "#22c55e" : "var(--text-dim)",
                      fontWeight: isCurrent ? 600 : 400,
                    }}
                  >
                    <span>{isDone ? "✓" : isCurrent ? "⏳" : "○"}</span>
                    <span>{t(`scan.${s.key}`)}</span>
                  </div>
                );
              })}
            </div>

            {elapsedSec >= 15 && elapsedSec < 35 && (
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0.4rem 0 0", fontStyle: "italic" }}>
                ℹ️ {t("scan.reassurance_15s")}
              </p>
            )}
            {elapsedSec >= 35 && (
              <p style={{ fontSize: "0.75rem", color: "var(--text-muted)", margin: "0.4rem 0 0", fontStyle: "italic" }}>
                ℹ️ {t("scan.reassurance_35s")}
              </p>
            )}
          </div>
        )}

        <div className="control-row">
          {mode === "upload" ? (
            <>
              {upload && (
                <button type="button" className="btn btn-ghost" onClick={clearUpload} disabled={loading}>
                  {t("scan.clear")}
                </button>
              )}
              <button
                type="button"
                className="btn btn-glow"
                onClick={handleAnalyzeUpload}
                disabled={loading || !upload}
              >
                {loading ? `${t("scan.analyzing")} (${elapsedSec}s)…` : t("scan.analyze_upload")}
              </button>
              {!upload && (
                <>
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => fileInputRef.current?.click()}
                    disabled={loading}
                  >
                    {t("scan.choose_file")}
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={handleLoadSample}
                    disabled={loading}
                  >
                    {t("scan.sample_scan")}
                  </button>
                </>
              )}
            </>
          ) : (
            <>
              {!cameraOn ? (
                <button type="button" className="btn btn-glow" onClick={startCamera}>
                  {t("scan.start_camera")}
                </button>
              ) : (
                <button type="button" className="btn btn-ghost" onClick={stopCamera}>
                  {t("scan.stop_camera")}
                </button>
              )}

              {mode === "snapshot" && cameraOn && (
                <button
                  type="button"
                  className="btn btn-glow"
                  onClick={handleTakePhoto}
                  disabled={loading}
                >
                  {loading ? `${t("scan.analyzing")} (${elapsedSec}s)…` : t("scan.take_photo")}
                </button>
              )}

              {mode === "live" && cameraOn && !liveActive && (
                <button
                  type="button"
                  className="btn btn-glow"
                  onClick={handleStartLive}
                  disabled={loading}
                >
                  {t("scan.start_live")}
                </button>
              )}

              {liveActive && (
                <button type="button" className="btn btn-stop" onClick={handleStopLive}>
                  {t("scan.stop_live")}
                </button>
              )}
            </>
          )}
        </div>

        {(status || hint) && (
          <div className="status-bar">
            {status && (
              <p className={`status-text ${liveActive ? "status-text--live" : ""}`}>
                {liveActive && <span className="live-dot" />}
                {status}
              </p>
            )}
            {hint && <p className="hint-text">⚠️ {hint}</p>}
          </div>
        )}
      </section>

      <DiagnosisReport
        result={report}
        label={liveActive ? t("report.live_title") : t("report.title")}
        loading={loading && !report}
        liveActive={liveActive}
      />
    </div>
  );
}

