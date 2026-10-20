import { useState } from "react";
import { ChatHandler, SuggestedQuestionsData } from "..";

export function SuggestedQuestions({
  questions,
  append,
}: {
  questions: SuggestedQuestionsData;
  append: Pick<ChatHandler, "append">["append"];
}) {
  const [showQuestions, setShowQuestions] = useState(questions.length > 0);

  return (
    showQuestions &&
    append !== undefined && (
      <div className="flex flex-wrap gap-2">
        {questions.map((question, index) => (
          // A real button (upstream used an <a> with no href, which the
          // keyboard can't reach).
          <button
            type="button"
            key={index}
            onClick={() => {
              append({ role: "user", content: question });
              setShowQuestions(false);
            }}
            // Pale-blue pills; 44px tall on phones for touch, 36px up.
            className="inline-flex min-h-11 max-w-full items-center rounded-full bg-[#E7F0FA] px-4 py-2 text-left text-[15px] font-medium text-[#454540] transition-colors hover:bg-[#8EBDDE] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 dark:bg-[#056CB6]/25 dark:text-[#E7F0FA] dark:hover:bg-[#056CB6]/45 sm:min-h-9"
          >
            <span className="break-words">{question}</span>
          </button>
        ))}
      </div>
    )
  );
}
