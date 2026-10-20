"use client";

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
    <div className="w-full max-w-[640px] md:max-w-[720px] lg:max-w-[840px] xl:max-w-[960px] 2xl:max-w-[1120px] px-4 sm:px-8 py-4 bg-[#F0EEE6] dark:bg-white/5 border border-[rgba(31,30,29,0.12)] dark:border-transparent rounded-2xl">
      <p className="text-xs sm:text-sm text-[#3D3D3A] dark:text-gray-300">
        <span className="font-bold">{strings.disclaimerLabel}</span>
        {strings.disclaimerBody}
      </p>
    </div>
  );
}
