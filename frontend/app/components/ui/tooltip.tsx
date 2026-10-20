"use client";

import { ReactNode, useCallback, useEffect, useRef, useState } from "react";

const MOBILE_HOLD_DELAY_MS = 500;

/**
 * Styled tooltip — a rounded dark pill that fades in on hover/focus, replacing
 * the browser-default `title` rectangle (ChatGPT-style). Wrap any control:
 *
 *   <Tooltip label="Settings"><button …/></Tooltip>
 *
 * Notes:
 * - Renders a `group/tooltip relative inline-flex` wrapper; pass layout classes
 *   (e.g. "flex-shrink-0") via `className` when the wrapped control needs them.
 *   The group is NAMED (`/tooltip`) on purpose: an unnamed `group` would also be
 *   triggered by any ancestor `.group` (e.g. a chat-message bubble that reveals
 *   its action icons on `group-hover`), so the pill would wrongly show when you
 *   hover the whole bubble. The named group scopes the reveal to THIS control only.
 * - `side` controls placement: "top" (default, for bottom-of-screen controls
 *   like the chat input) or "bottom" (for top-of-screen controls like the
 *   header gear).
 * - The pill is `pointer-events-none` + `z-50` so it never blocks clicks and
 *   layers above siblings. Shown on group-hover AND group-focus-within (keyboard).
 *   Also `select-none`: tooltips are ephemeral chrome — Ctrl+A/copy must never
 *   grab their text (and selection styling must never paint inside the pill).
 * - The wrapped control should keep its `aria-label` for screen readers; this
 *   tooltip is presentational (the `title` attribute should be removed).
 */
export function Tooltip({
  label,
  side = "top",
  align = "center",
  className = "",
  children,
}: {
  label: string;
  side?: "top" | "bottom";
  align?: "center" | "start" | "end";
  className?: string;
  children: ReactNode;
}) {
  const [isTouchDevice, setIsTouchDevice] = useState(false);
  const [isTouchOpen, setIsTouchOpen] = useState(false);
  const touchTimerRef = useRef<number | null>(null);
  const wrapperRef = useRef<HTMLSpanElement | null>(null);

  useEffect(() => {
    setIsTouchDevice(
      window.matchMedia?.("(hover: none) and (pointer: coarse)")?.matches ??
        false,
    );
  }, []);

  const clearTouchTimer = useCallback(() => {
    if (touchTimerRef.current != null) {
      window.clearTimeout(touchTimerRef.current);
      touchTimerRef.current = null;
    }
  }, []);

  const hideTouchTooltip = useCallback(() => {
    clearTouchTimer();
    setIsTouchOpen(false);
  }, [clearTouchTimer]);

  useEffect(() => () => clearTouchTimer(), [clearTouchTimer]);

  useEffect(() => {
    if (!isTouchDevice || !isTouchOpen) return;
    const handleOutsideTap = (event: PointerEvent) => {
      if (
        wrapperRef.current &&
        !wrapperRef.current.contains(event.target as Node)
      ) {
        hideTouchTooltip();
      }
    };
    document.addEventListener("pointerdown", handleOutsideTap);
    return () => document.removeEventListener("pointerdown", handleOutsideTap);
  }, [isTouchDevice, isTouchOpen, hideTouchTooltip]);

  const handleTouchStart = useCallback(() => {
    if (!isTouchDevice) return;

    clearTouchTimer();
    if (isTouchOpen) {
      hideTouchTooltip();
      return;
    }
    touchTimerRef.current = window.setTimeout(() => {
      setIsTouchOpen(true);
      touchTimerRef.current = null;
    }, MOBILE_HOLD_DELAY_MS);
  }, [clearTouchTimer, hideTouchTooltip, isTouchOpen, isTouchDevice]);

  const handleTouchCancel = useCallback(() => {
    if (!isTouchDevice) return;
    clearTouchTimer();
  }, [clearTouchTimer, isTouchDevice]);

  const tooltipVisibilityClasses = isTouchDevice
    ? "transition-opacity duration-150"
    : "opacity-0 transition-opacity duration-150 group-hover/tooltip:opacity-100 group-focus-within/tooltip:opacity-100";

  const pos = side === "bottom" ? "top-full mt-2" : "bottom-full mb-2";
  const alignCls =
    align === "start"
      ? "left-0"
      : align === "end"
        ? "right-0"
        : "left-1/2 -translate-x-1/2";
  return (
    <span
      ref={wrapperRef}
      className={`group/tooltip relative inline-flex ${className}`}
      onPointerDown={handleTouchStart}
      onPointerCancel={handleTouchCancel}
      onPointerLeave={handleTouchCancel}
    >
      {children}
      <span
        role="tooltip"
        data-mobile-open={isTouchOpen ? "true" : "false"}
        style={isTouchDevice ? { opacity: isTouchOpen ? 1 : 0 } : undefined}
        className={`pointer-events-none select-none absolute ${pos} ${alignCls} z-50 whitespace-nowrap rounded-lg bg-ia-gray-4 px-2.5 py-1.5 text-xs font-semibold text-white shadow-ia-pop dark:border dark:border-ia-gray-3 ${tooltipVisibilityClasses}`}
      >
        {label}
      </span>
    </span>
  );
}
