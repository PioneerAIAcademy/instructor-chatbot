import { Loader2 } from "lucide-react";
import { getChromeStrings } from "../../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../../lib/i18n";
import { EventData } from "../index";

/**
 * ChatEvents component displays real-time status indicators during RAG processing.
 * Shows inline status with randomized messages that auto-disappear when response starts.
 */
export function ChatEvents({
  data,
  isLoading,
  hasResponseText,
}: {
  data: EventData[];
  isLoading: boolean;
  hasResponseText: boolean;
}) {
  // Get the latest status message
  const latestMessage = data.length > 0 ? data[data.length - 1].title : "";

  // Show the indicator whenever we're loading and no answer text has
  // arrived yet — even BEFORE the first status event lands. The backend
  // takes a moment to open the stream and emit its first status; without
  // a default the indicator would flash empty in that window. Falling
  // back to a localized "Thinking…" keeps it from ever sitting blank.
  const showStatus = isLoading && !hasResponseText;

  if (!showStatus) return null;

  const displayMessage =
    latestMessage || getChromeStrings(resolveUiLanguage()).thinkingDefault;

  return (
    <div className="flex items-center gap-2 text-xs text-[#73726C] dark:text-[#C2C0B6]">
      <Loader2 className="h-4 w-4 animate-spin" />
      <span>{displayMessage}</span>
    </div>
  );
}
