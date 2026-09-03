"use client";

import React, { createContext, useContext, useEffect, useState, useMemo, useCallback } from "react";
import type { Locale } from "./types";
import { en } from "./en";
import { ur } from "./ur";

interface LanguageContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLanguage: () => void;
  t: (
    key: string,
    fallbackOrParams?: string | Record<string, string | number>,
    params?: Record<string, string | number>
  ) => string;
  dir: "ltr" | "rtl";
}

const dictionaries: Record<Locale, Record<string, string>> = {
  en,
  ur,
};

// Case-insensitive lookup map pre-computed for safety
const lowercaseMaps: Record<Locale, Record<string, string>> = {
  en: Object.keys(en).reduce((acc, k) => {
    acc[k.toLowerCase()] = en[k as keyof typeof en];
    return acc;
  }, {} as Record<string, string>),
  ur: Object.keys(ur).reduce((acc, k) => {
    acc[k.toLowerCase()] = ur[k as keyof typeof ur];
    return acc;
  }, {} as Record<string, string>),
};

const LanguageContext = createContext<LanguageContextType>({
  locale: "en",
  setLocale: () => {},
  toggleLanguage: () => {},
  t: (key: string) => key,
  dir: "ltr",
});

const STORAGE_KEY = "daantshaant_locale";

export function LanguageProvider({ children }: { children: React.ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("en");
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY) as Locale | null;
      if (saved === "en" || saved === "ur") {
        setLocaleState(saved);
      }
    } catch {
      // localStorage unavailable in some environments
    }
    setMounted(true);
  }, []);

  useEffect(() => {
    if (typeof document !== "undefined") {
      document.documentElement.lang = locale;
      document.documentElement.dir = locale === "ur" ? "rtl" : "ltr";
      if (locale === "ur") {
        document.documentElement.classList.add("lang-ur");
      } else {
        document.documentElement.classList.remove("lang-ur");
      }
    }
  }, [locale]);

  const setLocale = useCallback((newLocale: Locale) => {
    setLocaleState(newLocale);
    try {
      localStorage.setItem(STORAGE_KEY, newLocale);
    } catch {}
  }, []);

  const toggleLanguage = useCallback(() => {
    setLocale(locale === "en" ? "ur" : "en");
  }, [locale, setLocale]);

  const t = useCallback(
    (
      key: string,
      fallbackOrParams?: string | Record<string, string | number>,
      params?: Record<string, string | number>
    ): string => {
      let explicitFallback: string | undefined;
      let interpolationParams: Record<string, string | number> | undefined;

      if (typeof fallbackOrParams === "string") {
        explicitFallback = fallbackOrParams;
        interpolationParams = params;
      } else if (typeof fallbackOrParams === "object" && fallbackOrParams !== null) {
        interpolationParams = fallbackOrParams;
      }

      const dict = dictionaries[locale] || dictionaries.en;
      const lowerMap = lowercaseMaps[locale] || lowercaseMaps.en;
      const enLowerMap = lowercaseMaps.en;

      // 1. Direct exact key lookup
      let text: string | undefined = dict[key] || dictionaries.en[key];

      // 2. Case-insensitive lookup fallback
      if (!text) {
        const lowerKey = key.toLowerCase();
        text = lowerMap[lowerKey] || enLowerMap[lowerKey];
      }

      // 3. Fallback resolution if still missing
      if (!text) {
        if (process.env.NODE_ENV !== "production") {
          console.warn(`[i18n] Missing translation key: "${key}" for locale "${locale}"`);
        }

        if (explicitFallback) {
          text = explicitFallback;
        } else {
          // Format a safe, human-readable fallback from the key's last segment
          const lastSegment = key.split(".").pop() || key;
          text = lastSegment
            .replace(/_/g, " ")
            .replace(/\b\w/g, (c) => c.toUpperCase());
        }
      }

      // 4. Interpolate {param} placeholders
      if (interpolationParams && text) {
        Object.entries(interpolationParams).forEach(([k, v]) => {
          text = text!.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
        });
      }

      return text;
    },
    [locale]
  );

  const dir: "ltr" | "rtl" = locale === "ur" ? "rtl" : "ltr";

  const value = useMemo(
    () => ({
      locale,
      setLocale,
      toggleLanguage,
      t,
      dir,
    }),
    [locale, setLocale, toggleLanguage, t, dir]
  );

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
}

export function useLanguage() {
  return useContext(LanguageContext);
}

