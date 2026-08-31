"use client";

import { useState, useEffect } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { Header } from "@/components/Header";
import { CheckoutModal } from "@/components/CheckoutModal";

export default function ProductDetailPage() {
  const params = useParams();
  const router = useRouter();
  const product_id = params?.id as string;

  const [product, setProduct] = useState<any | null>(null);
  const [loading, setLoading] = useState(true);
  const [isCheckoutOpen, setIsCheckoutOpen] = useState(false);
  const [addedToCart, setAddedToCart] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!product_id) return;

    const fetchProduct = async () => {
      try {
        const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";
        const res = await fetch(`${API_BASE}/portal/products/${product_id}`);
        if (res.ok) {
          const data = await res.json();
          setProduct(data);
        } else {
          setError("Product not found");
        }
      } catch (err) {
        console.error("Error fetching product details:", err);
        setError("Failed to load product");
      } finally {
        setLoading(false);
      }
    };

    void fetchProduct();
  }, [product_id]);

  const handleAddToCart = () => {
    if (!product) return;
    try {
      const cart = JSON.parse(localStorage.getItem("dantshaant-cart") || "[]");
      if (!cart.some((item: any) => item.product_id === product.product_id)) {
        cart.push({
          product_id: product.product_id,
          name: product.name,
          price: product.price,
          images: product.images
        });
        localStorage.setItem("dantshaant-cart", JSON.stringify(cart));
        window.dispatchEvent(new Event("cart-updated"));
      }
      setAddedToCart(true);
      setTimeout(() => setAddedToCart(false), 2000);
    } catch (e) {
      console.error(e);
    }
  };

  const handleBuyNow = () => {
    setIsCheckoutOpen(true);
  };

  if (loading) {
    return (
      <div className="page-shell">
        <Header />
        <main className="demo-main" style={{ display: "flex", justifyContent: "center", alignItems: "center", minHeight: "50vh" }}>
          <div className="loader-ring">
            <div className="loader-ring-inner" />
          </div>
        </main>
      </div>
    );
  }

  if (error || !product) {
    return (
      <div className="page-shell">
        <Header />
        <main className="demo-main" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "50vh", gap: "1rem" }}>
          <div style={{ fontSize: "3rem" }}>🦷</div>
          <h2 style={{ color: "#fff", fontWeight: 700 }}>{error || "Product Not Found"}</h2>
          <p className="text-muted">The product you are trying to view does not exist or has been removed.</p>
          <Link href="/" className="btn btn-secondary" style={{ textDecoration: "none" }}>
            Return to Analyzer
          </Link>
        </main>
      </div>
    );
  }

  const imageSrc = product.images && product.images.length > 0 ? product.images[0] : "";

  return (
    <div className="page-shell">
      <div className="bg-orb bg-orb-a" aria-hidden />
      <div className="bg-orb bg-orb-b" aria-hidden />
      <div className="bg-grid" aria-hidden />

      <Header />

      <main className="demo-main" style={{ maxWidth: "800px", margin: "2rem auto", padding: "0 1rem" }}>
        <div style={{ marginBottom: "1rem" }}>
          <Link href="/" className="text-link" style={{ fontSize: "0.85rem", textDecoration: "none", color: "var(--accent)", display: "inline-flex", alignItems: "center", gap: "0.4rem" }}>
            ← Back to Home
          </Link>
        </div>

        <div className="rec-product-card" style={{ padding: "2rem", flexDirection: "column", gap: "2rem", cursor: "default" }}>
          <div style={{ display: "grid", gridTemplateColumns: "1fr", gap: "2rem" }} className="md-grid-2">
            
            {/* Left Column: Image */}
            <div style={{ 
              background: "rgba(255, 255, 255, 0.02)", 
              border: "1px solid rgba(255, 255, 255, 0.08)", 
              borderRadius: "var(--radius-md)", 
              overflow: "hidden", 
              aspectRatio: "1/1", 
              display: "flex", 
              alignItems: "center", 
              justifyContent: "center",
              position: "relative"
            }}>
              {imageSrc ? (
                <img src={imageSrc} alt={product.name} style={{ width: "100%", height: "100%", objectFit: "cover" }} />
              ) : (
                <div style={{ fontSize: "4rem" }}>🦷</div>
              )}
              <span className="chip" style={{ position: "absolute", top: "1rem", left: "1rem", textTransform: "capitalize", background: "rgba(0,0,0,0.6)" }}>
                {product.category}
              </span>
            </div>

            {/* Right Column: Details */}
            <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
              <div>
                <h1 style={{ fontSize: "1.8rem", fontWeight: 800, color: "#fff", margin: 0, fontFamily: "var(--font-syne)" }}>
                  {product.name}
                </h1>
                <div style={{ display: "flex", alignItems: "center", gap: "1rem", marginTop: "0.5rem" }}>
                  <span style={{ fontSize: "1.5rem", fontWeight: 800, color: "var(--accent)" }}>
                    ${product.price.toFixed(2)}
                  </span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                    {product.view_count} views · {product.recommendation_count} recommendations
                  </span>
                </div>
              </div>

              <div style={{ borderTop: "1px solid rgba(255, 255, 255, 0.08)", paddingTop: "1rem" }}>
                <h3 style={{ fontSize: "0.85rem", textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: "0.05em", marginBottom: "0.5rem" }}>
                  AI Clinical Description
                </h3>
                <p style={{ fontSize: "0.9rem", color: "var(--text)", lineHeight: 1.6, margin: 0 }}>
                  {product.ai_description}
                </p>
              </div>

              {product.problems_solved && product.problems_solved.length > 0 && (
                <div>
                  <h3 style={{ fontSize: "0.85rem", textTransform: "uppercase", color: "var(--text-muted)", letterSpacing: "0.05em", marginBottom: "0.5rem" }}>
                    Clinical Benefits
                  </h3>
                  <div className="rec-product-tags">
                    {product.problems_solved.map((p: string, idx: number) => (
                      <span key={idx} className="rec-product-tag" style={{ fontSize: "0.75rem", padding: "0.25rem 0.6rem" }}>
                        {p}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Action Buttons */}
              <div style={{ display: "flex", gap: "1rem", marginTop: "1.5rem", flexWrap: "wrap" }}>
                <button 
                  className={`btn ${addedToCart ? "btn-secondary" : "btn-buy"}`} 
                  onClick={handleAddToCart}
                  style={{ 
                    flex: 1, 
                    alignSelf: "stretch", 
                    margin: 0, 
                    background: addedToCart ? "rgba(16, 185, 129, 0.15)" : undefined,
                    borderColor: addedToCart ? "rgba(16, 185, 129, 0.3)" : undefined,
                    color: addedToCart ? "#10b981" : undefined
                  }}
                >
                  {addedToCart ? "✓ Added to Cart" : "Add to Cart"}
                </button>
                <button 
                  className="btn btn-buy" 
                  onClick={handleBuyNow}
                  style={{ flex: 1, alignSelf: "stretch", margin: 0, background: "linear-gradient(135deg, #00f2fe 0%, #4facfe 100%)", color: "#000" }}
                >
                  Buy Now
                </button>
              </div>
            </div>

          </div>
        </div>
      </main>

      <CheckoutModal
        product={product}
        isOpen={isCheckoutOpen}
        onClose={() => setIsCheckoutOpen(false)}
      />

      <footer className="site-footer">
        <span>DantShaant © 2026</span>
        <span className="footer-dot" />
        <span>Awareness tool — not a medical diagnosis</span>
      </footer>
    </div>
  );
}
