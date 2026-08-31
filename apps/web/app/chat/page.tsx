import { Header } from "@/components/Header";
import { ChatInterface } from "@/components/ChatInterface";

export default function ChatPage() {
  return (
    <div className="page-shell">
      <div className="bg-orb bg-orb-a" aria-hidden />
      <div className="bg-orb bg-orb-b" aria-hidden />
      <div className="bg-grid" aria-hidden />

      <Header />

      <main className="demo-main">
        <section className="hero-copy">
          <p className="eyebrow">Conversational AI · Persistent Memory</p>
          <h1 className="hero-title">
            Chat with
            <span className="hero-gradient"> DantShaant AI</span>
          </h1>
          <p className="hero-desc">
            Ask questions about oral health, share photos of your teeth for analysis,
            and get personalized recommendations. Your conversation history is saved.
          </p>
        </section>

        <div className="demo-grid">
          <ChatInterface />
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
