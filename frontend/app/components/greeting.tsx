"use client";

import { useEffect, useState } from "react";
import { getChromeStrings } from "../lib/chrome-strings";
import { resolveUiLanguage } from "../lib/i18n";

type TimePeriod = "morning" | "afternoon" | "evening" | "after_hours";

const getTimePeriod = (hour: number): TimePeriod => {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  if (hour >= 18 && hour < 22) return "evening";
  return "after_hours";
};

// The welcome heading, "Good morning. What can I help with?", and a subtitle.
// The time of day is only known in the browser, so the heading keeps its
// space but stays invisible until it mounts (no flash of the wrong greeting).
export default function Greeting() {
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  const [period, setPeriod] = useState<TimePeriod | null>(null);

  useEffect(() => {
    setUiLang(resolveUiLanguage());
    setPeriod(getTimePeriod(new Date().getHours()));
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);

  const strings = getChromeStrings(uiLang);
  const timeOfDay = {
    morning: strings.greetingMorning,
    afternoon: strings.greetingAfternoon,
    evening: strings.greetingEvening,
    after_hours: strings.greetingAfterHours,
  }[period ?? "morning"];

  return (
    <div className="flex flex-col items-center gap-2 px-2 text-center">
      <h1
        className={`text-[26px] font-bold leading-tight tracking-[-0.01em] text-ia-text sm:text-[32px] ${period ? "" : "invisible"}`}
      >
        {timeOfDay} {strings.greetingQuestion}
      </h1>
      <p className="text-[15px] text-ia-muted sm:text-base">
        {strings.welcomeSub}
      </p>
    </div>
  );
}
