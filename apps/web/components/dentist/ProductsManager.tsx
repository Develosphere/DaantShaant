"use client";

import { useEffect, useState } from "react";
import { PortalDashboard } from "@/components/portal/PortalDashboard";
import {
  listMyProducts,
  uploadProduct,
  updateProduct,
  deleteProduct,
  type Product,
  type ProductCategory,
  type ProductUpload,
} from "@/lib/product-api";
import styles from "./products-manager.module.css";

const CATEGORIES: { value: ProductCategory; label: string }[] = [
  { value: "toothbrush", label: "Toothbrush" },
  { value: "toothpaste", label: "Toothpaste" },
  { value: "whitening", label: "Whitening" },
  { value: "floss", label: "Floss" },
  { value: "mouthwash", label: "Mouthwash" },
  { value: "other", label: "Other" },
];

export function ProductsManager() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [showForm, setShowForm] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);

  // Form state
  const [formData, setFormData] = useState<ProductUpload>({
    name: "",
    category: "toothpaste",
    price: 0,
    raw_description: "",
  });
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    loadProducts();
  }, []);

  async function loadProducts() {
    setLoading(true);
    setError("");
    try {
      const data = await listMyProducts();
      setProducts(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load products");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    setError("");

    try {
      if (editingId) {
        await updateProduct(editingId, formData);
      } else {
        await uploadProduct(formData);
      }
      setShowForm(false);
      setEditingId(null);
      setFormData({ name: "", category: "toothpaste", price: 0, raw_description: "" });
      loadProducts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      setSubmitting(false);
    }
  }

  function handleEdit(product: Product) {
    setFormData({
      name: product.name,
      category: product.category as ProductCategory,
      price: product.price,
      raw_description: product.raw_description,
    });
    setEditingId(product.product_id);
    setShowForm(true);
  }

  async function handleDelete(id: string) {
    if (!confirm("Are you sure you want to delete this product?")) return;
    try {
      await deleteProduct(id);
      loadProducts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to delete product");
    }
  }

  async function handleToggleStatus(product: Product) {
    try {
      await updateProduct(product.product_id, {
        status: product.status === "active" ? "inactive" : "active",
      });
      loadProducts();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status");
    }
  }

  return (
    <PortalDashboard role="dentist" maxWidth={1200}>
      <div className={styles.container}>
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Product Catalog</h1>
            <p className={styles.subtitle}>
              Manage your dental products and recommendations
            </p>
          </div>
          <button
            type="button"
            className={styles.btnPrimary}
            onClick={() => {
              setShowForm(true);
              setEditingId(null);
              setFormData({ name: "", category: "toothpaste", price: 0, raw_description: "" });
            }}
          >
            ➕ Add Product
          </button>
        </div>

        {error && (
          <div className={styles.error}>
            <span>⚠️ {error}</span>
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        {showForm && (
          <div className={styles.modalOverlay} onClick={() => setShowForm(false)}>
            <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
              <h2 className={styles.modalTitle}>
                {editingId ? "Edit Product" : "Add New Product"}
              </h2>
              
              <form onSubmit={handleSubmit} className={styles.form}>
                <div className={styles.formGroup}>
                  <label>Product Name</label>
                  <input
                    type="text"
                    value={formData.name}
                    onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                    placeholder="e.g., Advanced Whitening Toothpaste"
                    required
                  />
                </div>

                <div className={styles.formRow}>
                  <div className={styles.formGroup}>
                    <label>Category</label>
                    <select
                      value={formData.category}
                      onChange={(e) =>
                        setFormData({ ...formData, category: e.target.value as ProductCategory })
                      }
                      required
                    >
                      {CATEGORIES.map((cat) => (
                        <option key={cat.value} value={cat.value}>
                          {cat.label}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div className={styles.formGroup}>
                    <label>Price ($)</label>
                    <input
                      type="number"
                      step="0.01"
                      min="0"
                      value={formData.price}
                      onChange={(e) =>
                        setFormData({ ...formData, price: parseFloat(e.target.value) || 0 })
                      }
                      placeholder="0.00"
                      required
                    />
                  </div>
                </div>

                <div className={styles.formGroup}>
                  <label>Description</label>
                  <textarea
                    value={formData.raw_description}
                    onChange={(e) => setFormData({ ...formData, raw_description: e.target.value })}
                    placeholder="Brief description of the product and its benefits..."
                    rows={4}
                    required
                  />
                  <span className={styles.hint}>
                    AI will enhance this description for patients
                  </span>
                </div>

                <div className={styles.formActions}>
                  <button
                    type="button"
                    className={styles.btnSecondary}
                    onClick={() => {
                      setShowForm(false);
                      setEditingId(null);
                    }}
                    disabled={submitting}
                  >
                    Cancel
                  </button>
                  <button type="submit" className={styles.btnPrimary} disabled={submitting}>
                    {submitting ? "Saving..." : editingId ? "Update" : "Add Product"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        )}

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <p>Loading products...</p>
          </div>
        ) : products.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>📦</div>
            <h3>No products yet</h3>
            <p>Start building your catalog by adding your first product</p>
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={() => {
                setShowForm(true);
                setEditingId(null);
              }}
            >
              Add Your First Product
            </button>
          </div>
        ) : (
          <div className={styles.grid}>
            {products.map((product) => (
              <div key={product.product_id} className={styles.card}>
                <div className={styles.cardHeader}>
                  <div>
                    <span className={styles.category}>{product.category}</span>
                    <button
                      type="button"
                      className={`${styles.statusBadge} ${
                        product.status === "active" ? styles.statusActive : styles.statusInactive
                      }`}
                      onClick={() => handleToggleStatus(product)}
                      title="Click to toggle status"
                    >
                      {product.status}
                    </button>
                  </div>
                  <div className={styles.cardActions}>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      onClick={() => handleEdit(product)}
                      title="Edit"
                    >
                      ✏️
                    </button>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      onClick={() => handleDelete(product.product_id)}
                      title="Delete"
                    >
                      🗑️
                    </button>
                  </div>
                </div>

                <h3 className={styles.cardTitle}>{product.name}</h3>
                <p className={styles.price}>${product.price.toFixed(2)}</p>
                
                <div className={styles.cardBody}>
                  <p className={styles.description}>{product.ai_description}</p>
                  
                  {product.problems_solved.length > 0 && (
                    <div className={styles.problems}>
                      <strong>Helps with:</strong>
                      <ul>
                        {product.problems_solved.slice(0, 3).map((problem, i) => (
                          <li key={i}>{problem}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>

                <div className={styles.cardFooter}>
                  <span className={styles.date}>
                    Updated {new Date(product.updated_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </PortalDashboard>
  );
}
