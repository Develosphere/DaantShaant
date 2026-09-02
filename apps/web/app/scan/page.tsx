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
            Capture a photo or run live video — DaantShaant screens your smile in seconds
            and provides an AI-assisted screening report and specialist recommendations.
          </p>
          <ul className="feature-pills">
            <li>Oral snapshot</li>
            <li>Live camera scan</li>
            <li>Upload image</li>
            <li>Dentist navigation</li>
          </ul>
        </section>

        <div className="demo-grid">
          <CameraPanel />
        </div>
      </main>

      <footer className="site-footer">
        <span>DaantShaant © 2026</span>
        <span className="footer-dot" />
        <span>AI-assisted screening tool — not a medical diagnosis</span>
      </footer>
    </div>
  );
}
