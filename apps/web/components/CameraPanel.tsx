"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { analyzeSnapshot, getUserId } from "@/lib/api";
import { fileToImagePayload, type ImagePayload } from "@/lib/image";
import { LiveSessionClient } from "@/lib/ws-live";
import type { PipelineResult } from "@/lib/types";
import { DiagnosisReport } from "./DiagnosisReport";

type Mode = "snapshot" | "live" | "upload";

export function CameraPanel() {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const liveClientRef = useRef<LiveSessionClient | null>(null);

  const [mode, setMode] = useState<Mode>("snapshot");
  const [cameraOn, setCameraOn] = useState(false);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [hint, setHint] = useState("");
  const [report, setReport] = useState<PipelineResult | null>(null);
  const [liveActive, setLiveActive] = useState(false);
  const [upload, setUpload] = useState<ImagePayload | null>(null);
  const [dragOver, setDragOver] = useState(false);

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
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (videoRef.current) videoRef.current.srcObject = null;
    setCameraOn(false);
  }, []);

  const switchMode = (next: Mode) => {
    if (liveActive) return;
    if (next === "upload") stopCamera();
    setMode(next);
    setHint("");
    if (next !== "upload") {
      setUpload(null);
      setStatus(next === "snapshot" ? "" : "");
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
      streamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  const runAnalysis = async (base64: string, mimeType: string, statusMsg: string) => {
    setLoading(true);
    setHint("");
    setStatus(statusMsg);
    try {
      const result = await analyzeSnapshot(base64, getUserId(), mimeType);
      setReport(result);
      setStatus("Analysis complete");
    } catch (e) {
      setStatus("Analysis failed");
      setHint(e instanceof Error ? e.message : "Unknown error");
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
    await runAnalysis(b64, "image/jpeg", "Analyzing snapshot…");
  };

  const handleUploadSelect = async (file: File) => {
    try {
      const payload = await fileToImagePayload(file);
      setUpload(payload);
      setHint("");
      setStatus(`Ready: ${payload.fileName}`);
    } catch (e) {
      setHint(e instanceof Error ? e.message : "Invalid file");
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
      setHint("Choose a teeth photo first.");
      return;
    }
    await runAnalysis(upload.base64, upload.mimeType, "Analyzing uploaded image…");
  };

  const clearUpload = () => {
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
          setStatus("Updating diagnosis…");
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
          <h2 className="panel-title">Oral scan</h2>
          <div className="mode-switch mode-switch--three" role="tablist">
            <button
              type="button"
              role="tab"
              aria-selected={mode === "snapshot"}
              className={mode === "snapshot" ? "active" : ""}
              onClick={() => switchMode("snapshot")}
              disabled={liveActive}
            >
              Snapshot
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "live"}
              className={mode === "live" ? "active" : ""}
              onClick={() => switchMode("live")}
              disabled={liveActive}
            >
              Live
            </button>
            <button
              type="button"
              role="tab"
              aria-selected={mode === "upload"}
              className={mode === "upload" ? "active" : ""}
              onClick={() => switchMode("upload")}
              disabled={liveActive}
            >
              Upload
            </button>
          </div>
        </div>

        {mode === "upload" ? (
          <div
            className={`upload-zone ${upload ? "upload-zone--filled" : ""} ${dragOver ? "upload-zone--drag" : ""} ${loading ? "upload-zone--busy" : ""}`}
            onDragOver={(e) => {
              e.preventDefault();
              setDragOver(true);
            }}
            onDragLeave={() => setDragOver(false)}
            onDrop={handleDrop}
            onClick={() => !upload && fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept="image/jpeg,image/png,image/webp"
              hidden
              onChange={handleFileInput}
            />
            {upload ? (
              <>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={upload.previewUrl} alt="Uploaded teeth" className="upload-preview" />
                <div className="upload-meta">
                  <span className="upload-name">{upload.fileName}</span>
                  <button
                    type="button"
                    className="upload-change"
                    onClick={(e) => {
                      e.stopPropagation();
                      fileInputRef.current?.click();
                    }}
                  >
                    Change image
                  </button>
                </div>
              </>
            ) : (
              <div className="upload-empty">
                <div className="upload-icon">↑</div>
                <p className="upload-title">Drop a teeth photo here</p>
                <span className="upload-sub">or click to browse · JPEG, PNG, WebP</span>
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
                <p>Camera off</p>
                <span>Enable camera to begin scanning</span>
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

        <div className="control-row">
          {mode === "upload" ? (
            <>
              {upload && (
                <button type="button" className="btn btn-ghost" onClick={clearUpload}>
                  Clear
                </button>
              )}
              <button
                type="button"
                className="btn btn-glow"
                onClick={handleAnalyzeUpload}
                disabled={loading || !upload}
              >
                {loading ? "Analyzing…" : "Analyze upload"}
              </button>
              {!upload && (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => fileInputRef.current?.click()}
                >
                  Choose file
                </button>
              )}
            </>
          ) : (
            <>
              {!cameraOn ? (
                <button type="button" className="btn btn-glow" onClick={startCamera}>
                  Start camera
                </button>
              ) : (
                <button type="button" className="btn btn-ghost" onClick={stopCamera}>
                  Stop camera
                </button>
              )}

              {mode === "snapshot" && cameraOn && (
                <button
                  type="button"
                  className="btn btn-glow"
                  onClick={handleTakePhoto}
                  disabled={loading}
                >
                  {loading ? "Analyzing…" : "Capture & analyze"}
                </button>
              )}

              {mode === "live" && cameraOn && !liveActive && (
                <button
                  type="button"
                  className="btn btn-glow"
                  onClick={handleStartLive}
                  disabled={loading}
                >
                  Start live analysis
                </button>
              )}

              {liveActive && (
                <button type="button" className="btn btn-stop" onClick={handleStopLive}>
                  Stop & get report
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
            {hint && <p className="hint-text">{hint}</p>}
          </div>
        )}
      </section>

      <DiagnosisReport
        result={report}
        label={liveActive ? "Live diagnosis" : "AI diagnosis report"}
        loading={loading && !report}
        liveActive={liveActive}
      />
    </div>
  );
}
