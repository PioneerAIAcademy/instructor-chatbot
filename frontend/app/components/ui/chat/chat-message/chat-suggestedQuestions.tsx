import { useState } from "react";
import { ChatHandler, SuggestedQuestionsData } from "..";

/**
 * Suggested follow-up chips (direction D): Blue 1 pills with Gray 4 text
 * (9.2:1), 36px tall, 44px on phones. Real buttons, so they work by keyboard.
 */
export function SuggestedQuestions({
  questions,
  append,
}: {
  questions: SuggestedQuestionsData;
  append: Pick<ChatHandler, "append">["append"];
}) {
  const [showQuestions, setShowQuestions] = useState(questions.length > 0);

  if (!showQuestions || append === undefined) return null;
  return (
    <ul className="m-0 flex list-none flex-wrap gap-2 p-0" aria-label="Suggested follow-up questions">
      {questions.map((question) => (
        <li key={question} className="max-w-full">
          <button
            type="button"
            onClick={() => {
              append({ role: "user", content: question });
              setShowQuestions(false);
            }}
            className="inline-flex min-h-[44px] max-w-full items-center rounded-full bg-ia-blue-1 px-3.5 py-2 text-left text-sm font-semibold leading-snug text-ia-gray-4 transition-colors hover:bg-ia-blue-2 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg sm:min-h-[36px]"
          >
            <span className="break-words">{question}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
