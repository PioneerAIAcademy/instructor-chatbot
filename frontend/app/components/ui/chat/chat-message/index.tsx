import { Check, Copy, Pencil, RefreshCw } from "lucide-react";

import { Message } from "ai";
import { Fragment, memo, useEffect, useState } from "react";
import { getChromeStrings } from "../../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../../lib/i18n";
import { Button } from "../../button";
import { Tooltip } from "../../tooltip";
import { useCopyToClipboard } from "../hooks/use-copy-to-clipboard";
import {
  ChatHandler,
  DateSpansData,
  EventData,
  MessageAnnotation,
  MessageAnnotationType,
  SourceData,
  SuggestedQuestionsData,
  UserLanguageData,
  getAnnotationData,
  getSourceAnnotationData,
} from "../index";
import ChatAvatar from "./chat-avatar";
import { ChatEvents } from "./chat-events";
import { ChatSources } from "./chat-sources";
import { SuggestedQuestions } from "./chat-suggestedQuestions";
import { cleanAnswerForClipboard } from "./copy-utils";
import Markdown from "./markdown";
import { UserFeedbackComponent } from "./UserFeedbackComponent";

type ContentDisplayConfig = {
  order: number;
  component: JSX.Element | null;
};

// Round icon action under a message (direction D): 40px, 44px on phones.
export const ICON_ACTION =
  "h-11 w-11 sm:h-10 sm:w-10 rounded-full border border-ia-border bg-transparent text-ia-text " +
  "hover:border-ia-border-strong hover:bg-transparent transition-colors " +
  "focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg";

// The answer: status line and text. The Sources button and the suggested
// follow-ups render below it, in ChatMessage (prototype order: actions row,
// then suggestion chips). Only the annotation types the backend sends
// (backend/API.md): events, date_spans, user_language, sources,
// suggested_questions.
function ChatMessageContent({
  message,
  isLoading,
  sourceData,
}: {
  message: Message;
  isLoading: boolean;
  // Processed once in ChatMessage (getSourceAnnotationData).
  sourceData?: SourceData;
}) {
  const annotations = message.annotations as MessageAnnotation[] | undefined;

  if (!annotations?.length)
    return (
      <Markdown
        content={message.content}
        isLoading={isLoading}
        messageId={message.id}
      />
    );

  const eventData = getAnnotationData<EventData>(
    annotations,
    MessageAnnotationType.EVENTS,
  );
  // The backend's date phrases (date_spans); Markdown highlights exactly these,
  // and only falls back to its own date pattern when there are none.
  const dateSpansData = getAnnotationData<DateSpansData>(
    annotations,
    MessageAnnotationType.DATE_SPANS,
  );
  const userLanguageData = getAnnotationData<UserLanguageData>(
    annotations,
    MessageAnnotationType.USER_LANGUAGE,
  );
  const userLanguage = userLanguageData[0]?.language;

  const contents: ContentDisplayConfig[] = [
    {
      // Render unconditionally: ChatEvents shows a "Thinking…" fallback while
      // loading before the first status event, and returns null itself once
      // the answer starts or loading ends.
      order: -3,
      component: (
        <ChatEvents
          isLoading={isLoading}
          data={eventData}
          hasResponseText={message.content.trim().length > 0}
        />
      ),
    },
    {
      order: 0,
      component: (
        <Markdown
          content={message.content}
          sources={sourceData}
          dateSpans={dateSpansData[0]}
          isLoading={isLoading}
          userLanguage={userLanguage}
          messageId={message.id}
        />
      ),
    },
  ];

  return (
    <div className="flex-1 gap-4 flex flex-col min-w-0 max-w-full">
      {contents
        .sort((a, b) => a.order - b.order)
        .map((content, index) => (
          <Fragment key={index}>{content.component}</Fragment>
        ))}
    </div>
  );
}

function ChatMessage({
  chatMessage,
  isLoading,
  append,
  reload,
  showReload,
  isLastMessage = false,
  onEditSubmit,
}: {
  chatMessage: Message;
  isLoading: boolean;
  append: Pick<ChatHandler, "append">["append"];
  reload?: Pick<ChatHandler, "reload">["reload"];
  showReload?: boolean;
  isLastMessage?: boolean;
  onEditSubmit: (messageId: string, content: string) => void;
}) {
  const { isCopied, copyToClipboard } = useCopyToClipboard({ timeout: 2000 });
  const [isEditing, setIsEditing] = useState(false);
  const [editedContent, setEditedContent] = useState("");
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  const chromeStrings = getChromeStrings(uiLang);

  // look for an annotation with the trace_id
  const traceId =
    (
      chatMessage.annotations?.find(
        (annotation) => (annotation as MessageAnnotation)?.trace_id,
      ) as MessageAnnotation
    )?.trace_id || "";

  const isUser = chatMessage.role === "user";
  const annotations = chatMessage.annotations as MessageAnnotation[] | undefined;
  const sourceData = annotations?.length ? getSourceAnnotationData(annotations)[0] : undefined;
  const suggestedQuestions = annotations?.length
    ? getAnnotationData<SuggestedQuestionsData>(
        annotations,
        MessageAnnotationType.SUGGESTED_QUESTIONS,
      )[0]
    : undefined;
  const copyContent = isUser
    ? chatMessage.content
    : cleanAnswerForClipboard(chatMessage.content);

  const handleEditClick = () => {
    setEditedContent(chatMessage.content);
    setIsEditing(true);
  };

  const handleSaveEdit = () => {
    const trimmedContent = editedContent.trim();
    if (trimmedContent) {
      onEditSubmit(chatMessage.id, trimmedContent);
    }
    setIsEditing(false);
    setEditedContent("");
  };

  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditedContent("");
  };

  return (
    <div
      data-message-id={chatMessage.id}
      data-message-role={chatMessage.role}
      className={`flex flex-col gap-2 ${isUser ? "items-end" : "items-start"}`}
    >
      {/* User message - dark bubble on right */}
      {isUser && (
        <div
          className={`group flex flex-col items-end gap-1 ${isEditing ? "w-full max-w-[90%] sm:max-w-[576px]" : "max-w-[90%] sm:max-w-[76%]"}`}
        >
          {isEditing ? (
            /* Edit mode - inline textarea with full width */
            <div className="w-full rounded-xl border border-ia-border-strong bg-ia-surface p-3 shadow-[0_0_0_2px_var(--ia-bg),0_0_0_4px_var(--ia-focus)]">
              <textarea
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                aria-label="Edit your message"
                className="w-full bg-transparent border-none text-ia-text focus:outline-none text-base leading-6 resize-none min-h-[50px] max-h-[200px]"
                autoFocus
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) {
                    e.preventDefault();
                    handleSaveEdit();
                  }
                }}
              />
              <div className="flex items-center justify-end gap-3 mt-3">
                <Button
                  onClick={handleCancelEdit}
                  variant="ghost"
                  className="h-10 rounded-full border border-ia-border bg-transparent px-4 text-sm font-semibold text-ia-text hover:border-ia-border-strong hover:bg-transparent focus-visible:ring-2 focus-visible:ring-ia-focus"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  className="h-10 rounded-full bg-ia-blue-4 px-5 text-sm font-semibold text-white hover:bg-ia-navy-4 focus-visible:ring-2 focus-visible:ring-ia-focus"
                >
                  Save
                </Button>
              </div>
            </div>
          ) : (
            /* Normal message display - hugs content */
            <>
              {/* Gray 4 bubble, white text (9.7:1). */}
              <div className="rounded-xl bg-ia-bubble px-4 py-3 text-white">
                <p className="text-base leading-6 break-words whitespace-pre-wrap">
                  {chatMessage.content}
                </p>
              </div>

              {/* Action buttons for user message - only visible on hover */}
              <div className="flex items-center gap-1 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                <Tooltip label="Edit" side="top">
                  <Button
                    onClick={handleEditClick}
                    size="icon"
                    variant="ghost"
                    className={ICON_ACTION}
                    aria-label="Edit"
                  >
                    <Pencil aria-hidden="true" className="h-4 w-4" />
                  </Button>
                </Tooltip>
                <Tooltip
                  label={chromeStrings.copyButton}
                  side="top"
                  align="end"
                >
                  <Button
                    onClick={() => copyToClipboard(copyContent)}
                    size="icon"
                    variant="ghost"
                    className={`${ICON_ACTION} ${isCopied ? "pointer-events-none" : ""}`}
                    aria-label={chromeStrings.copyButton}
                  >
                    {isCopied ? (
                      <Check aria-hidden="true" className="h-4 w-4" />
                    ) : (
                      <Copy aria-hidden="true" className="h-4 w-4" />
                    )}
                  </Button>
                </Tooltip>
              </div>
            </>
          )}
        </div>
      )}

      {/* Bot message - left aligned with inline action icons */}
      {!isUser && (
        <div className="w-full">
          <div className="flex items-start gap-3">
            {/* Avatar on the left */}
            <div className="mt-0.5">
              <ChatAvatar role={chatMessage.role} />
            </div>

            {/* Message content */}
            <div className="flex-1 min-w-0 max-w-full">
              <ChatMessageContent
                message={chatMessage}
                isLoading={isLoading}
                sourceData={sourceData}
              />

              {/* Action buttons - inline after message content */}
              {!isLoading && (
                <div className="mt-4 flex flex-wrap items-center gap-2">
                  {sourceData && (
                    <ChatSources data={sourceData} answer={chatMessage.content} />
                  )}
                  <Tooltip
                    label={chromeStrings.copyButton}
                    side="top"
                    align="start"
                  >
                    <Button
                      onClick={() => copyToClipboard(copyContent)}
                      size="icon"
                      variant="ghost"
                      className={`${ICON_ACTION} ${isCopied ? "pointer-events-none" : ""}`}
                      aria-label={chromeStrings.copyButton}
                    >
                      {isCopied ? (
                        <Check aria-hidden="true" className="h-[18px] w-[18px]" />
                      ) : (
                        <Copy aria-hidden="true" className="h-[18px] w-[18px]" />
                      )}
                    </Button>
                  </Tooltip>
                  <UserFeedbackComponent
                    traceId={traceId}
                    isLastMessage={isLastMessage}
                  />
                  {showReload && reload && (
                    <Tooltip label={chromeStrings.regenerateButton} side="top">
                      <Button
                        onClick={reload}
                        size="icon"
                        variant="ghost"
                        className={ICON_ACTION}
                        aria-label={chromeStrings.regenerateButton}
                      >
                        <RefreshCw aria-hidden="true" className="h-[18px] w-[18px]" />
                      </Button>
                    </Tooltip>
                  )}
                </div>
              )}
              {!isLoading && suggestedQuestions && (
                <div className="mt-4 mb-4">
                  <SuggestedQuestions questions={suggestedQuestions} append={append} />
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Memoized so a completed message does not re-render on every streamed token
// of a later message. Props are referentially stable for completed messages
// (useChat keeps prior message objects; append/reload/onEditSubmit are stable),
// so the default shallow comparison keeps per-token render cost O(1).
export default memo(ChatMessage);
