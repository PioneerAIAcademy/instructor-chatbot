"use client";

import { useEffect, useState } from "react";
import { resolveUiLanguage } from "../../../../lib/i18n";
import { useUiLanguage } from "../../../../lib/use-chrome-strings";
import { useClientConfig } from "./use-config";

/**
 * The starter questions from `GET /api/v1/chat/config?lang=<code>`
 * (backend/API.md): `{"starterQuestions": [...]}` in the interface language,
 * or `null` when none are configured. Refetched when the language changes.
 *
 * Upstream fetched these inside the message list, which only mounts after
 * the chat starts, and rendered them only when there were no messages, so
 * they were never shown. They are shown on the empty chat now.
 */
export function useStarterQuestions(): string[] {
  const { backend } = useClientConfig();
  // Only a trigger: the effect re-runs when the language changes.
  const uiLang = useUiLanguage();
  const [questions, setQuestions] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        // Read the language here, not from the first render's "en"
        // placeholder, so the first request already asks for the right
        // cards and English ones never flash before them.
        const lang = resolveUiLanguage();
        const response = await fetch(
          `${backend}/api/v1/chat/config?lang=${encodeURIComponent(lang)}`,
        );
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
  }, [backend, uiLang]);

  return questions;
}
