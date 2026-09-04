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
import { ModalPortal } from "@/components/common/ModalPortal";
import { useLanguage } from "@/i18n";
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
  const { t } = useLanguage();
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
    if (!confirm(t("products_mgmt.confirm_delete"))) return;
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
            <h1 className={styles.title}>{t("products_mgmt.title")}</h1>
            <p className={styles.subtitle}>
              {t("products_mgmt.subtitle")}
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
            ➕ {t("products_mgmt.add_btn")}
          </button>
        </div>

        {error && (
          <div className={styles.error}>
            <span>⚠️ {error}</span>
            <button onClick={() => setError("")}>×</button>
          </div>
        )}

        {showForm && (
          <ModalPortal>
            <div className={styles.modalOverlay} onClick={() => setShowForm(false)}>
              <div className={styles.modal} onClick={(e) => e.stopPropagation()}>
                <h2 className={styles.modalTitle}>
                  {editingId ? t("products_mgmt.edit") : t("products_mgmt.add_btn")}
                </h2>
                
                <form onSubmit={handleSubmit} className={styles.form}>
                  <div className={styles.formGroup}>
                    <label>{t("products_mgmt.name")}</label>
                    <input
                      type="text"
                      value={formData.name}
                      onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                      placeholder="e.g., Advanced Fluoride Shield Toothpaste"
                      required
                    />
                  </div>

                  <div className={styles.formRow}>
                    <div className={styles.formGroup}>
                      <label>{t("products_mgmt.category")}</label>
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
                      <label>{t("products_mgmt.price")}</label>
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
                    <label>{t("products_mgmt.description")}</label>
                    <textarea
                      value={formData.raw_description}
                      onChange={(e) => setFormData({ ...formData, raw_description: e.target.value })}
                      placeholder="Clinical description of the product and its oral hygiene benefits..."
                      rows={4}
                      required
                    />
                    <span className={styles.hint}>
                      AI will enhance this description for patients based on screening findings
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
                      {t("products_mgmt.cancel")}
                    </button>
                    <button type="submit" className={styles.btnPrimary} disabled={submitting}>
                      {submitting ? t("common.loading") : editingId ? t("products_mgmt.save") : t("products_mgmt.add_btn")}
                    </button>
                  </div>
                </form>
              </div>
            </div>
          </ModalPortal>
        )}

        {loading ? (
          <div className={styles.loading}>
            <div className={styles.spinner} />
            <p>{t("common.loading")}</p>
          </div>
        ) : products.length === 0 ? (
          <div className={styles.empty}>
            <div className={styles.emptyIcon}>📦</div>
            <h3>{t("products_mgmt.empty")}</h3>
            <p>{t("products_mgmt.subtitle")}</p>
            <button
              type="button"
              className={styles.btnPrimary}
              onClick={() => {
                setShowForm(true);
                setEditingId(null);
              }}
            >
              {t("products_mgmt.add_btn")}
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
                      title="Toggle status"
                    >
                      {product.status}
                    </button>
                  </div>
                  <div className={styles.cardActions}>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      onClick={() => handleEdit(product)}
                      title={t("products_mgmt.edit")}
                    >
                      ✏️
                    </button>
                    <button
                      type="button"
                      className={styles.iconBtn}
                      onClick={() => handleDelete(product.product_id)}
                      title={t("products_mgmt.delete")}
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
