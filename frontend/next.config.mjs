/** @type {import('next').NextConfig} */
import { withSentryConfig } from "@sentry/nextjs";
import fs from "fs";
import webpack from "./webpack.config.mjs";

const nextConfig = JSON.parse(fs.readFileSync("./next.config.json", "utf-8"));
nextConfig.webpack = webpack;

// A static export with no server code, so upstream's withLlamaIndex wrapper
// (for server-side LlamaIndex) isn't needed.
const configured = nextConfig;

// Next 15.5 enables the experimental segment explorer by default in dev.
// With this app's React 18 / webpack manifest path, Next's own
// SegmentViewNode client reference can fail to register as a named export.
configured.experimental = {
  ...(configured.experimental || {}),
  devtoolSegmentExplorer: false,
};

// Generate client-side source maps so the Sentry plugin has something to
// upload. Set explicitly so a release never uploads with zero artifacts
// (which leaves production stack traces minified).
configured.productionBrowserSourceMaps = true;

// LOCAL TUNNEL TESTING ONLY — enabled by DEV_PROXY_BACKEND.
// A phone cannot reach `localhost:8000`, and giving the backend its own public
// tunnel does not work either: the tunnel serves an HTML interstitial to
// browser requests, so `fetch` receives markup instead of JSON and the app
// hangs on its loading state. Proxying the API through this origin keeps
// everything on one host with one interstitial. Never set in production.
if (process.env.DEV_PROXY_BACKEND) {
  configured.rewrites = async () => [
    {
      source: "/api/:path*",
      destination: `${process.env.DEV_PROXY_BACKEND}/api/:path*`,
    },
  ];
}

export default withSentryConfig(configured, {
  // The Instructor Assistant's own Sentry project (CLAUDE.md §13 Q5), for
  // source map upload and release tagging. Without SENTRY_AUTH_TOKEN (and
  // these), the upload is skipped; only stack-trace readability suffers.
  org: process.env.SENTRY_ORG,
  project: process.env.SENTRY_PROJECT,
  // Suppress Sentry CLI output during local builds; keep verbose in CI.
  silent: !process.env.CI,
  // Disable Sentry's own telemetry pings.
  telemetry: false,
  // Source map upload reads SENTRY_AUTH_TOKEN from .env.sentry-build-plugin (gitignored)
  // locally, or from the build environment. Without a token, the upload step is skipped
  // silently — only stack-trace readability is degraded.
  authToken: process.env.SENTRY_AUTH_TOKEN,
  // Upload wider set of client source files for better stack trace resolution.
  widenClientFileUpload: true,
  // Delete generated source maps from the public bundle after upload so they
  // are not served to end users. Sentry keeps its own copy (indexed by debug
  // ID via artifact bundles) for stack-trace symbolication. Without this,
  // *.js.map files ship in the public `out/` static export.
  sourcemaps: { deleteSourcemapsAfterUpload: true },
});
