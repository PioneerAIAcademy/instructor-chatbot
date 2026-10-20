"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { Check, X } from "lucide-react";

export type ToastType = "info" | "success" | "error";

interface ToastProps {
  message: string;
  show: boolean;
  type?: ToastType;
  onClose: () => void;
}

export function Toast({ message, show, type = "info", onClose }: ToastProps) {
  const [mounted, setMounted] = useState(show);
  const [portalRoot, setPortalRoot] = useState<HTMLElement | null>(null);

  // Prototype .toast: Gray 4 with white text; the icon carries the status
  // (green check, red cross) next to the words, never color alone.
  const tintClass = "bg-ia-gray-4 border-transparent dark:border-ia-gray-3";

  useEffect(() => {
    setPortalRoot(document.body);
  }, []);

  useEffect(() => {
    if (show) {
      const timer = setTimeout(() => {
        onClose();
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [show, onClose]);

  useEffect(() => {
    if (show) {
      setMounted(true);
      return;
    }

    // Allow exit transition to play before unmounting.
    const timer = setTimeout(() => setMounted(false), 260);
    return () => clearTimeout(timer);
  }, [show]);

  if (!mounted || !portalRoot) return null;

  const toastContent = (
    <div
      className={[
        "fixed left-1/2 -translate-x-1/2 z-[10000]",
        "top-4 sm:top-16",
        "w-auto max-w-[280px] sm:max-w-sm",
        "mx-4",
        "transition-[opacity,transform] duration-300 ease-out",
        show ? "opacity-100 translate-y-0" : "opacity-0 -translate-y-2",
      ].join(" ")}
      role="status"
      aria-live="polite"
    >
      <div
        className={[
          "relative overflow-hidden",
          "flex items-center gap-2.5 rounded-xl px-[18px] py-3.5 border",
          "text-white shadow-ia-pop",
          tintClass,
        ].join(" ")}
      >
        {type === "success" && <Check aria-hidden="true" className="h-4 w-4 text-ia-green-3 flex-shrink-0" />}
        {type === "error" && <X aria-hidden="true" className="h-4 w-4 text-ia-red-3 flex-shrink-0" />}
        <p className="text-sm font-semibold">{message}</p>
      </div>
    </div>
  );

  return createPortal(toastContent, portalRoot);
}

export function useToast() {
  const [show, setShow] = useState(false);
  const [message, setMessage] = useState("");
  const [type, setType] = useState<ToastType>("info");

  const showToast = (msg: string, toastType: ToastType = "info") => {
    setMessage(msg);
    setType(toastType);
    setShow(true);
  };

  const hideToast = () => {
    setShow(false);
  };

  return { show, message, type, showToast, hideToast };
}
