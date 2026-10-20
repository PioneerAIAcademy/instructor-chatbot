import { useEffect, useRef } from "react";

import ChatMessage from "./chat-message";
import { ChatHandler } from "./chat.interface";
import ChatPendingIndicator from "./chat-pending-indicator";

export default function ChatMessages(
  props: Pick<
    ChatHandler,
    "messages" | "isLoading" | "reload" | "stop" | "append"
  > & {
    onEditSubmit: (messageId: string, content: string) => void;
  },
) {
  const scrollableChatContainerRef = useRef<HTMLDivElement>(null);
  const messageLength = props.messages.length;
  const lastMessage = props.messages[messageLength - 1];

  const scrollToBottom = () => {
    if (scrollableChatContainerRef.current) {
      scrollableChatContainerRef.current.scrollTop =
        scrollableChatContainerRef.current.scrollHeight;
    }
  };

  const isLastMessageFromAssistant =
    messageLength > 0 && lastMessage?.role !== "user";

  // `isPending` indicate
  // that stream response is not yet received from the server,
  // so we show a loading indicator to give a better UX.
  const isPending = props.isLoading && !isLastMessageFromAssistant;

  // Only scroll when a new message is ADDED — not on every streamed token.
  // Depending on `lastMessage` (a new object each token) forced a synchronous
  // reflow on every token; `messageLength` changes only when a turn is added.
  useEffect(() => {
    scrollToBottom();
  }, [messageLength]);

  return (
    <div
      className="flex-1 w-full"
      ref={scrollableChatContainerRef}
    >
      <div className="flex flex-col gap-6">
        {props.messages.map((m, i) => {
          const isLastMessage = i === messageLength - 1;
          const isLoadingMessage = isLastMessage && props.isLoading;
          const showReloadIcon =
            isLastMessage && !props.isLoading && m.role !== "user";
          return (
            <ChatMessage
              key={m.id}
              chatMessage={m}
              isLoading={isLoadingMessage}
              append={props.append!}
              reload={props.reload}
              showReload={showReloadIcon}
              isLastMessage={isLastMessage}
              onEditSubmit={props.onEditSubmit}
            />
          );
        })}
        {isPending && (
          <ChatPendingIndicator />
        )}
      </div>
    </div>
  );
}
