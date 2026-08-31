import { Header } from "@/components/Header";
import { CameraPanel } from "@/components/CameraPanel";

export default function ScanPage() {
  return (
    <div className="page-shell">
      <div className="bg-orb bg-orb-a" aria-hidden />
      <div className="bg-orb bg-orb-b" aria-hidden />
      <div className="bg-grid" aria-hidden />

      <Header />

      <main className="demo-main">
        <section className="hero-copy">
          <p className="eyebrow">Live prototype · Vision AI + clinical rules</p>
          <h1 className="hero-title">
            Scan your smile.
            <span className="hero-gradient"> Know your teeth.</span>
          </h1>
          <p className="hero-desc">
            Capture a photo or run live video — DantShaant analyzes teeth in seconds
            and returns a clear diagnosis report powered by Gemini vision.
          </p>
          <ul className="feature-pills">
            <li>Snapshot analysis</li>
            <li>Live WebSocket scan</li>
            <li>Upload image</li>
            <li>OpenCV quality gate</li>
          </ul>
        </section>

        <div className="demo-grid">
          <CameraPanel />
        </div>
      </main>

      <footer className="site-footer">
        <span>DantShaant © 2026</span>
        <span className="footer-dot" />
        <span>Awareness tool — not a medical diagnosis</span>
      </footer>
    </div>
  );
}
