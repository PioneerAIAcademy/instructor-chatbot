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
            "p-0 h-9 w-9 rounded-full",
            "hover:bg-white/15 focus-visible:ring-2 focus-visible:ring-white",
            "transition-colors",
            isOpen ? "bg-white/15" : "",
          ].join(" ")}
        >
          <Settings
            className={[
              "h-5 w-5 text-white",
              "transition-transform duration-200 ease-out",
              isOpen ? "rotate-90" : "rotate-0",
            ].join(" ")}
          />
        </Button>
        </Tooltip>

        {isOpen && (
          <div
            className={[
              "absolute right-0 top-11",
              "w-[248px]",
              "rounded-2xl",
              "border border-black/10 dark:border-white/10",
              "ring-1 ring-black/5 dark:ring-white/5",
              "bg-[#FFFEFA]/95 dark:bg-[#0E0F10]/95 backdrop-blur-md",
              "shadow-[0_18px_48px_rgba(0,0,0,0.16)] dark:shadow-[0_18px_60px_rgba(0,0,0,0.62)]",
              "p-2.5",
              "z-[9999] pointer-events-auto origin-top-right",
              "animate-in fade-in zoom-in-95 duration-150",
            ].join(" ")}
            onClick={(e) => e.stopPropagation()}
            onMouseDown={(e) => e.stopPropagation()}
          >
            {/* Theme */}
            <div className="px-1 pb-2.5">
              <h3 className="text-[10px] font-semibold tracking-wide text-[#454540] dark:text-white/80 mb-1.5">
                {strings.settingsTheme}
              </h3>
              <div className="grid grid-cols-3 gap-1 rounded-xl border border-black/10 dark:border-white/10 bg-black/[0.035] dark:bg-white/5 p-1">
                <Tooltip label={strings.themeLight} side="bottom" align="start" className="w-full">
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleThemeChange("light");
                  }}
                  aria-label={strings.themeLight}
                  className={[
                    "h-9 w-full rounded-lg flex items-center justify-center",
                    "transition-colors",
                    "text-[#646362] dark:text-white/70",
                    "hover:bg-black/5 dark:hover:bg-white/10",
                    theme === "light"
                      ? "bg-[#056CB6]/20 text-[#3D3D3A] dark:bg-white/10 dark:text-white shadow-[0_1px_0_rgba(0,0,0,0.06)]"
                      : "",
                  ].join(" ")}
                >
                  <Sun className="h-4 w-4" />
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
                    "h-9 w-full rounded-lg flex items-center justify-center",
                    "transition-colors",
                    "text-[#646362] dark:text-white/70",
                    "hover:bg-black/5 dark:hover:bg-white/10",
                    theme === "dark"
                      ? "bg-[#056CB6]/20 text-[#3D3D3A] dark:bg-white/10 dark:text-white shadow-[0_1px_0_rgba(0,0,0,0.06)]"
                      : "",
                  ].join(" ")}
                >
                  <Moon className="h-4 w-4" />
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
                    "h-9 w-full rounded-lg flex items-center justify-center",
                    "transition-colors",
                    "text-[#646362] dark:text-white/70",
                    "hover:bg-black/5 dark:hover:bg-white/10",
                    theme === "system"
                      ? "bg-[#056CB6]/20 text-[#3D3D3A] dark:bg-white/10 dark:text-white shadow-[0_1px_0_rgba(0,0,0,0.06)]"
                      : "",
                  ].join(" ")}
                >
                  <Monitor className="h-4 w-4" />
                </button>
                </Tooltip>
              </div>
            </div>

            <div className="my-2 h-px bg-black/10 dark:bg-white/10" />

            {/* Language */}
            <div className="px-1 pb-2.5">
              <div className="flex items-center gap-2 mb-1.5">
                <Globe className="h-3.5 w-3.5 text-[#646362] dark:text-white/70" />
                <h3 className="text-[10px] font-semibold tracking-wide text-[#454540] dark:text-white/80">
                  {strings.settingsLanguage}
                </h3>
              </div>
              <div
                role="listbox"
                aria-label={strings.settingsLanguage}
                className="max-h-[208px] overflow-y-auto rounded-xl border border-black/10 bg-black/[0.035] p-1 [scrollbar-color:rgba(61,61,58,0.28)_transparent] [scrollbar-width:thin] [&::-webkit-scrollbar]:w-1 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-black/25 hover:[&::-webkit-scrollbar-thumb]:bg-black/35 dark:border-white/10 dark:bg-white/5 dark:[scrollbar-color:rgba(255,255,255,0.38)_transparent] dark:[&::-webkit-scrollbar-thumb]:bg-white/40 dark:hover:[&::-webkit-scrollbar-thumb]:bg-white/55"
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
                        "w-full text-left rounded-lg px-2 py-1.5 text-sm",
                        "transition-colors",
                        "text-[#3D3D3A] dark:text-white/85",
                        "hover:bg-black/5 dark:hover:bg-white/10",
                        isSelected
                          ? "bg-[#056CB6]/20 dark:bg-white/10 font-medium"
                          : "",
                      ].join(" ")}
                    >
                      {label}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="my-2 h-px bg-black/10 dark:bg-white/10" />

            {/* Help (only when NEXT_PUBLIC_HELP_URL is set) */}
            {helpUrl && (
              <>
              <a
                href={helpUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="group flex items-center gap-3 rounded-xl px-2 py-2 text-sm font-medium text-[#3D3D3A] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                onClick={(e) => {
                  e.stopPropagation();
                }}
              >
                <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-black/5 dark:bg-white/10 group-hover:bg-[#056CB6]/15 dark:group-hover:bg-[#056CB6]/30 transition-colors">
                  <HelpCircle className="h-4 w-4 text-[#646362] dark:text-white/70 group-hover:text-[#3D3D3A] dark:group-hover:text-white transition-colors" />
                </span>
                <span>{strings.settingsHelp}</span>
              </a>
              <div className="my-2 h-px bg-black/10 dark:bg-white/10" />
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
              className="group w-full flex items-center gap-3 rounded-xl px-2 py-2 text-sm font-medium text-[#3D3D3A] dark:text-white hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
            >
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-black/5 dark:bg-white/10 group-hover:bg-[#056CB6]/15 dark:group-hover:bg-[#056CB6]/30 transition-colors">
                <MessageSquare className="h-4 w-4 text-[#E18158]" />
              </span>
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
