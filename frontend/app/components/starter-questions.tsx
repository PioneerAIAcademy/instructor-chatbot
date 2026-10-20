"use client";

/**
 * Starter question cards on the empty chat. Upstream fetched starters but
 * never showed them, so this borrows the look of upstream's disclaimer card
 * (white, hairline border, rounded-2xl), with a light-blue hover. Two columns
 * on wider screens, one on phones. Clicking a card asks it.
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
      className="grid w-full grid-cols-1 gap-2 md:grid-cols-2"
      aria-label="Suggested questions"
    >
      {questions.map((question) => (
        <li key={question} className="flex">
          <button
            type="button"
            onClick={() => onAsk(question)}
            className="w-full rounded-2xl border border-[rgba(31,30,29,0.12)] bg-white px-4 py-3 text-left text-sm font-medium text-[#3D3D3A] transition-colors hover:bg-[#056CB6]/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 dark:border-[rgba(252,252,252,0.06)] dark:bg-[#242628] dark:text-[#FCFCFC] dark:hover:bg-[#056CB6]/25 sm:text-[15px]"
          >
            {question}
          </button>
        </li>
      ))}
    </ul>
  );
}
