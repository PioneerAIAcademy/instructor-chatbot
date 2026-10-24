import { useEffect, useRef, useState } from "react";

/**
 * Throttle a fast-changing value to at most one update per `intervalMs`,
 * with a guaranteed trailing flush, and an instant bypass.
 *
 * Streaming-jank fix (2026-06-12): the backend streams one character per SSE
 * event (~55 updates/s) and every update re-rendered the streaming message's
 * whole subtree. CPU-profiling the freeze showed ~50% of all time in React
 * element creation alone (jsxDEV/createElement) — render FREQUENCY, not the
 * markdown parse, was the dominant cost. Feeding the messages list through
 * this throttle renders the heavy subtree ~11×/s instead of 55×/s while the
 * typewriter still advances every flush (~5 chars per group).
 *
 * `bypass` (set when the stream is NOT active) returns the live value
 * untouched and resets the flush clock, so the user's own message appears
 * instantly on submit and the final answer settles instantly on stream end.
 */
export function useThrottledValue<T>(
  value: T,
  intervalMs: number,
  bypass: boolean,
): T {
  const [throttled, setThrottled] = useState(value);
  const latestRef = useRef(value);
  const lastFlushRef = useRef(0);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  latestRef.current = value;

  useEffect(() => {
    if (bypass) {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
        timerRef.current = null;
      }
      lastFlushRef.current = 0;
      setThrottled(value);
      return;
    }
    const now = Date.now();
    const elapsed = now - lastFlushRef.current;
    if (elapsed >= intervalMs) {
      lastFlushRef.current = now;
      setThrottled(value);
      return;
    }
    if (!timerRef.current) {
      timerRef.current = setTimeout(() => {
        timerRef.current = null;
        lastFlushRef.current = Date.now();
        setThrottled(latestRef.current);
      }, intervalMs - elapsed);
    }
  }, [value, bypass, intervalMs]);

  useEffect(
    () => () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    },
    [],
  );

  return bypass ? value : throttled;
}
