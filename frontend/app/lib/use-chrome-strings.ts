"use client";

import { useEffect, useState } from "react";
import { getChromeStrings, type ChromeStrings } from "./chrome-strings";
import { type LangCode, resolveUiLanguage } from "./i18n";

/**
 * The interface language and its strings, following Settings → Language
 * (SettingsMenu dispatches `user-language-pref-changed`). English until the
 * component mounts, because the language is only known in the browser.
 */
export function useUiLanguage(): LangCode {
  const [uiLang, setUiLang] = useState<LangCode>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  return uiLang;
}

export function useChromeStrings(): ChromeStrings {
  return getChromeStrings(useUiLanguage());
}
