"use client";

/**
 * Starter question cards on the empty chat (direction D): a 4px Blue 4 bar,
 * two columns on wider screens, one on phones. Clicking a card asks it.
 */
export default function StarterQuestions({
  questions,
  onAsk,
}: {
  questions: string[];
  onAsk: (question: string) => void;
}) {
  if (!questions.length) return null;
  return (
    <ul
      className="grid w-full grid-cols-1 gap-3 sm:grid-cols-2 sm:gap-4"
      aria-label="Suggested questions"
    >
      {questions.map((question) => (
        <li key={question} className="flex">
          <button
            type="button"
            onClick={() => onAsk(question)}
            className="flex min-h-[76px] w-full overflow-hidden rounded-xl border border-ia-border bg-ia-surface text-left transition-colors hover:border-ia-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg"
          >
            <span aria-hidden="true" className="w-1 flex-shrink-0 bg-ia-blue-4" />
            <span className="flex items-center p-4 text-[15px] font-semibold leading-snug text-ia-text">
              {question}
            </span>
          </button>
        </li>
      ))}
    </ul>
  );
}
