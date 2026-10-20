"use client";

import { useEffect, useState } from "react";
import { getChromeStrings } from "../lib/chrome-strings";
import { resolveUiLanguage } from "../lib/i18n";

// Array of friendly, casual greetings to randomly display to users
const WARM_TEXTS = [
  "Welcome!",
  "Need assistance?",
  "What do you need?",
  "What can I do for you?",
  "What's on your mind?",
  "Need help?",
  "Hello, how can I support?",
  "Here to help!",
  "Need a hand?",
  "How's it going?",
  "Got questions?",
  "How can I assist?",
  "How can I help with your course?",
  "What's up?",
  "How may I assist you?",
  "What can I help you find?",
  "Need a hand with a course question?",
  "Let's find an answer together",
  "Looks like you have a question.",
];

// Late-night (after_hours, 22:00–05:00) extras appended to WARM_TEXTS.
const AFTER_HOURS_TEXTS = [
  "Up late? How can I help?",
  "Still up? I'm here to help.",
  "Working late? What can I do for you?",
  "Looks like we're both still awake.",
  "Still awake? Let's make it worth it.",
  "Quiet hours — a good time to get things done.",
  "Night shift? Let's get through it.",
  "Late night? Let's talk.",
];

// LocalStorage key to persist greeting state across sessions
const STORAGE_KEY = "chatbot_greeting_data";
// Version number to invalidate old greeting data when logic changes
const GREETING_VERSION = "12"; // 12: Instructor Assistant wording
const SPECIAL_DAY_GREETING_EXPIRY_HOUR = 17;

type TimePeriod = "morning" | "afternoon" | "evening" | "after_hours";

const getTimePeriod = (): TimePeriod => {
  const hour = new Date().getHours();
  if (hour >= 5 && hour < 12) {
    return "morning";
  } else if (hour >= 12 && hour < 18) {
    return "afternoon";
  } else if (hour >= 18 && hour < 22) {
    return "evening";
  }
  return "after_hours";
};

// Returns appropriate greeting based on current time of day, localized.
const getTimeBasedGreeting = (period = getTimePeriod()) => {
  const lang = resolveUiLanguage();
  const strings = getChromeStrings(lang);
  if (period === "after_hours") return strings.greetingAfterHours;
  if (period === "morning") return strings.greetingMorning;
  if (period === "afternoon") return strings.greetingAfternoon;
  return strings.greetingEvening;
};

const getCasualGreetings = (period: TimePeriod) => {
  if (period === "after_hours") {
    return [...WARM_TEXTS, ...AFTER_HOURS_TEXTS];
  }
  // morning / afternoon / evening also get a time-aware casual phrase,
  // e.g. "How can I help you this morning?".
  return [...WARM_TEXTS, `How can I help you this ${period}?`];
};

// Returns a day-specific greeting when one should be emphasized.
const getSpecialDayGreeting = () => {
  const now = new Date();
  if (now.getHours() >= SPECIAL_DAY_GREETING_EXPIRY_HOUR) {
    return null;
  }

  // First day of the month — a high-occurrence celebratory greeting that
  // takes precedence over the weekly day-of-week specials.
  if (now.getDate() === 1 && Math.random() < 0.9) {
    return "Happy New Month!";
  }

  const day = now.getDay();
  const greetingsByDay: Partial<Record<number, string[]>> = {
    0: ["Happy Sunday!", "Happy Weekend!"],
    4: ["Happy Thursday!"],
    6: ["Happy Weekend!"],
  };
  const greetings = greetingsByDay[day];

  if (!greetings || Math.random() >= 0.7) {
    return null;
  }

  return greetings[Math.floor(Math.random() * greetings.length)];
};

const isSpecialDayGreeting = (value?: string) => {
  return /^Happy (Sunday|Thursday|Weekend|New Month)!$/i.test(value || "");
};

const isSpecialDayGreetingExpired = (value?: string) => {
  return (
    isSpecialDayGreeting(value) &&
    new Date().getHours() >= SPECIAL_DAY_GREETING_EXPIRY_HOUR
  );
};

const getMillisecondsUntilSpecialGreetingExpiry = () => {
  const now = new Date();
  const expiry = new Date(now);
  expiry.setHours(SPECIAL_DAY_GREETING_EXPIRY_HOUR, 0, 0, 0);

  return expiry.getTime() - now.getTime();
};

export default function Greeting() {
  const [greeting, setGreeting] = useState<string>("");
  // Track if component has mounted to prevent hydration mismatch
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);

    // Determines if enough time has passed to show a new greeting
    // Uses a random interval between 30 minutes and 2 hours to keep greetings fresh
    const shouldUpdateGreeting = (lastUpdated: number): boolean => {
      const now = Date.now();
      const timeDiff = now - lastUpdated;
      const minInterval = 30 * 60 * 1000; // 30 minutes
      const maxInterval = 120 * 60 * 1000; // 2 hours
      const randomInterval =
        Math.random() * (maxInterval - minInterval) + minInterval;
      return timeDiff > randomInterval;
    };

    // Main logic to select and display the appropriate greeting
    const selectGreeting = () => {
      try {
        const stored = localStorage.getItem(STORAGE_KEY);
        const now = Date.now();
        const currentTimePeriod = getTimePeriod();
        const currentTimeGreeting = getTimeBasedGreeting(currentTimePeriod);

        // Non-English handling. English-only WARM_TEXTS / day-specific
        // specials stay English by design. For es/pt (reviewed-native
        // markets) we ship a SMALL localized casual pool so those users
        // get warmth/variety too: a simple coin-flip between the
        // time-of-day phrase and a random casual one. Other non-English
        // locales (fr/it/ja/ko/zh/tl) have an empty casual pool and stay
        // time-of-day only.
        const lang = resolveUiLanguage();
        if (lang !== "en") {
          const casualPool = getChromeStrings(lang).casualGreetings;
          if (casualPool.length > 0) {
            const useTimeGreeting = Math.random() < 0.5;
            if (useTimeGreeting) {
              setGreeting(currentTimeGreeting);
            } else {
              const randomIndex = Math.floor(Math.random() * casualPool.length);
              setGreeting(casualPool[randomIndex]);
            }
          } else {
            setGreeting(currentTimeGreeting);
          }
          return;
        }
        let storedGreetingData: {
          greeting?: string;
          lastUpdated?: number;
          timePeriod?: TimePeriod;
          version?: string;
        } | null = null;

        if (stored) {
          storedGreetingData = JSON.parse(stored);

          // Clear old data if version has changed
          if (storedGreetingData?.version !== GREETING_VERSION) {
            localStorage.removeItem(STORAGE_KEY);
            storedGreetingData = null;
          } else {
            const isSameTimePeriod =
              storedGreetingData.timePeriod === currentTimePeriod;
            const lastUpdated = storedGreetingData.lastUpdated ?? 0;
            if (
              isSameTimePeriod &&
              !isSpecialDayGreetingExpired(storedGreetingData.greeting) &&
              !shouldUpdateGreeting(lastUpdated)
            ) {
              setGreeting(storedGreetingData.greeting || currentTimeGreeting);
              return;
            }
          }
        }

        let newGreeting: string;
        if (
          !storedGreetingData ||
          storedGreetingData.timePeriod !== currentTimePeriod
        ) {
          // First visit - use time greeting, but check for day-specific specials.
          // After hours is the exception: its time greeting is a single fixed
          // string, so a first visit (and every time-period change) showed the
          // SAME line, and the 30min-2hr persistence held it there. Draw from
          // the rotating night pool instead so late-night visitors see variety.
          if (currentTimePeriod === "after_hours") {
            const nightPool = getCasualGreetings(currentTimePeriod);
            newGreeting =
              getSpecialDayGreeting() ||
              nightPool[Math.floor(Math.random() * nightPool.length)];
          } else {
            newGreeting = getSpecialDayGreeting() || currentTimeGreeting;
          }
        } else {
          // Subsequent visits - vary the greeting
          // 70% chance of a day-specific greeting on configured days.
          const specialDayGreeting = getSpecialDayGreeting();
          if (specialDayGreeting) {
            newGreeting = specialDayGreeting;
          } else {
            // 50/50 split between time-based and casual greetings
            const useTimeGreeting = Math.random() < 0.4;
            if (useTimeGreeting) {
              newGreeting = currentTimeGreeting;
            } else {
              // Pick a random casual greeting, including night-only options after hours.
              const greetings = getCasualGreetings(currentTimePeriod);
              const randomIndex = Math.floor(Math.random() * greetings.length);
              newGreeting = greetings[randomIndex];
            }
          }
        }

        // Save the selected greeting to localStorage with timestamp
        localStorage.setItem(
          STORAGE_KEY,
          JSON.stringify({
            greeting: newGreeting,
            lastUpdated: now,
            timePeriod: currentTimePeriod,
            version: GREETING_VERSION,
          }),
        );

        setGreeting(newGreeting);
      } catch (error) {
        // Fallback to time-based greeting if localStorage fails
        setGreeting(getTimeBasedGreeting());
      }
    };

    selectGreeting();
    const specialGreetingExpiryTimeout =
      getMillisecondsUntilSpecialGreetingExpiry();
    const expiryTimer =
      specialGreetingExpiryTimeout > 0
        ? window.setTimeout(selectGreeting, specialGreetingExpiryTimeout)
        : null;

    // Re-select when the user picks a language from SettingsMenu so the
    // greeting flips to the new locale's time-based phrase immediately.
    const onLangChange = () => selectGreeting();
    window.addEventListener("user-language-pref-changed", onLangChange);
    return () => {
      if (expiryTimer !== null) {
        window.clearTimeout(expiryTimer);
      }
      window.removeEventListener("user-language-pref-changed", onLangChange);
    };
  }, []);

  // Prevent hydration mismatch by not rendering greeting until component mounts on client-side
  // This ensures server-rendered HTML matches client-rendered HTML
  const sub = getChromeStrings(resolveUiLanguage()).greetingSub;

  // Crimson Pro 600 (direction D). An h2: the header holds the page's h1.
  // Rendered invisible until mounted so server and client HTML match.
  return (
    <div className="flex flex-col">
      <h2
        className={`m-0 font-display text-[26px] font-semibold leading-[1.2] text-ia-text sm:text-[32px] ${mounted ? "" : "invisible"}`}
      >
        {mounted ? greeting : "Loading..."}
      </h2>
      <p className="mt-1 text-base leading-normal text-ia-text">{sub}</p>
    </div>
  );
}
