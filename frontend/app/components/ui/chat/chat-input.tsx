import { useCallback, useEffect, useRef, useState } from "react";
import { getChromeStrings } from "../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../lib/i18n";
import { Button } from "../button";
import { Tooltip } from "../tooltip";
import { ChatHandler } from "./chat.interface";

function useChromeStrings() {
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  return getChromeStrings(uiLang);
}

// The send/stop button: 44px, Blue 4 with white (5.5:1), Navy 4 on hover.
const ROUND_BUTTON =
  "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full p-0 " +
  "bg-ia-blue-4 text-white hover:bg-ia-navy-4 " +
  "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg";

export default function ChatInput(
  props: Pick<
    ChatHandler,
    | "isLoading"
    | "input"
    | "handleSubmit"
    | "handleInputChange"
    | "messages"
    | "setInput"
    | "append"
    | "stop"
  > & {
    inputPlaceholder?: string;
  },
) {
  const strings = useChromeStrings();
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);
  // Phones get the short placeholder: a textarea placeholder can't end in
  // "…" (Chrome just cuts it off), and the long one doesn't fit.
  const [isNarrow, setIsNarrow] = useState(false);
  useEffect(() => {
    const query = window.matchMedia("(max-width: 639px)");
    const update = () => setIsNarrow(query.matches);
    update();
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  const placeholder = isNarrow
    ? strings.inputPlaceholderShort
    : (props.inputPlaceholder ?? strings.inputPlaceholder);

  const resizeTextarea = useCallback(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    if (!props.input) {
      textarea.style.height = "";
      textarea.scrollTop = 0;
      return;
    }
    textarea.style.height = "auto";
    const maxHeight =
      window.innerWidth >= 1024 ? 260 : window.innerWidth >= 768 ? 220 : 150;
    textarea.style.height = `${Math.min(textarea.scrollHeight, maxHeight)}px`;
    textarea.scrollTop = textarea.scrollHeight;
  }, [props.input]);

  // The value can change without typing (a starter question, a cleared
  // input), so keep the height in step with it, not only with onInput.
  useEffect(() => {
    resizeTextarea();
  }, [props.input, resizeTextarea]);

  const onSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    props.handleSubmit(e);
    if (textareaRef.current) {
      textareaRef.current.style.height = "";
    }
  };

  return (
    <form onSubmit={onSubmit} className="w-full">
      <div className="flex w-full items-end gap-3 rounded-xl border border-ia-border bg-ia-surface py-3 pl-4 pr-3 transition-[border-color,box-shadow] focus-within:border-ia-border-strong focus-within:shadow-[0_0_0_2px_var(--ia-bg),0_0_0_4px_var(--ia-focus)]">
        <textarea
          ref={textareaRef}
          autoFocus
          name="message"
          aria-label={placeholder}
          placeholder={placeholder}
          // Placeholder at body contrast: Gray 3 fails AA below 18px.
          className="min-h-[44px] w-full resize-none overflow-y-auto border-none bg-transparent px-0 py-[10px] text-base leading-6 text-ia-text placeholder:text-ia-text placeholder:opacity-100 focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 max-h-[150px] md:max-h-[220px] lg:max-h-[260px] [scrollbar-width:thin] [scrollbar-color:var(--ia-gray-3)_transparent]"
          value={props.input}
          onChange={(e) => props.handleInputChange(e as any)}
          rows={1}
          onInput={resizeTextarea}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              // requestSubmit() ignores the disabled Send button, so check
              // here too: a blank or spaces-only input sends nothing.
              if (props.isLoading || !props.input.trim()) return;
              e.currentTarget.form?.requestSubmit();
            }
          }}
        />

        {props.isLoading ? (
          <Tooltip label={strings.stopButton} side="top" align="end">
            <Button
              type="button"
              onClick={props.stop}
              aria-label={strings.stopButton}
              className={ROUND_BUTTON}
            >
              <svg width="18" height="18" viewBox="0 0 20 20" aria-hidden="true">
                <rect x="3" y="3" width="14" height="14" fill="currentColor" rx="3.5" />
              </svg>
            </Button>
          </Tooltip>
        ) : (
          <Tooltip label={strings.sendButton} side="top" align="end">
            <Button
              type="submit"
              disabled={!props.input.trim()}
              aria-label={strings.sendButton}
              className={`${ROUND_BUTTON} disabled:cursor-not-allowed disabled:bg-ia-gray-1 disabled:text-ia-gray-3 disabled:opacity-100 dark:disabled:bg-ia-gray-3 dark:disabled:text-ia-gray-1`}
            >
              <svg
                width="22"
                height="22"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M12 19V5" />
                <path d="m5 12 7-7 7 7" />
              </svg>
            </Button>
          </Tooltip>
        )}
      </div>
    </form>
  );
}
