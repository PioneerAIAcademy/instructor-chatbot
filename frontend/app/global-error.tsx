"use client";

/* eslint-disable @next/next/no-img-element -- Keep the global error boundary independent of Next Image runtime. */

import { useEffect, useState } from "react";

const themeBootstrapScript = `
  (function () {
    try {
      var stored = localStorage.getItem("theme");
      var preference = stored === "light" || stored === "dark" || stored === "system"
        ? stored
        : "system";
      var resolved = preference === "system"
        ? (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light")
        : preference;
      document.documentElement.classList.remove("light", "dark", "system");
      document.documentElement.classList.add(resolved);
      document.documentElement.dataset.themePreference = preference;
    } catch (error) {
      var fallback = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches
        ? "dark"
        : "light";
      document.documentElement.classList.remove("light", "dark", "system");
      document.documentElement.classList.add(fallback);
      document.documentElement.dataset.themePreference = "system";
    }
  })();
`;

type ResolvedTheme = "light" | "dark";

const resolveTheme = (): ResolvedTheme => {
  if (typeof window === "undefined") {
    return "light";
  }

  try {
    const stored = window.localStorage.getItem("theme");
    const preference =
      stored === "light" || stored === "dark" || stored === "system"
        ? stored
        : "system";

    if (preference === "light" || preference === "dark") {
      return preference;
    }

    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches
      ? "dark"
      : "light";
  } catch {
    return window.matchMedia?.("(prefers-color-scheme: dark)")?.matches
      ? "dark"
      : "light";
  }
};

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const [resolvedTheme, setResolvedTheme] =
    useState<ResolvedTheme>(resolveTheme);

  useEffect(() => {
    const applyTheme = () => {
      const nextTheme = resolveTheme();
      document.documentElement.classList.remove("light", "dark", "system");
      document.documentElement.classList.add(nextTheme);
      setResolvedTheme(nextTheme);
    };

    applyTheme();

    const mediaQuery = window.matchMedia?.("(prefers-color-scheme: dark)");
    mediaQuery?.addEventListener?.("change", applyTheme);
    window.addEventListener("storage", applyTheme);

    return () => {
      mediaQuery?.removeEventListener?.("change", applyTheme);
      window.removeEventListener("storage", applyTheme);
    };
  }, []);

  useEffect(() => {
    // Lazy-import Sentry so the module is not evaluated during the
    // static-export prerender. With output: "export", prerendering
    // /_not-found pulled @sentry/nextjs through this boundary and
    // webpack failed to resolve a chunk Sentry expects at runtime.
    void import("@sentry/nextjs")
      .then((Sentry) => {
        Sentry.captureException(error);
      })
      .catch(() => undefined);
  }, [error]);

  return (
    <html className={resolvedTheme} lang="en" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{ __html: themeBootstrapScript }} />
        <style
          dangerouslySetInnerHTML={{
            __html: `
              :root {
                color-scheme: light;
                /* Direction D (same palette as app/globals.css). This page
                   can't rely on the app's stylesheet, so it repeats it. */
                --error-bg: #FFFFFF;
                --error-text: #454540;
                --error-muted: #454540;
                --error-button-bg: #056CB6;
                --error-button-text: #FFFFFF;
                --error-button-hover: #0F4B8F;
                --error-header-bg: #FFFFFF;
                --error-header-text: #454540;
                --error-header-border: #E3E1DE;
                --error-logo-filter: none;
                --error-focus: #0F4B8F;
              }

              :root.dark {
                color-scheme: dark;
                --error-bg: #000000;
                --error-text: #E3E1DE;
                --error-muted: #E3E1DE;
                --error-button-bg: #056CB6;
                --error-button-text: #FFFFFF;
                --error-button-hover: #0F4B8F;
                --error-header-bg: #454540;
                --error-header-text: #E3E1DE;
                --error-header-border: #7E7A76;
                --error-logo-filter: brightness(0) invert(0.89);
                --error-focus: #FFC328;
              }

              * {
                box-sizing: border-box;
              }

              html,
              body {
                margin: 0;
                min-height: 100%;
              }

              body {
                background: var(--error-bg);
                color: var(--error-text);
                font-family: Mulish, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
              }

              .global-error-shell {
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                background: var(--error-bg);
                color: var(--error-text);
              }

              .global-error-header {
                width: 100%;
                min-height: 58px;
                flex-shrink: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                position: relative;
                padding: 10px 24px;
                background: var(--error-header-bg);
                border-bottom: 1px solid var(--error-header-border);
              }

              .global-error-logo-link {
                position: absolute;
                left: 24px;
                display: inline-flex;
                align-items: center;
              }

              .global-error-logo {
                width: 156px;
                max-width: 38vw;
                height: auto;
                display: block;
                filter: var(--error-logo-filter);
              }

              .global-error-title {
                margin: 0;
                color: var(--error-header-text);
                font-size: 18px;
                font-weight: 700;
                line-height: 1.2;
                text-align: center;
                white-space: nowrap;
              }

              .global-error-main {
                flex: 1;
                display: flex;
                align-items: center;
                justify-content: center;
                padding: 48px 24px;
              }

              .global-error-content {
                width: min(100%, 560px);
                text-align: center;
              }

              .global-error-eyebrow {
                margin: 0;
                color: var(--error-muted);
                font-size: 13px;
                font-weight: 800;
                letter-spacing: 0.08em;
                line-height: 1.2;
                text-transform: uppercase;
              }

              .global-error-heading {
                margin: 14px 0 0;
                color: var(--error-text);
                font-size: 34px;
                font-weight: 700;
                letter-spacing: 0;
                line-height: 1.15;
              }

              .global-error-copy {
                max-width: 460px;
                margin: 14px auto 0;
                color: var(--error-muted);
                font-size: 16px;
                line-height: 1.55;
              }

              .global-error-action {
                margin-top: 24px;
                min-height: 44px;
                border: 0;
                border-radius: 999px;
                background: var(--error-button-bg);
                color: var(--error-button-text);
                cursor: pointer;
                font: inherit;
                font-size: 15px;
                font-weight: 800;
                padding: 0 18px;
                transition:
                  background-color 160ms ease,
                  transform 160ms ease,
                  box-shadow 160ms ease;
              }

              .global-error-action:hover {
                background: var(--error-button-hover);
                transform: translateY(-1px);
                box-shadow: 0 10px 22px rgba(0, 0, 0, 0.14);
              }

              .global-error-action:active {
                transform: translateY(0);
              }

              .global-error-action:focus-visible {
                outline: 2px solid var(--error-focus);
                outline-offset: 3px;
              }

              @media (max-width: 640px) {
                .global-error-header {
                  min-height: 70px;
                  align-items: flex-end;
                  padding: 8px 16px 10px;
                }

                .global-error-logo-link {
                  left: 14px;
                  top: 8px;
                }

                .global-error-logo {
                  width: 142px;
                  max-width: 48vw;
                }

                .global-error-title {
                  font-size: 18px;
                }

                .global-error-main {
                  align-items: flex-start;
                  padding-top: 26vh;
                }

                .global-error-heading {
                  font-size: 29px;
                }

                .global-error-copy {
                  font-size: 15px;
                }
              }
            `,
          }}
        />
      </head>
      <body>
        <div className="global-error-shell">
          <header className="global-error-header">
            <a className="global-error-logo-link" href="/">
              <img
                alt="BYU-Pathway Worldwide"
                className="global-error-logo"
                src="/pathway-horizontal-logo.png"
              />
            </a>
            <h1 className="global-error-title">Instructor Assistant</h1>
          </header>

          <main className="global-error-main">
            <section
              className="global-error-content"
              aria-labelledby="error-title"
            >
              <p className="global-error-eyebrow">Instructor Assistant</p>
              <h2 className="global-error-heading" id="error-title">
                Something went wrong
              </h2>
              <p className="global-error-copy">
                Please try again. If this keeps happening, wait a few minutes
                and reload the page.
              </p>
              <button
                className="global-error-action"
                onClick={reset}
                type="button"
              >
                Try again
              </button>
            </section>
          </main>
        </div>
      </body>
    </html>
  );
}
