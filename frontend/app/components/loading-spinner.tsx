"use client";

import { useEffect, useState } from "react";

export default function LoadingSpinner() {
  return (
    <div role="status" className="fixed inset-0 flex items-center justify-center bg-ia-bg z-50">
      <div className="flex flex-col items-center gap-4">
        <div className="relative">
          <div aria-hidden="true" className="w-12 h-12 border-4 border-ia-gray-1 dark:border-ia-gray-4 border-t-ia-blue-4 rounded-full motion-safe:animate-spin"></div>
        </div>
        <p className="text-sm text-ia-text font-semibold">
          Loading...
        </p>
      </div>
    </div>
  );
}

export function AppLoader({ children }: { children: React.ReactNode }) {
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    // Wait for theme to be applied and components to be ready
    const timer = setTimeout(() => {
      setIsLoading(false);
    }, 800); // Minimum loading time to ensure smooth transition

    return () => clearTimeout(timer);
  }, []);

  if (isLoading) {
    return <LoadingSpinner />;
  }

  return <>{children}</>;
}