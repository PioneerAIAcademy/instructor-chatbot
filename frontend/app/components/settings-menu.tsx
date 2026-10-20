"use client";

import {
  Globe,
  HelpCircle,
  MessageSquare,
  Monitor,
  Moon,
  Settings,
  Sun,
} from "lucide-react";
import { useTheme } from "next-themes";
import * as React from "react";

import { getChromeStrings } from "../lib/chrome-strings";
import { Tooltip } from "./ui/tooltip";
import {
  LANG_LABELS,
  SUPPORTED_LANGS,
  resolveUiLanguage,
  setUserLanguagePref,
  type LangPref,
} from "../lib/i18n";
import { GeneralFeedbackDrawer } from "./general-feedback-drawer";
import { Button } from "./ui/button";

// A menu row (prototype .menu-row): 44px minimum, Gray 4 text, Blue 1 hover.
const MENU_ROW =
  "flex min-h-[44px] items-center gap-2.5 rounded-lg px-3 text-sm font-semibold text-ia-text transition-colors " +
  "hover:bg-ia-blue-1 hover:text-ia-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ia-focus";

export function SettingsMenu() {
  const [isOpen, setIsOpen] = React.useState(false);
  const [isFeedbackOpen, setIsFeedbackOpen] = React.useState(false);
  const [uiLang, setUiLang] =
    React.useState<ReturnType<typeof resolveUiLanguage>>("en");
  const { theme, setTheme, resolvedTheme: currentResolvedTheme } = useTheme();
  // The instructor help page. Hidden until one is configured: upstream's
  // link is the other assistant's guide.
  const helpUrl = process.env.NEXT_PUBLIC_HELP_URL?.trim() || "";

  // Hydrate language state on client only — resolveUiLanguage reads
  // localStorage + navigator.language so it must run after mount to
  // avoid SSR mismatches.
  React.useEffect(() => {
    setUiLang(resolveUiLanguage());
  }, []);

  const handleLanguageChange = (newPref: LangPref) => {
    setUserLanguagePref(newPref);
    setUiLang(resolveUiLanguage());
    // Notify other components on the same tab (chat-section reads the
    // same key when composing each chat request body).
    window.dispatchEvent(
      new CustomEvent("user-language-pref-changed", { detail: newPref }),
    );
    setIsOpen(false);
  };

  const strings = getChromeStrings(uiLang);

  const handleToggle = () => {
    setIsOpen((v) => !v);
  };

  const handleThemeChange = (newTheme: string) => {
    const prefersReducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

    const root = document.documentElement;

    if (theme === newTheme) {
      setIsOpen(false);
      return;
    }

    const resolvedTheme =
      newTheme === "system"
        ? window.matchMedia?.("(prefers-color-scheme: dark)")?.matches
          ? "dark"
          : "light"
        : newTheme;

    const isAlreadyInResolvedTheme =
      currentResolvedTheme === resolvedTheme ||
      root.classList.contains(resolvedTheme) ||
      (resolvedTheme === "dark"
        ? root.classList.contains("dark")
        : root.classList.contains("light"));

    if (isAlreadyInResolvedTheme) {
      root.classList.remove("light", "dark", "system");
      root.classList.add(resolvedTheme);
      setTheme(newTheme);
      setIsOpen(false);
      return;
    }

    const doc = document as unknown as {
      startViewTransition?: (updateCallback: () => void | Promise<void>) => {
        finished?: Promise<unknown>;
      };
    };

    if (
      !prefersReducedMotion &&
      typeof doc.startViewTransition === "function"
    ) {
      root.classList.add("theme-view-transition");
      try {
        const viewTransition = doc.startViewTransition(() => {
          root.classList.remove("light", "dark", "system");
          root.classList.add(resolvedTheme);
          setTheme(newTheme);
        });
        viewTransition?.finished?.finally?.(() => {
          root.classList.remove("theme-view-transition");
        });
        setIsOpen(false);
        return;
      } catch {
        root.classList.remove("theme-view-transition");
      }
    }

    root.classList.add("theme-color-transition");
    root.classList.remove("light", "dark", "system");
    root.classList.add(resolvedTheme);
    setTheme(newTheme);

    const durationMs = (() => {
      if (prefersReducedMotion) return 0;
      const raw = getComputedStyle(root)
        .getPropertyValue("--theme-transition-duration")
        .trim();
      const msMatch = raw.match(/^([0-9.]+)ms$/);
      if (msMatch) return Number(msMatch[1]);
      const sMatch = raw.match(/^([0-9.]+)s$/);
      if (sMatch) return Number(sMatch[1]) * 1000;
      const numMatch = raw.match(/^([0-9.]+)$/);
      if (numMatch) return Number(numMatch[1]);
      return 1200;
    })();

    window.setTimeout(() => {
      root.classList.remove("theme-color-transition");
    }, durationMs + 50);

    setIsOpen(false);
  };

  const openFeedback = () => {
    setIsOpen(false);
    setIsFeedbackOpen(true);
  };

  // Close dropdown when clicking outside.
  React.useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as HTMLElement;
      if (isOpen && !target.closest(".settings-menu-container")) {
        setIsOpen(false);
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen]);

  return (
    <>
      <div className="settings-menu-container relative flex items-center">
        <Tooltip label={strings.settingsTitle} side="bottom" align="end">
        <Button
          variant="ghost"
          size="icon"
          onClick={handleToggle}
          aria-haspopup="menu"
          aria-expanded={isOpen}
          aria-label={strings.settingsTitle}
          className={[
            "p-0 h-11 w-11 rounded-full text-ia-header-text",
            "hover:bg-ia-blue-1 dark:hover:bg-ia-gray-3",
            "transition-colors",
            "focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-header-bg",
            isOpen ? "bg-ia-blue-1 dark:bg-ia-gray-3" : "",
          ].join(" ")}
        >
          <Settings
            aria-hidden="true"
            className={[
              "h-[22px] w-[22px]",
              "transition-transform duration-200 ease-out",
              isOpen ? "rotate-90" : "rotate-0",
            ].join(" ")}
          />
        </Button>
        </Tooltip>

        {isOpen && (
          <div
            className={[
              "absolute right-0 top-12",
              "w-[308px] max-w-[calc(100vw-32px)]",
              "rounded-xl",
              "border border-ia-border",
              "bg-ia-surface text-ia-text shadow-ia-pop",
              "p-2",
              "z-[9999] pointer-events-auto origin-top-right",
              "animate-in fade-in zoom-in-95 duration-150",
            ].join(" ")}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Theme */}
            <div className="px-1 pb-2.5">
              <h3 className="mb-1.5 px-1 pt-1 text-[13px] font-semibold text-ia-text">
                {strings.settingsTheme}
              </h3>
              <div className="grid grid-cols-3 overflow-hidden rounded-full border border-ia-border">
                <Tooltip label={strings.themeLight} side="bottom" align="start" className="w-full">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleThemeChange("light");
                  }}
                  aria-label={strings.themeLight}
                  className={[
                    "h-11 w-full flex items-center justify-center",
                    "transition-colors text-ia-text",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ia-focus",
                    theme === "light"
                      ? "bg-ia-blue-4 text-white"
                      : "hover:bg-ia-blue-1 hover:text-ia-gray-4",
                  ].join(" ")}
                >
                  <Sun aria-hidden="true" className="h-4 w-4" />
                </button>
                </Tooltip>
                <Tooltip label={strings.themeDark} side="bottom" align="center" className="w-full">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleThemeChange("dark");
                  }}
                  aria-label={strings.themeDark}
                  className={[
                    "h-11 w-full flex items-center justify-center",
                    "transition-colors text-ia-text",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ia-focus",
                    theme === "dark"
                      ? "bg-ia-blue-4 text-white"
                      : "hover:bg-ia-blue-1 hover:text-ia-gray-4",
                  ].join(" ")}
                >
                  <Moon aria-hidden="true" className="h-4 w-4" />
                </button>
                </Tooltip>
                <Tooltip label={strings.themeSystem} side="bottom" align="end" className="w-full">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleThemeChange("system");
                  }}
                  aria-label={strings.themeSystem}
                  className={[
                    "h-11 w-full flex items-center justify-center",
                    "transition-colors text-ia-text",
                    "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ia-focus",
                    theme === "system"
                      ? "bg-ia-blue-4 text-white"
                      : "hover:bg-ia-blue-1 hover:text-ia-gray-4",
                  ].join(" ")}
                >
                  <Monitor aria-hidden="true" className="h-4 w-4" />
                </button>
                </Tooltip>
              </div>
            </div>

            <div className="mx-1 my-1.5 h-px bg-ia-border" />

            {/* Language */}
            <div className="px-1 pb-2.5">
              <div className="flex items-center gap-2 mb-1.5">
                <Globe aria-hidden="true" className="h-4 w-4 text-ia-text" />
                <h3 className="text-[13px] font-semibold text-ia-text">
                  {strings.settingsLanguage}
                </h3>
              </div>
              <div
                role="listbox"
                aria-label={strings.settingsLanguage}
                className="max-h-[208px] overflow-y-auto rounded-lg border border-ia-border p-1 [scrollbar-width:thin] [scrollbar-color:var(--ia-gray-3)_transparent]"
              >
                {/* "Auto" row hidden per Claude.ai pattern — when no
                    pref is set, the cascade (navigator.language +
                    backend geo-IP) still resolves the right language;
                    we just don't expose "Auto" as an explicit row. The
                    checkmark follows the RESOLVED language (uiLang) so
                    users see which language is currently active. */}
                {SUPPORTED_LANGS.map((code) => {
                  const isSelected = uiLang === code;
                  const label = LANG_LABELS[code].native;
                  return (
                    <button
                      key={code}
                      role="option"
                      aria-selected={isSelected}
                      onClick={(e) => {
                        e.preventDefault();
                        e.stopPropagation();
                        handleLanguageChange(code);
                      }}
                      className={[
                        "w-full min-h-[40px] text-left rounded-lg px-3 py-2 text-sm",
                        "transition-colors text-ia-text",
                        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-ia-focus",
                        isSelected
                          ? "bg-ia-blue-1 text-ia-gray-4 font-semibold"
                          : "hover:bg-ia-blue-1 hover:text-ia-gray-4",
                      ].join(" ")}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="mx-1 my-1.5 h-px bg-ia-border" />

            {/* Help (only when NEXT_PUBLIC_HELP_URL is set) */}
            {helpUrl && (
              <>
                <a
                  href={helpUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className={MENU_ROW}
                  onClick={(e) => {
                    e.stopPropagation();
                  }}
                >
                  <HelpCircle aria-hidden="true" className="h-[18px] w-[18px]" />
                  <span>{strings.settingsHelp}</span>
                </a>
                <div className="mx-1 my-1.5 h-px bg-ia-border" />
              </>
            )}

            {/* Send feedback */}
            <button
              type="button"
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                openFeedback();
              }}
              className={`${MENU_ROW} w-full`}
            >
              <MessageSquare aria-hidden="true" className="h-[18px] w-[18px]" />
              <span>{strings.settingsFeedback}</span>
            </button>
          </div>
        )}
      </div>

      <GeneralFeedbackDrawer
        isOpen={isFeedbackOpen}
        onClose={() => setIsFeedbackOpen(false)}
      />
    </>
  );
}
