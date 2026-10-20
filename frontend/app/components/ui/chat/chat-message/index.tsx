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
import { ACTION_BUTTON, ChatSources } from "./chat-sources";
import { SuggestedQuestions } from "./chat-suggestedQuestions";
import { cleanAnswerForClipboard } from "./copy-utils";
import Markdown from "./markdown";
import { UserFeedbackComponent } from "./UserFeedbackComponent";

type ContentDisplayConfig = {
  order: number;
  component: JSX.Element | null;
};

// The answer: status line, text, the action row (Sources pill, thumbs, copy),
// then the suggested follow-ups. Only the annotation types the backend sends (backend/API.md):
// events, date_spans, user_language, sources, suggested_questions. The
// calendar, tuition, image, file, tool, and correction branches are gone.
function ChatMessageContent({
  message,
  isLoading,
  append,
  sourceData,
  actionRow,
}: {
  message: Message;
  isLoading: boolean;
  append: Pick<ChatHandler, "append">["append"];
  // Processed once in ChatMessage.
  sourceData?: SourceData;
  actionRow: JSX.Element | null;
}) {
  const annotations = message.annotations as MessageAnnotation[] | undefined;

  if (!annotations?.length)
    return (
      <div className="flex min-w-0 max-w-full flex-1 flex-col gap-4">
        <Markdown
          content={message.content}
          isLoading={isLoading}
          messageId={message.id}
        />
        {actionRow}
      </div>
    );

  const eventData = getAnnotationData<EventData>(
    annotations,
    MessageAnnotationType.EVENTS,
  );
  const suggestedQuestionsData = getAnnotationData<SuggestedQuestionsData>(
    annotations,
    MessageAnnotationType.SUGGESTED_QUESTIONS,
  );
  // The backend's date phrases; Markdown highlights exactly these and only
  // falls back to its own date pattern when there are none.
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
      // Render unconditionally — ChatEvents shows a localized "Thinking…"
      // fallback while loading even before the first status event arrives,
      // and returns null itself once a response starts or loading ends.
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
    {
      order: 3,
      component: actionRow,
    },
    {
      order: 4,
      component: suggestedQuestionsData[0] ? (
        <SuggestedQuestions
          questions={suggestedQuestionsData[0]}
          append={append}
        />
      ) : null,
    },
  ];

  return (
    <div className="flex-1 gap-4 flex flex-col min-w-0 max-w-full">
      {contents
        .sort((a, b) => a.order - b.order)
        .map((content, index) => (
          <Fragment key={index}>{content.component}</Fragment>
        ))}
      <div className="mb-2"></div>
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
  // Processed once per message (getSourceAnnotationData is cached and pure).
  const annotations = chatMessage.annotations as MessageAnnotation[] | undefined;
  const sourceData = annotations?.length
    ? getSourceAnnotationData(annotations)[0]
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
          className={`group flex flex-col items-end gap-1 ${isEditing ? "w-full max-w-[90%] sm:max-w-[576px]" : "max-w-[90%] sm:max-w-[576px]"}`}
        >
          {isEditing ? (
            /* Edit mode - inline textarea with full width */
            <div className="w-full bg-[#F0EEE6] dark:bg-[#2a2a2a] border border-[rgba(31,30,29,0.15)] dark:border-[rgba(252,252,252,0.1)] rounded-2xl p-4">
              <textarea
                value={editedContent}
                onChange={(e) => setEditedContent(e.target.value)}
                className="w-full bg-transparent border-none text-[#3D3D3A] dark:text-white placeholder:text-[#73726C] dark:placeholder:text-[#B5B5B5] focus:outline-none text-sm sm:text-[15.75px] leading-[24px] sm:leading-[28px] resize-none min-h-[50px] max-h-[200px]"
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
                  className="text-[#73726C] dark:text-[#B5B5B5] bg-[#D1CFC2] hover:bg-[#B3B1A0] hover:text-[#3D3D3A] dark:text-[#3E3C33] dark:hover:text-white text-sm"
                >
                  Cancel
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  className="bg-[#056CB6] dark:bg-white text-white dark:text-black hover:bg-[#0F4B8F] dark:hover:bg-gray-200 text-sm px-6"
                >
                  Save
                </Button>
              </div>
            </div>
          ) : (
            /* Normal message display - hugs content */
            <>
              <div className="bg-[#E9E7E1] dark:bg-[#242628] text-[#3D3D3A] dark:text-[#FCFCFC] px-4 sm:px-[17px] py-3 sm:py-[11px] rounded-[24px] rounded-br-[8px] border border-[rgba(31,30,29,0.12)] dark:border-[rgba(252,252,252,0.06)]">
                <p className="text-sm sm:text-[15.75px] leading-[24px] sm:leading-[28px] tracking-[-0.1px] break-words">
                  {chatMessage.content}
                </p>
              </div>

              {/* Action buttons for user message - only visible on hover */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Tooltip label="Edit" side="top">
                  <Button
                    onClick={handleEditClick}
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6 rounded-full hover:bg-[rgba(181,181,181,0.15)] transition-colors focus-visible:ring-focus-ring focus-visible:ring-offset-2"
                    aria-label="Edit"
                  >
                    <Pencil className="h-3.5 w-3.5 text-[#3D3D3A] dark:text-[#FCFCFC] hover:text-[#1F1E1D] dark:hover:text-white transition-colors" />
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
                    className={`h-6 w-6 rounded-full hover:bg-[rgba(181,181,181,0.15)] transition-colors focus-visible:ring-focus-ring focus-visible:ring-offset-2 ${isCopied ? "pointer-events-none" : ""}`}
                    aria-label={chromeStrings.copyButton}
                  >
                    {isCopied ? (
                      <Check className="h-3.5 w-3.5 text-gray-700 dark:text-[#FCFCFC]" />
                    ) : (
                      <Copy className="h-3.5 w-3.5 text-gray-700 dark:text-[#FCFCFC] hover:text-gray-900 dark:hover:text-white transition-colors" />
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

            {/* Message content, with the action row under the text */}
            <div className="flex-1 min-w-0 max-w-full">
              <ChatMessageContent
                message={chatMessage}
                isLoading={isLoading}
                append={append}
                sourceData={sourceData}
                actionRow={
                  isLoading ? null : (
                    <div className="flex flex-wrap items-center gap-2">
                      {sourceData && (
                        <ChatSources
                          data={sourceData}
                          answer={chatMessage.content}
                        />
                      )}
                      <UserFeedbackComponent
                        traceId={traceId}
                        isLastMessage={isLastMessage}
                      />
                      <Tooltip
                        label={chromeStrings.copyButton}
                        side="top"
                        align="start"
                      >
                        <Button
                          onClick={() => copyToClipboard(copyContent)}
                          variant="ghost"
                          className={`${ACTION_BUTTON} ${isCopied ? "pointer-events-none" : ""}`}
                          aria-label={chromeStrings.copyButton}
                        >
                          {isCopied ? (
                            <Check className="h-[18px] w-[18px]" aria-hidden="true" />
                          ) : (
                            <Copy className="h-[18px] w-[18px]" aria-hidden="true" />
                          )}
                        </Button>
                      </Tooltip>
                      {showReload && reload && (
                        <Tooltip label={chromeStrings.regenerateButton} side="top">
                          <Button
                            onClick={reload}
                            variant="ghost"
                            className={ACTION_BUTTON}
                            aria-label={chromeStrings.regenerateButton}
                          >
                            <RefreshCw className="h-[18px] w-[18px]" aria-hidden="true" />
                          </Button>
                        </Tooltip>
                      )}
                    </div>
                  )
                }
              />
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
