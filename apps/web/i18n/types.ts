export type Locale = "en" | "ur";

export type TranslationDictionary = {
  [key: string]: string | TranslationDictionary;
};
