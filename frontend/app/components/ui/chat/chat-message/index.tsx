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

// The answer: status line, text, the cited guides as chips with the action
// icons under them, then the suggested follow-ups. Only the annotation types the backend sends (backend/API.md):
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
      component:
        !isLoading && suggestedQuestionsData[0] ? (
          <SuggestedQuestions
            questions={suggestedQuestionsData[0]}
            onAsk={(question) => append?.({ role: "user", content: question })}
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
            <div className="w-full rounded-2xl border border-ia-line bg-ia-surface p-4">
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
                  {chromeStrings.editCancel}
                </Button>
                <Button
                  onClick={handleSaveEdit}
                  className="bg-[#FFC328] dark:bg-white text-[#1F1E1D] dark:text-black hover:bg-[#F5B400] dark:hover:bg-gray-200 text-sm px-6"
                >
                  {chromeStrings.editSave}
                </Button>
              </div>
            </div>
          ) : (
            /* Normal message display - hugs content */
            <>
              <div className="rounded-2xl rounded-br-md bg-ia-surface px-4 py-2.5 text-ia-text">
                <p className="break-words text-[15px] leading-6">
                  {chatMessage.content}
                </p>
              </div>

              {/* Action buttons for user message - only visible on hover */}
              <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
                <Tooltip label={chromeStrings.editButton} side="top">
                  <Button
                    onClick={handleEditClick}
                    size="icon"
                    variant="ghost"
                    className="h-6 w-6 rounded-full hover:bg-[rgba(181,181,181,0.15)] transition-colors focus-visible:ring-focus-ring focus-visible:ring-offset-2"
                    aria-label={chromeStrings.editButton}
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
                    // The cited guides as chips, then small gray icons:
                    // copy, thumbs up and down, regenerate.
                    <div className="flex flex-col gap-2">
                      {sourceData && (
                        <ChatSources
                          data={sourceData}
                          answer={chatMessage.content}
                        />
                      )}
                      <div className="-ml-2 flex items-center gap-0.5">
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
                              <Check className="h-4 w-4" aria-hidden="true" />
                            ) : (
                              <Copy className="h-4 w-4" aria-hidden="true" />
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
                              variant="ghost"
                              className={ACTION_BUTTON}
                              aria-label={chromeStrings.regenerateButton}
                            >
                              <RefreshCw className="h-4 w-4" aria-hidden="true" />
                            </Button>
                          </Tooltip>
                        )}
                      </div>
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
