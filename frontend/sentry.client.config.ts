import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,

  // Only enable Sentry when DSN is configured (prevents noise in dev)
  enabled: !!process.env.NEXT_PUBLIC_SENTRY_DSN,

  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? "production",

  // Capture 10% of transactions for performance monitoring
  tracesSampleRate: 0.1,

  // Replay: only on errors (no continuous sampling) to cap quota usage.
  // Privacy: mask all DOM text + block media so chat content never leaves the browser.
  replaysOnErrorSampleRate: 1.0,
  replaysSessionSampleRate: 0,

  integrations: [
    Sentry.replayIntegration({
      maskAllText: true,
      blockAllMedia: true,
    }),
  ],
});
