import { API_BASE, getStoredUser } from "./portal-auth";

export type ProductCategory =
  | "toothbrush"
  | "toothpaste"
  | "whitening"
  | "floss"
  | "mouthwash"
  | "other";

export type ProductStatus = "active" | "inactive";

export type Product = {
  product_id: string;
  dentist_id: string;
  name: string;
  category: string;
  price: number;
  raw_description: string;
  ai_description: string;
  problems_solved: string[];
  status: string;
  image_url?: string | null;
  created_at: string;
  updated_at: string;
};

export type ProductUpload = {
  name: string;
  category: ProductCategory;
  price: number;
  raw_description: string;
};

export type ProductUpdate = {
  name?: string;
  price?: number;
  raw_description?: string;
  status?: ProductStatus;
};

function authHeaders(role: "dentist" | "patient" = "dentist"): HeadersInit {
  const user = getStoredUser(role);
  if (!user?.access_token) throw new Error(`Please sign in as a ${role}`);
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${user.access_token}`,
  };
}

export async function uploadProduct(
  product: ProductUpload
): Promise<{ product_id: string; ai_description: string; problems_solved: string[] }> {
  const res = await fetch(`${API_BASE}/portal/products/upload`, {
    method: "POST",
    headers: authHeaders("dentist"),
    body: JSON.stringify(product),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to upload product");
  }
  return res.json();
}

export async function listMyProducts(): Promise<Product[]> {
  const res = await fetch(`${API_BASE}/portal/products/my`, {
    headers: authHeaders("dentist"),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : "Failed to fetch products"
    );
  }
  return res.json();
}

export async function listProducts(params?: {
  category?: string;
  search?: string;
  limit?: number;
}): Promise<Product[]> {
  const query = new URLSearchParams();
  if (params?.category) query.set("category", params.category);
  if (params?.search) query.set("search", params.search);
  if (params?.limit) query.set("limit", String(params.limit));

  const url = `${API_BASE}/portal/products/${query.toString() ? `?${query}` : ""}`;
  const res = await fetch(url);
  
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : "Failed to fetch products"
    );
  }
  return res.json();
}

export async function getProduct(productId: string): Promise<Product> {
  const res = await fetch(`${API_BASE}/portal/products/${productId}`);
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(
      typeof err.detail === "string" ? err.detail : "Failed to fetch product"
    );
  }
  return res.json();
}

export async function updateProduct(
  productId: string,
  updates: ProductUpdate
): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/portal/products/${productId}`, {
    method: "PATCH",
    headers: authHeaders("dentist"),
    body: JSON.stringify(updates),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to update product");
  }
  return res.json();
}

export async function deleteProduct(productId: string): Promise<{ message: string }> {
  const res = await fetch(`${API_BASE}/portal/products/${productId}`, {
    method: "DELETE",
    headers: authHeaders("dentist"),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(typeof err.detail === "string" ? err.detail : "Failed to delete product");
  }
  return res.json();
}
