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
                --error-bg: #FAF9F5;
                --error-text: #141413;
                --error-muted: #646362;
                --error-button-bg: #141413;
                --error-button-text: #FFFFFF;
                --error-button-hover: #2D2D2A;
                --error-header-shadow: rgba(0, 0, 0, 0.18);
              }

              :root.dark {
                color-scheme: dark;
                --error-bg: #222320;
                --error-text: #E6E4DA;
                --error-muted: #C2C0B6;
                --error-button-bg: #056CB6;
                --error-button-text: #FFFFFF;
                --error-button-hover: #0F4B8F;
                --error-header-shadow: rgba(0, 0, 0, 0.55);
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
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
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
                background: #056CB6;
                box-shadow: 0 1px 3px var(--error-header-shadow);
              }

              .global-error-logo-link {
                position: absolute;
                left: 24px;
                display: inline-flex;
                align-items: center;
              }

              .global-error-logo {
                width: 198px;
                max-width: 38vw;
                height: auto;
                display: block;
              }

              .global-error-title {
                margin: 0;
                color: #454540;
                font-size: 20px;
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
                min-height: 46px;
                border: 0;
                border-radius: 8px;
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
                outline: 3px solid rgba(5, 108, 182, 0.6);
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
