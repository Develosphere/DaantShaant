import type { PipelineResult } from "./types";
import { getUserId, getWsUrl } from "./api";

export type LiveCallbacks = {
  onReady?: (sessionId: string) => void;
  onProgress?: (step: string, seq?: number) => void;
  onHint?: (message: string) => void;
  onPartial?: (result: PipelineResult) => void;
  onFinal?: (result: PipelineResult) => void;
  onError?: (message: string) => void;
  onStatus?: (status: string) => void;
};

export class LiveSessionClient {
  private ws: WebSocket | null = null;
  private seq = 0;
  private intervalId: ReturnType<typeof setInterval> | null = null;
  private captureFrame: (() => string | null) | null = null;

  connect(callbacks: LiveCallbacks): Promise<void> {
    return new Promise((resolve, reject) => {
      this.ws = new WebSocket(getWsUrl());

      this.ws.onopen = () => {
        callbacks.onStatus?.("Connected");
        this.ws?.send(
          JSON.stringify({
            type: "session.start",
            user_id: getUserId(),
            locale: "en",
          })
        );
      };

      this.ws.onmessage = (ev) => {
        const msg = JSON.parse(ev.data as string);
        switch (msg.type) {
          case "session.ready":
            callbacks.onReady?.(msg.session_id);
            callbacks.onStatus?.("Live analysis running…");
            resolve();
            break;
          case "analysis.progress":
            callbacks.onProgress?.(msg.step, msg.seq);
            break;
          case "quality.hint":
            callbacks.onHint?.(msg.message);
            break;
          case "analysis.partial":
            callbacks.onPartial?.({
              analysis: msg.analysis,
              diagnosis: msg.diagnosis,
            });
            break;
          case "analysis.final":
            if (msg.analysis && msg.diagnosis) {
              callbacks.onFinal?.({
                analysis: msg.analysis,
                diagnosis: msg.diagnosis,
              });
            }
            callbacks.onStatus?.("Session complete");
            this.stopSendingFrames();
            break;
          case "error":
            callbacks.onError?.(msg.message ?? msg.code);
            break;
        }
      };

      this.ws.onerror = () => {
        callbacks.onError?.("WebSocket connection failed");
        reject(new Error("WebSocket error"));
      };

      this.ws.onclose = () => {
        callbacks.onStatus?.("Disconnected");
        this.stopSendingFrames();
      };
    });
  }

  startSendingFrames(capture: () => string | null, fps = 1) {
    this.captureFrame = capture;
    this.stopSendingFrames();
    const ms = 1000 / fps;
    this.intervalId = setInterval(() => {
      if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return;
      const b64 = capture();
      if (!b64) return;
      this.seq += 1;
      this.ws.send(
        JSON.stringify({
          type: "frame",
          seq: this.seq,
          image_base64: b64,
        })
      );
    }, ms);
  }

  stopSendingFrames() {
    if (this.intervalId) {
      clearInterval(this.intervalId);
      this.intervalId = null;
    }
  }

  endSession() {
    this.stopSendingFrames();
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify({ type: "session.end" }));
    }
  }

  disconnect() {
    this.endSession();
    this.ws?.close();
    this.ws = null;
  }
}
