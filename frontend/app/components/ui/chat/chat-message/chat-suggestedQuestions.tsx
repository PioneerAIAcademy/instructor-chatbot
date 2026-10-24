import { useChromeStrings } from "../../../../lib/use-chrome-strings";
import { SuggestedQuestionsData } from "..";

// An answer's suggested follow-ups, as outlined pills under it. Clicking one
// asks it. Real buttons (upstream used an <a> with no href, which the
// keyboard can't reach).
export function SuggestedQuestions({
  questions,
  onAsk,
}: {
  questions: SuggestedQuestionsData;
  onAsk: (question: string) => void;
}) {
  const strings = useChromeStrings();
  if (!questions.length) return null;
  return (
    <div
      role="group"
      aria-label={strings.followUpsAria}
      className="flex flex-wrap gap-2"
    >
      {questions.map((question) => (
        <button
          type="button"
          key={question}
          onClick={() => onAsk(question)}
          // 44px tall on phones for touch, 36px up.
          className="inline-flex min-h-11 max-w-full items-center rounded-full border border-ia-line bg-ia-page px-4 py-2 text-left text-[14px] font-semibold text-ia-body transition-colors hover:border-ia-gold hover:bg-ia-gold-soft focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-focus-ring focus-visible:ring-offset-2 sm:min-h-9"
        >
          {question}
        </button>
      ))}
    </div>
  );
}
