"use client";

import { Info } from "lucide-react";
import { useEffect, useState } from "react";
import { resolveUiLanguage } from "../lib/i18n";
import { getChromeStrings } from "../lib/chrome-strings";

export default function DisclaimerMessage() {
  const [uiLang, setUiLang] = useState<ReturnType<typeof resolveUiLanguage>>("en");

  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);

  const strings = getChromeStrings(uiLang);

  return (
    // Info notice (direction D): Blue 3 left bar on the surface.
    <div className="flex w-full items-start gap-3 rounded-xl border border-l-4 border-ia-border border-l-ia-blue-3 bg-ia-surface p-4">
      <Info aria-hidden="true" className="mt-0.5 h-5 w-5 flex-shrink-0 text-ia-blue-3" />
      <p className="m-0 text-[15px] leading-normal text-ia-text">
        <span className="font-bold">{strings.disclaimerLabel}</span>
        {strings.disclaimerBody}
      </p>
    </div>
  );
}
