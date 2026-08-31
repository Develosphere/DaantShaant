"use client";

import styles from "./portal-auth.module.css";

type Props = {
  preview: string | null;
  onChange: (file: File | null, dataUrl: string | null) => void;
};

export function ProfileImageField({ preview, onChange }: Props) {
  return (
    <div className={styles.avatarField}>
      <div className={styles.avatarRing}>
        <img
          src={preview ?? "/default-avatar.svg"}
          alt="Profile preview"
          className={styles.avatarPreview}
        />
      </div>
      <div className={`${styles.formGroup} ${styles.avatarUpload}`}>
        <label htmlFor="profile-image-input">Profile photo</label>
        <label htmlFor="profile-image-input" className={styles.fileBtn}>
          Choose image
        </label>
        <input
          id="profile-image-input"
          type="file"
          accept="image/jpeg,image/png,image/webp"
          className={styles.fileInput}
          onChange={(e) => {
            const file = e.target.files?.[0] ?? null;
            if (!file) {
              onChange(null, null);
              return;
            }
            const reader = new FileReader();
            reader.onload = () => onChange(file, reader.result as string);
            reader.readAsDataURL(file);
          }}
        />
        <span className={styles.hint}>Optional — default icon used if skipped</span>
      </div>
    </div>
  );
}
