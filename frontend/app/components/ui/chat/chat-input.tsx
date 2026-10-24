import { ArrowUp } from "lucide-react";
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

// The question box, without the controls this app doesn't use (uploads,
// dictation, the role pill, LlamaCloud): a white box with a soft border, a
// gold send button, and a dark stop button while an answer streams.
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
      <div className="flex w-full items-end gap-2 rounded-2xl border border-ia-line bg-ia-page py-2 pl-4 pr-2 shadow-[0_1px_2px_rgba(0,0,0,0.04),0_4px_16px_rgba(0,0,0,0.06)] transition-[border-color,box-shadow] focus-within:border-ia-gold dark:shadow-none">
        <textarea
          ref={textareaRef}
          autoFocus
          name="message"
          aria-label={placeholder}
          placeholder={placeholder}
          className="max-h-[150px] min-h-[40px] w-full resize-none overflow-y-auto border-none bg-transparent px-0 py-[9px] text-[15px] leading-[22px] text-ia-text placeholder:text-ia-muted focus:outline-none focus-visible:ring-0 focus-visible:ring-offset-0 md:max-h-[220px] lg:max-h-[260px] [scrollbar-width:thin] [scrollbar-color:#646362_transparent]"
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
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ia-text p-0 text-ia-page hover:opacity-85"
            >
              <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
                <rect x="1" y="1" width="12" height="12" fill="currentColor" rx="2.5" />
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
              // BYU gold with a near-black arrow (10.4:1); white would be 1.6:1.
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-ia-gold p-0 text-ia-on-gold hover:bg-ia-gold-hover disabled:cursor-not-allowed disabled:opacity-40"
            >
              <ArrowUp className="h-5 w-5" strokeWidth={2.25} aria-hidden="true" />
              <span className="sr-only">{strings.sendButton}</span>
            </Button>
          </Tooltip>
        )}
      </div>
    </form>
  );
}
