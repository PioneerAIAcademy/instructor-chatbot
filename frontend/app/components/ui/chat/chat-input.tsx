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

// Upstream's input, without the controls this app doesn't use (uploads,
// dictation, the role pill, LlamaCloud). Same look; the send/stop button is
// blue instead of gold.
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
  const placeholder = props.inputPlaceholder ?? strings.inputPlaceholder;

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

  // The value can change without typing (a cleared input, a ?prompt= prefill),
  // so keep the height in step with it, not only with onInput.
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
      <div className="w-full rounded-3xl border border-[rgba(31,30,29,0.15)] bg-white px-4 py-3 transition-[background-color,border-color,box-shadow] dark:border-[rgba(252,252,252,0.06)] dark:bg-[#242628]">
        <div className="relative mb-3 flex w-full items-center">
          <textarea
            ref={textareaRef}
            autoFocus
            name="message"
            aria-label={placeholder}
            placeholder={placeholder}
            className="min-h-[24px] w-full resize-none overflow-y-auto border-none bg-transparent px-0 text-sm text-[#141413] placeholder:text-[#73726C] focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 dark:text-white dark:placeholder:text-[#B5B5B5] sm:text-[15.875px] max-h-[150px] md:max-h-[220px] lg:max-h-[260px] [scrollbar-width:thin] [scrollbar-color:#646362_transparent]"
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
        </div>

        <div className="flex w-full items-center justify-end gap-2">
          {props.isLoading ? (
            <Tooltip label={strings.stopButton} side="top" align="end">
              <Button
                type="button"
                onClick={props.stop}
                aria-label={strings.stopButton}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-[#056CB6] p-0 text-white hover:bg-[#0F4B8F] dark:bg-white dark:text-black dark:hover:bg-gray-100"
              >
                <svg width="20" height="20" viewBox="0 0 20 20" aria-hidden="true">
                  <rect x="3" y="3" width="14" height="14" fill="currentColor" rx="3.5" />
                </svg>
                <span className="sr-only">{strings.stopButton}</span>
              </Button>
            </Tooltip>
          ) : (
            <Tooltip label={strings.sendButton} side="top" align="end">
              <Button
                type="submit"
                disabled={!props.input.trim()}
                aria-label={strings.sendButton}
                className="flex h-10 w-10 items-center justify-center rounded-full bg-[#056CB6] p-0 text-white hover:bg-[#0F4B8F] disabled:cursor-not-allowed disabled:opacity-50 dark:bg-white dark:text-black dark:hover:bg-gray-100"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                  <path
                    d="M14 2L7 9M14 2L9.5 14L7 9M14 2L2 6.5L7 9"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
                <span className="sr-only">{strings.sendButton}</span>
              </Button>
            </Tooltip>
          )}
        </div>
      </div>
    </form>
  );
}
