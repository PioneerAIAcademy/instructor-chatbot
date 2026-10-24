"use client";

import { useChromeStrings } from "../lib/use-chrome-strings";

// The welcome screen's cards, two columns on wider screens, one on phones.
// Each starter from the backend (CONVERSATION_STARTERS) is either a plain
// question or "Title | question": the card shows the title in bold and the
// question under it, and clicking it asks the question.
export function parseStarter(starter: string): {
  title: string;
  question: string;
} {
  const split = starter.indexOf("|");
  if (split === -1) return { title: starter.trim(), question: starter.trim() };
  const title = starter.slice(0, split).trim();
  const question = starter.slice(split + 1).trim();
  if (!title || !question) {
    const only = title || question;
    return { title: only, question: only };
  }
  return { title, question };
}

export default function StarterQuestions({
  questions,
  onAsk,
}: {
  questions: string[];
  onAsk: (question: string) => void;
}) {
  const strings = useChromeStrings();
  const starters = questions.map(parseStarter).filter((s) => s.question);
  if (!starters.length) return null;
  return (
    <ul
      className="grid w-full grid-cols-1 gap-2 sm:grid-cols-2 sm:gap-3"
      aria-label={strings.startersAria}
    >
      {starters.map(({ title, question }) => (
        <li key={question} className="flex">
          <button
            type="button"
            onClick={() => onAsk(question)}
            className="flex w-full flex-col gap-1 rounded-xl bg-ia-surface px-4 py-3 text-left transition-colors hover:bg-ia-gold-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2"
          >
            <span className="text-sm font-bold text-ia-text">{title}</span>
            {question !== title && (
              <span className="text-[13px] leading-snug text-ia-muted">
                {question}
              </span>
            )}
          </button>
        </li>
      ))}
    </ul>
  );
}
