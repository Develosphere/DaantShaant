"use client";

import { useState, useEffect, useCallback } from "react";
import { Header } from "@/components/Header";

const API_BASE = process.env.NEXT_PUBLIC_ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

type Product = {
  product_id: string;
  name: string;
  category: string;
  price: number;
  ai_description: string;
  problems_solved: string[];
  images: string[];
  dentist_id: string;
  status: string;
  view_count: number;
  recommendation_count: number;
  created_at: string;
};

export default function PortalPage() {
  // Authentication State
  const [token, setToken] = useState<string | null>(null);
  const [userRole, setUserRole] = useState<string | null>(null);
  const [userName, setUserName] = useState<string | null>(null);
  const [authMode, setAuthMode] = useState<"login" | "register">("login");
  const [authLoading, setAuthLoading] = useState(false);
  const [authError, setAuthError] = useState("");

  // Form Fields
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [name, setName] = useState("");
  const [role, setRole] = useState("dentist");
  const [clinicName, setClinicName] = useState("");
  const [licenseNumber, setLicenseNumber] = useState("");

  // Dashboard Tabs & Products State
  const [activeTab, setActiveTab] = useState<"catalog" | "upload" | "edit" | "orders">("catalog");
  const [products, setProducts] = useState<Product[]>([]);
  const [loadingProducts, setLoadingProducts] = useState(false);
  const [productError, setProductError] = useState("");

  // Orders State
  const [orders, setOrders] = useState<any[]>([]);
  const [loadingOrders, setLoadingOrders] = useState(false);
  const [ordersError, setOrdersError] = useState("");

  const fetchOrders = useCallback(async () => {
    if (!token) return;
    setLoadingOrders(true);
    setOrdersError("");
    try {
      const res = await fetch(`${API_BASE}/portal/products/orders/notifications`, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        throw new Error(await res.text().catch(() => "Failed to fetch orders"));
      }
      const data = await res.json();
      setOrders(data);
    } catch (e) {
      setOrdersError(e instanceof Error ? e.message : "Error loading orders");
    } finally {
      setLoadingOrders(false);
    }
  }, [token]);

  const handleUpdateOrderStatus = async (orderId: string, newStatus: string) => {
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/portal/products/orders/${orderId}/status`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`
        },
        body: JSON.stringify({ status: newStatus })
      });
      if (res.ok) {
        void fetchOrders();
      }
    } catch (err) {
      console.error("Failed to update status:", err);
    }
  };

  useEffect(() => {
    if (token && activeTab === "orders") {
      void fetchOrders();
    }
  }, [token, activeTab, fetchOrders]);

  // Upload/Edit Product Form Fields
  const [prodName, setProdName] = useState("");
  const [prodCategory, setProdCategory] = useState("toothbrush");
  const [prodPrice, setProdPrice] = useState("");
  const [prodDescription, setProdDescription] = useState("");
  const [prodImage, setProdImage] = useState<string | null>(null);
  const [prodImagePreview, setProdImagePreview] = useState<string | null>(null);
  const [editingProductId, setEditingProductId] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [uploadSuccess, setUploadSuccess] = useState("");

  const handleProductImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    // Preview
    setProdImagePreview(URL.createObjectURL(file));

    // Base64
    const reader = new FileReader();
    reader.onloadend = () => {
      setProdImage(reader.result as string);
    };
    reader.readAsDataURL(file);
  };

  // Initialize Auth
  useEffect(() => {
    if (typeof window !== "undefined") {
      const savedToken = localStorage.getItem("dantshaant_portal_token");
      const savedRole = localStorage.getItem("dantshaant_portal_role");
      const savedName = localStorage.getItem("dantshaant_portal_name");
      if (savedToken) {
        setToken(savedToken);
        setUserRole(savedRole);
        setUserName(savedName);
      }
    }
  }, []);

  // Fetch products
  const fetchProducts = useCallback(async () => {
    if (!token) return;
    setLoadingProducts(true);
    setProductError("");
    try {
      const endpoint = activeTab === "catalog" ? `${API_BASE}/portal/products/my` : `${API_BASE}/portal/products/my`;
      const res = await fetch(endpoint, {
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        throw new Error(await res.text().catch(() => "Failed to fetch products"));
      }
      const data = await res.json();
      setProducts(data);
    } catch (e) {
      setProductError(e instanceof Error ? e.message : "Error loading catalog");
    } finally {
      setLoadingProducts(false);
    }
  }, [token, activeTab]);

  useEffect(() => {
    if (token) {
      void fetchProducts();
    }
  }, [token, activeTab, fetchProducts]);

  // Handle Authentication
  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault();
    setAuthLoading(true);
    setAuthError("");
    try {
      const endpoint = authMode === "login"
        ? `${API_BASE}/portal/auth/login`
        : `${API_BASE}/portal/auth/register`;

      const payload = authMode === "login"
        ? { email, password }
        : { email, password, name, role, clinic_name: clinicName, license_number: role === "dentist" ? licenseNumber : null };

      const res = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({ detail: "Authentication failed" }));
        throw new Error(typeof errorData.detail === "string" ? errorData.detail : JSON.stringify(errorData.detail));
      }

      const data = await res.json();
      setToken(data.access_token);
      setUserRole(data.role);
      setUserName(data.name);

      localStorage.setItem("dantshaant_portal_token", data.access_token);
      localStorage.setItem("dantshaant_portal_role", data.role);
      localStorage.setItem("dantshaant_portal_name", data.name);
    } catch (e) {
      setAuthError(e instanceof Error ? e.message : "Authentication error");
    } finally {
      setAuthLoading(false);
    }
  };

  const handleLogout = () => {
    setToken(null);
    setUserRole(null);
    setUserName(null);
    localStorage.removeItem("dantshaant_portal_token");
    localStorage.removeItem("dantshaant_portal_role");
    localStorage.removeItem("dantshaant_portal_name");
  };

  // Handle Upload or Edit Product
  const handleProductSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setUploading(true);
    setUploadError("");
    setUploadSuccess("");

    try {
      const payload = {
        name: prodName,
        category: prodCategory,
        price: parseFloat(prodPrice),
        raw_description: prodDescription,
        images: prodImage ? [prodImage] : [],
      };

      const url = editingProductId
        ? `${API_BASE}/portal/products/${editingProductId}`
        : `${API_BASE}/portal/products/upload`;

      const method = editingProductId ? "PATCH" : "POST";

      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify(payload),
      });

      if (!res.ok) {
        throw new Error(await res.text().catch(() => "Operation failed"));
      }

      setUploadSuccess(editingProductId ? "Product updated successfully!" : "Product uploaded and analyzed by AI successfully!");
      
      // Clear fields if not editing
      if (!editingProductId) {
        setProdName("");
        setProdPrice("");
        setProdDescription("");
        setProdImage(null);
        setProdImagePreview(null);
      }

      // Return to catalog tab after delay
      setTimeout(() => {
        setEditingProductId(null);
        setActiveTab("catalog");
        setUploadSuccess("");
      }, 1500);

    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "Error saving product");
    } finally {
      setUploading(false);
    }
  };

  // Trigger Edit Mode
  const startEdit = (product: Product) => {
    setEditingProductId(product.product_id);
    setProdName(product.name);
    setProdCategory(product.category);
    setProdPrice(product.price.toString());
    setProdDescription(product.ai_description); // Populate with desc
    setActiveTab("edit");
  };

  // Delete product
  const deleteProduct = async (productId: string) => {
    if (!confirm("Are you sure you want to delete this product?")) return;
    try {
      const res = await fetch(`${API_BASE}/portal/products/${productId}`, {
        method: "DELETE",
        headers: {
          Authorization: `Bearer ${token}`,
        },
      });
      if (!res.ok) {
        throw new Error(await res.text());
      }
      await fetchProducts();
    } catch (e) {
      alert(e instanceof Error ? e.message : "Error deleting product");
    }
  };

  return (
    <div className="page-shell">
      <div className="bg-orb bg-orb-a" aria-hidden />
      <div className="bg-orb bg-orb-b" aria-hidden />
      <div className="bg-grid" aria-hidden />

      <Header />

      <main className="portal-wrapper">
        {!token ? (
          // AUTHENTICATION SCREEN
          <div className="portal-card" style={{ maxWidth: "480px", margin: "2rem auto" }}>
            <h2 className="hero-title" style={{ fontSize: "1.8rem", textAlign: "center", marginBottom: "1.5rem" }}>
              Dentist Portal
            </h2>

            <div className="mode-switch mode-switch--two" style={{ marginBottom: "1.5rem" }}>
              <button
                type="button"
                className={authMode === "login" ? "active" : ""}
                onClick={() => setAuthMode("login")}
              >
                Sign In
              </button>
              <button
                type="button"
                className={authMode === "register" ? "active" : ""}
                onClick={() => setAuthMode("register")}
              >
                Create Account
              </button>
            </div>

            <form onSubmit={handleAuth} className="control-column">
              {authMode === "register" && (
                <>
                  <div className="form-group">
                    <label>Full Name</label>
                    <input
                      type="text"
                      required
                      placeholder="Dr. John Doe"
                      value={name}
                      onChange={(e) => setName(e.target.value)}
                    />
                  </div>
                  <div className="form-group">
                    <label>Role</label>
                    <select value={role} onChange={(e) => setRole(e.target.value)}>
                      <option value="dentist">Dentist</option>
                      <option value="patient">Patient</option>
                    </select>
                  </div>
                  <div className="form-group">
                    <label>Clinic Name</label>
                    <input
                      type="text"
                      required
                      placeholder="Smile Dental Clinic"
                      value={clinicName}
                      onChange={(e) => setClinicName(e.target.value)}
                    />
                  </div>
                  {role === "dentist" && (
                    <div className="form-group">
                      <label>Dental License Number</label>
                      <input
                        type="text"
                        required
                        placeholder="LIC-12345"
                        value={licenseNumber}
                        onChange={(e) => setLicenseNumber(e.target.value)}
                      />
                    </div>
                  )}
                </>
              )}

              <div className="form-group">
                <label>Email Address</label>
                <input
                  type="email"
                  required
                  placeholder="name@example.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                />
              </div>

              <div className="form-group">
                <label>Password</label>
                <input
                  type="password"
                  required
                  placeholder="••••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                />
              </div>

              {authError && <p className="alert alert-warn">{authError}</p>}

              <button
                type="submit"
                className="btn btn-glow"
                style={{ width: "100%", marginTop: "1rem" }}
                disabled={authLoading}
              >
                {authLoading ? "Please wait..." : authMode === "login" ? "Sign In" : "Register"}
              </button>
            </form>
          </div>
        ) : (
          // LOGGED IN DASHBOARD
          <div>
            <div className="portal-card" style={{ marginBottom: "2rem", padding: "1.25rem 2rem" }}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "1rem" }}>
                <div>
                  <span className="eyebrow" style={{ textTransform: "capitalize" }}>
                    Logged in as {userRole}
                  </span>
                  <h2 className="hero-title" style={{ fontSize: "1.5rem", margin: "0.2rem 0 0" }}>
                    {userName}
                  </h2>
                </div>
                <button type="button" className="btn btn-ghost" onClick={handleLogout}>
                  Sign Out
                </button>
              </div>
            </div>

            {/* Tab navigation */}
            <div className="portal-tabs">
              <button
                type="button"
                className={`portal-tab-btn ${activeTab === "catalog" ? "active" : ""}`}
                onClick={() => {
                  setEditingProductId(null);
                  setActiveTab("catalog");
                }}
              >
                Product Catalog
              </button>
              {userRole === "dentist" && (
                <button
                  type="button"
                  className={`portal-tab-btn ${activeTab === "upload" || activeTab === "edit" ? "active" : ""}`}
                  onClick={() => {
                    if (activeTab !== "edit") {
                      setProdName("");
                      setProdCategory("toothbrush");
                      setProdPrice("");
                      setProdDescription("");
                      setEditingProductId(null);
                      setActiveTab("upload");
                    }
                  }}
                >
                  {editingProductId ? "Edit Product" : "Upload Product"}
                </button>
              )}
              {userRole === "dentist" && (
                <button
                  type="button"
                  className={`portal-tab-btn ${activeTab === "orders" ? "active" : ""}`}
                  onClick={() => {
                    setEditingProductId(null);
                    setActiveTab("orders");
                  }}
                >
                  Order Notifications
                </button>
              )}
            </div>

            {/* TABS CONTENT */}
            {activeTab === "catalog" && (
              <div>
                <h3 className="hero-title" style={{ fontSize: "1.2rem", marginBottom: "1rem" }}>
                  My Dental Products
                </h3>

                {loadingProducts ? (
                  <div className="loader-ring" />
                ) : productError ? (
                  <p className="alert alert-warn">{productError}</p>
                ) : products.length === 0 ? (
                  <div className="empty-illustration">
                    <p className="empty-title">No products found</p>
                    <p className="empty-desc">
                      Upload products to see them in your catalog and recommend them to patients.
                    </p>
                  </div>
                ) : (
                  <div className="product-grid">
                    {products.map((p) => (
                      <div key={p.product_id} className="product-card">
                        {p.images && p.images.length > 0 && (
                          // eslint-disable-next-line @next/next/no-img-element
                          <img
                            src={p.images[0]}
                            alt={p.name}
                            style={{
                              width: "100%",
                              height: "180px",
                              objectFit: "cover",
                              borderRadius: "8px",
                              border: "1px solid var(--glass-border)",
                            }}
                          />
                        )}
                        <div className="product-card-header">
                          <h4 className="product-card-title">{p.name}</h4>
                          <span className="product-card-price">${p.price.toFixed(2)}</span>
                        </div>

                        <div className="product-badge-group">
                          <span className="category-badge">{p.category}</span>
                          {p.problems_solved.map((prob, idx) => (
                            <span key={idx} className="problem-badge">
                              {prob}
                            </span>
                          ))}
                        </div>

                        <p className="product-desc">{p.ai_description}</p>

                        <div className="product-stats">
                          <div className="product-stat-item">
                            <span>Views:</span>
                            <span className="product-stat-value">{p.view_count}</span>
                          </div>
                          <div className="product-stat-item">
                            <span>Recommendations:</span>
                            <span className="product-stat-value">{p.recommendation_count}</span>
                          </div>
                        </div>

                        {userRole === "dentist" && (
                          <div className="product-actions">
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              onClick={() => startEdit(p)}
                            >
                              Edit
                            </button>
                            <button
                              type="button"
                              className="btn btn-ghost btn-sm"
                              style={{ color: "var(--danger)" }}
                              onClick={() => deleteProduct(p.product_id)}
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}

            {(activeTab === "upload" || activeTab === "edit") && (
              <div className="portal-card" style={{ maxWidth: "680px" }}>
                <h3 className="hero-title" style={{ fontSize: "1.2rem", marginBottom: "1.5rem" }}>
                  {editingProductId ? "Edit Product Details" : "Upload New Dental Product"}
                </h3>

                <form onSubmit={handleProductSubmit} className="control-column">
                  <div className="form-group">
                    <label>Product Name</label>
                    <input
                      type="text"
                      required
                      placeholder="Ultra Whitening Toothpaste"
                      value={prodName}
                      onChange={(e) => setProdName(e.target.value)}
                    />
                  </div>

                  <div className="portal-grid-two">
                    <div className="form-group">
                      <label>Category</label>
                      <select value={prodCategory} onChange={(e) => setProdCategory(e.target.value)}>
                        <option value="toothbrush">Toothbrush</option>
                        <option value="toothpaste">Toothpaste</option>
                        <option value="mouthwash">Mouthwash</option>
                        <option value="floss">Floss</option>
                        <option value="whitening">Whitening</option>
                        <option value="orthodontic">Orthodontic</option>
                        <option value="other">Other</option>
                      </select>
                    </div>

                    <div className="form-group">
                      <label>Price (USD)</label>
                      <input
                        type="number"
                        required
                        step="0.01"
                        placeholder="9.99"
                        value={prodPrice}
                        onChange={(e) => setProdPrice(e.target.value)}
                      />
                    </div>
                  </div>

                  <div className="form-group">
                    <label>{editingProductId ? "Product Description" : "Raw Description (AI will polish this)"}</label>
                    <textarea
                      required
                      rows={4}
                      placeholder="e.g. This is a special toothpaste that uses fluoride and baking soda to restore enamel and remove stains."
                      value={prodDescription}
                      onChange={(e) => setProdDescription(e.target.value)}
                    />
                  </div>

                  <div className="form-group">
                    <label>Product Image {!editingProductId && <span style={{ color: "var(--danger)" }}>*</span>}</label>
                    <input
                      type="file"
                      accept="image/*"
                      required={!editingProductId}
                      onChange={handleProductImageChange}
                    />
                    {prodImagePreview && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img
                        src={prodImagePreview}
                        alt="Product preview"
                        style={{
                          width: "100px",
                          height: "100px",
                          objectFit: "cover",
                          marginTop: "0.5rem",
                          borderRadius: "8px",
                          border: "1px solid var(--glass-border)",
                        }}
                      />
                    )}
                  </div>

                  {uploadError && <p className="alert alert-warn">{uploadError}</p>}
                  {uploadSuccess && (
                    <p className="alert" style={{ background: "rgba(61, 214, 140, 0.1)", border: "1px solid rgba(61, 214, 140, 0.25)", color: "var(--success)" }}>
                      {uploadSuccess}
                    </p>
                  )}

                  <div style={{ display: "flex", gap: "1rem", marginTop: "1rem" }}>
                    <button
                      type="button"
                      className="btn btn-ghost"
                      onClick={() => {
                        setEditingProductId(null);
                        setActiveTab("catalog");
                      }}
                      disabled={uploading}
                    >
                      Cancel
                    </button>
                    <button type="submit" className="btn btn-glow" disabled={uploading}>
                      {uploading ? (
                        <span style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                          <span className="loader-ring-inner" style={{ display: "inline-block", width: "12px", height: "12px", border: "2px solid white", borderTopColor: "transparent", borderRadius: "50%", animation: "spin 0.6s linear infinite" }} />
                          {editingProductId ? "Updating..." : "AI analyzing product..."}
                        </span>
                      ) : (
                        editingProductId ? "Save Changes" : "Upload & Analyze"
                      )}
                    </button>
                  </div>
                </form>
              </div>
            )}

            {activeTab === "orders" && (
              <div>
                <h3 className="hero-title" style={{ fontSize: "1.2rem", marginBottom: "1rem" }}>
                  Order Notifications & Purchases
                </h3>

                {loadingOrders ? (
                  <div style={{ display: "flex", justifyContent: "center", padding: "2rem" }}>
                    <div className="loader-ring">
                      <div className="loader-ring-inner" />
                    </div>
                  </div>
                ) : ordersError ? (
                  <p className="error-msg">{ordersError}</p>
                ) : orders.length === 0 ? (
                  <div className="empty-illustration" style={{ padding: "3rem" }}>
                    <div className="empty-icon">📦</div>
                    <p className="empty-title">No orders yet</p>
                    <p className="empty-desc">When patients purchase your recommended items, order notifications will appear here in real time.</p>
                  </div>
                ) : (
                  <div style={{ display: "flex", flexDirection: "column", gap: "1rem" }}>
                    {orders.map((o) => (
                      <div key={o.order_id} className="rec-product-card rec-product-card--split" style={{ padding: "1.25rem", cursor: "default", justifyContent: "space-between", flexWrap: "wrap", gap: "1rem" }}>
                        <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "monospace" }}>
                            Order: #{o.order_id.slice(-6).toUpperCase()}
                          </span>
                          <span style={{ fontSize: "1rem", fontWeight: 700, color: "#fff" }}>
                            {o.product_name}
                          </span>
                          <span style={{ fontSize: "0.8rem", color: "var(--text-muted)" }}>
                            Buyer: {o.patient_name} ({o.patient_email})
                          </span>
                          <span style={{ fontSize: "0.75rem", color: "var(--text-muted)" }}>
                            Date: {new Date(o.created_at).toLocaleDateString()} at {new Date(o.created_at).toLocaleTimeString()}
                          </span>
                        </div>

                        <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                          <div style={{ textAlign: "right" }}>
                            <div style={{ fontSize: "1.1rem", fontWeight: 700, color: "var(--accent)" }}>
                              ${o.price.toFixed(2)}
                            </div>
                            <span className={`chip chip-${o.status === "shipped" ? "live" : "analyzing"}`} style={{ textTransform: "capitalize", background: o.status === "shipped" ? "rgba(16, 185, 129, 0.1)" : "rgba(245, 158, 11, 0.1)", color: o.status === "shipped" ? "#10b981" : "#f59e0b", border: "1px solid currentColor" }}>
                              {o.status}
                            </span>
                          </div>

                          {o.status === "pending" && (
                            <button
                              type="button"
                              className="btn btn-buy btn-sm"
                              style={{ background: "linear-gradient(135deg, #10b981 0%, #059669 100%)", color: "#fff", alignSelf: "center" }}
                              onClick={() => handleUpdateOrderStatus(o.order_id, "shipped")}
                            >
                              Mark Shipped
                            </button>
                          )}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        )}
      </main>

      <footer className="site-footer">
        <span>DantShaant © 2026</span>
        <span className="footer-dot" />
        <span>Awareness tool — not a medical diagnosis</span>
      </footer>
    </div>
  );
}
