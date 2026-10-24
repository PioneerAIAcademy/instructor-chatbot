// frontend/app/lib/i18n.ts
//
// i18n helpers for the Instructor Assistant interface (every string in
// app/lib/chrome-strings.ts).
//
// Detection cascade (`getInitialLanguage`):
//   1. localStorage `user_language_pref` (set by the SettingsMenu picker)
//      - "auto"   -> fall through to step 2
//      - <code>   -> return as-is (manual override wins)
//   2. `navigator.language` matched against SUPPORTED_LANGS
//      - This implements "user in Spain -> Spanish UI" without geo-IP,
//        because the browser locale typically matches the user's region.
//   3. Default to "en"
//
// The chosen value is also passed to the backend in the chat request
// `data.user_language_pref` so server-side LLM responses align with the
// UI language. When the user picks "auto", the backend reverts to its
// existing text-detection cascade (LocalizationManager.detect_language).

// The interface languages (owner, 2026-10-20): the instructor countries are
// the US, Mexico, Brazil, and the Philippines (English). A stored pick of any
// other code (from before this list was trimmed) reads as "auto".
export const SUPPORTED_LANGS = ["en", "es", "pt"] as const;

export type LangCode = (typeof SUPPORTED_LANGS)[number];
export type LangPref = "auto" | LangCode;

export const LANG_LABELS: Record<LangCode, { native: string; english: string }> = {
  en: { native: "English", english: "English" },
  es: { native: "Español", english: "Spanish" },
  pt: { native: "Português", english: "Portuguese" },
};

const STORAGE_KEY = "user_language_pref";

function isLangCode(value: string): value is LangCode {
  return (SUPPORTED_LANGS as readonly string[]).includes(value);
}

function normalizeBrowserLocale(raw: string | undefined | null): LangCode | null {
  if (!raw) return null;
  const base = raw.toLowerCase().split("-")[0].split("_")[0];
  return isLangCode(base) ? base : null;
}

export function getUserLanguagePref(): LangPref {
  if (typeof window === "undefined") return "auto";
  const stored = window.localStorage.getItem(STORAGE_KEY);
  if (!stored) return "auto";
  if (stored === "auto") return "auto";
  return isLangCode(stored) ? stored : "auto";
}

export function setUserLanguagePref(pref: LangPref): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, pref);
}

/**
 * Resolves the effective language code for rendering UI chrome. When the
 * user has chosen "auto", we fall back to navigator.language matched
 * against SUPPORTED_LANGS, then to English. The "auto" value itself is
 * what gets sent to the backend so it can run its own detection.
 */
export function resolveUiLanguage(): LangCode {
  const pref = getUserLanguagePref();
  if (pref !== "auto") return pref;
  if (typeof navigator !== "undefined") {
    const fromNavigator = normalizeBrowserLocale(navigator.language);
    if (fromNavigator) return fromNavigator;
  }
  return "en";
}
