const MAX_BYTES = 12 * 1024 * 1024; // 12 MB
const ALLOWED = ["image/jpeg", "image/png", "image/webp"];

export type ImagePayload = {
  base64: string;
  mimeType: string;
  previewUrl: string;
  fileName: string;
};

export async function fileToImagePayload(file: File): Promise<ImagePayload> {
  if (!ALLOWED.includes(file.type)) {
    throw new Error("Use JPEG, PNG, or WebP images only.");
  }
  if (file.size > MAX_BYTES) {
    throw new Error("Image must be under 12 MB.");
  }

  const dataUrl = await readAsDataUrl(file);
  const base64 = dataUrl.split(",")[1];
  if (!base64) {
    throw new Error("Could not read image file.");
  }

  return {
    base64,
    mimeType: file.type,
    previewUrl: dataUrl,
    fileName: file.name,
  };
}

function readAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(new Error("Failed to read file"));
    reader.readAsDataURL(file);
  });
}
