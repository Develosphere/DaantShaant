"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import type { PortalRole } from "@/lib/portal-types";
import { registerPortal } from "@/lib/portal-auth";
import { PortalAuthShell } from "./PortalAuthShell";
import { ProfileImageField } from "./ProfileImageField";
import { usePortalGuestGuard } from "./usePortalGuestGuard";
import styles from "./portal-auth.module.css";

type Props = { role: PortalRole };

export function RegisterPage({ role }: Props) {
  usePortalGuestGuard(role);
  const router = useRouter();
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [location, setLocation] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [profileImage, setProfileImage] = useState<string | null>(null);
  const [preview, setPreview] = useState<string | null>(null);

  const [degree, setDegree] = useState("");
  const [degreeYear, setDegreeYear] = useState("");
  const [institution, setInstitution] = useState("");
  const [specializedTraining, setSpecializedTraining] = useState("");

  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");

    if (password !== confirmPassword) {
      setError("Passwords do not match");
      return;
    }
    if (password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setLoading(true);
    try {
      const payload = {
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        email: email.trim(),
        password,
        phone: phone.trim(),
        location: location.trim(),
        profile_image: profileImage,
        ...(role === "dentist"
          ? {
              degree: degree.trim(),
              degree_year: parseInt(degreeYear, 10),
              institution: institution.trim(),
              specialized_training: specializedTraining.trim() || undefined,
            }
          : {}),
      };

      await registerPortal(role, payload);
      router.push(`/${role}/dashboard`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Registration failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <PortalAuthShell role={role} mode="register">
      <form
        className={`${styles.form} ${styles.formRegister}`}
        onSubmit={handleSubmit}
      >
        {error && (
          <div className={styles.error} role="alert">
            {error}
          </div>
        )}

        <ProfileImageField
          preview={preview}
          onChange={(_file, dataUrl) => {
            setProfileImage(dataUrl);
            setPreview(dataUrl);
          }}
        />

        <div className={styles.row}>
          <div className={styles.formGroup}>
            <label htmlFor={`${role}-first`}>First name</label>
            <input
              id={`${role}-first`}
              required
              placeholder="First name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
            />
          </div>
          <div className={styles.formGroup}>
            <label htmlFor={`${role}-last`}>Last name</label>
            <input
              id={`${role}-last`}
              required
              placeholder="Last name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
            />
          </div>
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-reg-email`}>Email address</label>
          <input
            id={`${role}-reg-email`}
            type="email"
            required
            autoComplete="email"
            placeholder="you@example.com"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-phone`}>Phone</label>
          <input
            id={`${role}-phone`}
            type="tel"
            required
            placeholder="+92 300 1234567"
            value={phone}
            onChange={(e) => setPhone(e.target.value)}
          />
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-location`}>Location</label>
          <input
            id={`${role}-location`}
            required
            placeholder="City, Country"
            value={location}
            onChange={(e) => setLocation(e.target.value)}
          />
        </div>

        {role === "dentist" && (
          <div className={styles.dentistBlock}>
            <p className={styles.sectionLabel}>Professional credentials</p>
            <div className={styles.formGroup}>
              <label htmlFor={`${role}-degree`}>Degree</label>
              <input
                id={`${role}-degree`}
                required
                placeholder="BDS, DDS, etc."
                value={degree}
                onChange={(e) => setDegree(e.target.value)}
              />
            </div>
            <div className={styles.row}>
              <div className={styles.formGroup}>
                <label htmlFor={`${role}-year`}>Year completed</label>
                <input
                  id={`${role}-year`}
                  type="number"
                  required
                  min={1950}
                  max={2030}
                  placeholder="2024"
                  value={degreeYear}
                  onChange={(e) => setDegreeYear(e.target.value)}
                />
              </div>
              <div className={styles.formGroup}>
                <label htmlFor={`${role}-inst`}>Institution</label>
                <input
                  id={`${role}-inst`}
                  required
                  placeholder="University name"
                  value={institution}
                  onChange={(e) => setInstitution(e.target.value)}
                />
              </div>
            </div>
            <div className={styles.formGroup}>
              <label htmlFor={`${role}-training`}>
                Specialized training{" "}
                <span className={styles.optional}>(optional)</span>
              </label>
              <input
                id={`${role}-training`}
                placeholder="e.g. Orthodontics fellowship"
                value={specializedTraining}
                onChange={(e) => setSpecializedTraining(e.target.value)}
              />
            </div>
          </div>
        )}

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-reg-pass`}>Password</label>
          <input
            id={`${role}-reg-pass`}
            type="password"
            required
            autoComplete="new-password"
            placeholder="Min. 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
          />
          <span className={styles.hint}>
            At least 8 characters, with a letter and a number
          </span>
        </div>

        <div className={styles.formGroup}>
          <label htmlFor={`${role}-confirm`}>Confirm password</label>
          <input
            id={`${role}-confirm`}
            type="password"
            required
            autoComplete="new-password"
            placeholder="Repeat password"
            value={confirmPassword}
            onChange={(e) => setConfirmPassword(e.target.value)}
          />
        </div>

        <button type="submit" className={styles.submit} disabled={loading}>
          {loading ? "Creating account…" : "Create account"}
        </button>
      </form>
    </PortalAuthShell>
  );
}
