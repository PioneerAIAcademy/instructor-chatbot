"use client";

import { useEffect, useState } from "react";

// The opening screen: the app's name, with a blue band sweeping through the
// letters to the right and back to the left until the app is ready
// (globals.css, .loader-word). With reduced motion the name is simply blue.
export default function LoadingSpinner() {
  return (
    <div
      role="status"
      aria-label="Loading Instructor Assistant"
      className="fixed inset-0 z-50 flex items-center justify-center bg-[#FAF9F5] px-4 dark:bg-[#262624]"
    >
      <p
        aria-hidden="true"
        className="loader-word text-center text-[clamp(1.5rem,6vw,3rem)] font-extrabold uppercase leading-tight tracking-[0.12em]"
      >
        Instructor Assistant
      </p>
    </div>
  );
}

export function AppLoader({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Wait for theme to be applied and components to be ready
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 1000); // At least one sweep of the name, right and back (globals.css)

    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  return <>{children}</>;
}