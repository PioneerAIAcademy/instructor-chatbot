"use client";

import { useEffect, useState } from "react";
import { useClientConfig } from "./use-config";

/**
 * The starter questions from `GET /api/v1/chat/config` (backend/API.md):
 * `{"starterQuestions": [...]}`, or `null` when none are configured.
 *
 * Upstream fetched these inside the message list, which only mounts after
 * the chat starts, and rendered them only when there were no messages, so
 * they were never shown. They are shown on the empty chat now.
 */
export function useStarterQuestions(): string[] {
  const { backend } = useClientConfig();
  const [questions, setQuestions] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const response = await fetch(`${backend}/api/v1/chat/config`);
        if (!response.ok) return;
        const data = await response.json();
        const list = Array.isArray(data?.starterQuestions)
          ? data.starterQuestions.filter(
              (q: unknown): q is string => typeof q === "string" && q.trim() !== "",
            )
          : [];
        if (!cancelled) setQuestions(list.slice(0, 4));
      } catch {
        // No starters is a fine empty state; nothing to tell the user.
      }
    };
    load();
    return () => {
      cancelled = true;
    };
  }, [backend]);

  return questions;
}
