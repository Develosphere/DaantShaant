"use client";

import React, { createContext, useContext, useEffect, useState, useMemo, useCallback } from "react";
import type { Locale } from "./types";
import { en } from "./en";
import { ur } from "./ur";

type TranslationKey = keyof typeof en;

interface LanguageContextType {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  toggleLanguage: () => void;
  t: (key: string, params?: Record<string, string | number>) => string;
  dir: "ltr" | "rtl";
}

const dictionaries: Record<Locale, Record<string, string>> = {
  en,
  ur,
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
    (key: string, params?: Record<string, string | number>): string => {
      const dict = dictionaries[locale] || dictionaries.en;
      let text = dict[key] || dictionaries.en[key] || key;

      if (params) {
        Object.entries(params).forEach(([k, v]) => {
          text = text.replace(new RegExp(`\\{${k}\\}`, "g"), String(v));
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
