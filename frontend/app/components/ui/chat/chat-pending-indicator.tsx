import { getChromeStrings } from "../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../lib/i18n";
import ChatAvatar from "./chat-message/chat-avatar";
import { ChatStatus } from "./chat-status";

export default function ChatPendingIndicator() {
  return (
    <div className="w-full">
      <div className="flex items-start gap-3">
        <div className="mt-0.5">
          <ChatAvatar role="assistant" />
        </div>
        <div className="flex min-h-8 min-w-0 max-w-full flex-1 items-center">
          <ChatStatus text={getChromeStrings(resolveUiLanguage()).thinkingDefault} />
        </div>
      </div>
    </div>
  );
}
