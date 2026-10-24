// Custom 404 page. Required so `output: "export"` doesn't fall back to
// Next.js's auto-generated /_not-found, which during prerender pulls
// the global-error boundary and breaks the build under @sentry/nextjs
// (see app/global-error.tsx for the matching workaround).
export const dynamic = "force-static";

export default function NotFound() {
  return (
    <html>
      <body
        style={{
          margin: 0,
          minHeight: "100vh",
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontFamily:
            "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
          background: "#FAF9F5",
          color: "#141413",
        }}
      >
        <main style={{ textAlign: "center", padding: "2rem" }}>
          <h1 style={{ fontSize: "2rem", margin: 0 }}>404</h1>
          <p style={{ marginTop: "0.5rem", color: "#73726C" }}>
            That page could not be found.
          </p>
        </main>
      </body>
    </html>
  );
}
