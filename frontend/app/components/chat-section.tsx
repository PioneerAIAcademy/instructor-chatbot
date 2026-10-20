"use client";

import * as Sentry from "@sentry/nextjs";
import { useChat } from "ai/react";

import { getEditedDraftSnapshot } from "@/app/lib/draft-registry";
import { AlertTriangle, ArrowDown, ShieldCheck, X } from "lucide-react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getChromeStrings } from "../lib/chrome-strings";
import { getUserLanguagePref, resolveUiLanguage } from "../lib/i18n";
import { getDeviceId, getSessionId, getTimezone } from "../utils/session";
import DisclaimerMessage from "./disclaimer-message";
import Greeting from "./greeting";
import StarterQuestions from "./starter-questions";
import { ChatInput, ChatMessages, type SourceNode } from "./ui/chat";
import {
  SOURCES_PANEL_EVENT,
  type SourcesPanelEventDetail,
  SourcesSidebar,
} from "./ui/chat/chat-message/chat-sources";
import { useClientConfig } from "./ui/chat/hooks/use-config";
import { useStarterQuestions } from "./ui/chat/hooks/use-starter-questions";
import { useThrottledValue } from "./ui/chat/hooks/use-throttled-value";

const SCROLL_BOTTOM_THRESHOLD_PX = 120;
const SCROLL_BUTTON_REVEAL_PX = 220;

// Small breathing room left above the pinned prompt.
const PIN_TOP_GAP_PX = 12;

// Distance to the end of the REAL content — discount the reserved bottom
// spacer so "at the bottom" means "the answer is fully in view," not "scrolled
// into the empty reserved space."
const getDistanceFromBottom = (container: HTMLDivElement) => {
  const spacer = container.querySelector<HTMLElement>("[data-bottom-spacer]");
  const spacerHeight = spacer?.offsetHeight ?? 0;
  return (
    container.scrollHeight -
    spacerHeight -
    container.scrollTop -
    container.clientHeight
  );
};

export default function ChatSection() {
  const { backend } = useClientConfig();
  const [hasStartedChat, setHasStartedChat] = useState(false);
  const starterQuestions = useStarterQuestions();
  const [chatError, setChatError] = useState<string | null>(null);
  const [showScrollToBottom, setShowScrollToBottom] = useState(false);
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  const [sourcesPanel, setSourcesPanel] = useState<{
    nodes: SourceNode[];
    groupId?: string;
    citedIndices?: number[];
  } | null>(null);
  const scrollContainerRef = useRef<HTMLDivElement>(null);
  const showScrollToBottomRef = useRef(false);
  const lastScrollTopRef = useRef(0);
  // Set when the user submits their OWN prompt (typed or programmatic). The
  // messages effect consumes it on its next post-commit run to ALWAYS
  // smooth-scroll the just-sent prompt into view, regardless of current
  // scroll position — a user submitting always wants to see what they sent.
  // Decoupled from the effect's distance/lastMessageRole heuristic, which
  // raced (the assistant placeholder could land first, flipping
  // lastMessageRole to "assistant" before the effect ran).
  const pendingUserScrollRef = useRef(false);
  // ChatGPT-style "pin the sent prompt to the top": a bottom spacer reserves
  // just enough room so the just-sent prompt can scroll to the top, and the
  // answer streams into the space below it. `pinnedTurnRef` stays true for the
  // duration of the current turn so streaming never yanks the view to the
  // bottom; it releases when the turn finishes.
  const bottomSpacerRef = useRef<HTMLDivElement>(null);
  const pinnedTurnRef = useRef(false);
  const deviceIdRef = useRef<string>("");
  const sessionIdRef = useRef<string>(getSessionId());
  const timezoneRef = useRef<string>(getTimezone());

  // Load device fingerprint on mount (async)
  useEffect(() => {
    getDeviceId().then((id) => {
      deviceIdRef.current = id;
    });
  }, []);

  // Hydrate ui language from localStorage on mount + subscribe to changes
  // from SettingsMenu (which dispatches `user-language-pref-changed`).
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);

  const chromeStrings = getChromeStrings(uiLang);
  const isSourcesPanelOpen = Boolean(sourcesPanel?.nodes.length);

  const baseChatHeaders = useMemo(
    () => ({
      "Content-Type": "application/json",
      "X-Session-ID": sessionIdRef.current,
      "X-Timezone": timezoneRef.current,
      "X-API-Key": process.env.NEXT_PUBLIC_API_KEY ?? "",
    }),
    [],
  );

  const handleChatError = useCallback((error: unknown) => {
    if (!(error instanceof Error)) throw error;
    // Always show a friendly message — never expose raw errors to the user
    const friendlyMessage = "Something went wrong. Please try again.";
    // Extract raw detail for Sentry diagnostics only
    let rawDetail = error.message;
    try {
      const parsed = JSON.parse(error.message);
      rawDetail = parsed.detail ?? error.message;
    } catch {
      // error.message is not JSON — use as-is for Sentry
    }
    Sentry.captureException(error, {
      extra: { rawDetail },
    });
    setChatError(friendlyMessage);
  }, []);

  const {
    messages,
    input,
    isLoading,
    handleSubmit,
    handleInputChange,
    reload,
    stop,
    append,
    setInput,
    setMessages,
  } = useChat({
    api: `${backend}/api/v1/chat`,
    headers: baseChatHeaders,
    onError: handleChatError,
  });

  // Prefill the composer from `?prompt=<text>` (mirrors ChatGPT's deep-link),
  // so another page can link straight to a question. PREFILL ONLY: it does
  // not auto-send. Read in an effect (not useSearchParams) to avoid the App
  // Router Suspense requirement and any hydration mismatch.
  useEffect(() => {
    const prompt = new URLSearchParams(window.location.search).get("prompt");
    if (prompt) setInput(prompt);
  }, [setInput]);

  // Keep a ref to the latest messages so the stable edit callback can read
  // current state without being recreated on every streamed token — which
  // would defeat React.memo on ChatMessage and re-render the whole list.
  const messagesRef = useRef(messages);
  messagesRef.current = messages;

  // Streaming-jank fix (2026-06-12): the backend streams one char per SSE
  // event (~55/s), so `messages` got a new array + a new streaming-message
  // object ~55×/s. CPU-profiling the freeze showed ~43% of all time in React
  // element creation alone (jsxDEV/createElement) — render FREQUENCY, not the
  // markdown parse, was the dominant cost. Throttling the array handed to the
  // heavy ChatMessages renderer to ~11×/s holds each memoized ChatMessage's
  // `message` prop stable between flushes, so the expensive markdown subtree
  // re-renders ~11×/s instead of ~55×/s. Bypassed when NOT streaming so the
  // user's own message appears instantly and the final answer settles
  // instantly on stream end (and the appended-correction animation, which
  // runs after isLoading flips false, sees live messages). Pairs with the
  // block-memoized markdown so each of those renders is also cheaper.
  const displayMessages = useThrottledValue(messages, 90, !isLoading);

  // The request `data` the backend needs: the question and the language
  // preference. No role: the backend serves one audience and ignores any
  // client role (CLAUDE.md §7 Phase 1).
  // When the user has typed into an RTF draft, those edits live only in that
  // widget's contentEditable DOM — `messages` still holds the draft as the model
  // wrote it. Attaching the edited text here is what lets the next turn revise
  // from what the user actually has in front of them. Returns nothing when the
  // draft is untouched, so an unedited draft is not re-sent as duplicate tokens.
  // See app/lib/draft-registry.ts for why this is a registry and not context.
  const buildDraftContext = useCallback(() => {
    const snapshot = getEditedDraftSnapshot();
    if (!snapshot) return {};
    return {
      edited_draft: {
        draft_type: snapshot.draftType,
        subject: snapshot.subject,
        body: snapshot.body,
      },
    };
  }, []);

  const buildRequestData = useCallback(
    (question: string) => ({
      question,
      user_language_pref:
        typeof window !== "undefined" ? getUserLanguagePref() : "auto",
      ...buildDraftContext(),
    }),
    [buildDraftContext],
  );

  const chatRequestHeaders = useCallback(
    (extra?: Record<string, string>) => ({
      ...baseChatHeaders,
      "X-Device-ID": deviceIdRef.current,
      ...(extra ?? {}),
    }),
    [baseChatHeaders],
  );

  // Every programmatic submission (starter and suggested questions, edited
  // resubmits) goes through useChat's append(). Raw append() sends NO request
  // body, so the backend never sees `data`. appendMessage injects the SAME
  // data the typed-input path sends (language, edited draft).
  const appendMessage = useCallback(
    (
      message: Parameters<typeof append>[0],
      options?: Parameters<typeof append>[1],
    ) => {
      const content =
        typeof message?.content === "string" ? message.content : "";
      pendingUserScrollRef.current = true;
      setHasStartedChat(true);
      setChatError(null);
      return append(message, {
        ...options,
        body: { ...(options?.body ?? {}), data: buildRequestData(content) },
        headers: chatRequestHeaders(options?.headers as Record<string, string>),
      });
    },
    [append, buildRequestData, chatRequestHeaders],
  );

  // The regenerate button calls useChat's reload(), which resubmits the last
  // user message. Bare reload() also sends no body — wrap it so regenerate
  // carries the same request data as a typed submit.
  const reloadWithMode = useCallback(
    (options?: Parameters<typeof reload>[0]) => {
      const lastUser = [...messagesRef.current]
        .reverse()
        .find((m) => m.role === "user");
      const content =
        typeof lastUser?.content === "string" ? lastUser.content : "";
      setChatError(null);
      return reload({
        ...options,
        body: { ...(options?.body ?? {}), data: buildRequestData(content) },
        headers: chatRequestHeaders(options?.headers as Record<string, string>),
      });
    },
    [reload, buildRequestData, chatRequestHeaders],
  );

  // Truncate the conversation at the edited message and resubmit it.
  // `setMessages` and `appendMessage` are stable references, so this callback
  // stays stable across renders.
  const handleEditSubmit = useCallback(
    (messageId: string, content: string) => {
      const msgs = messagesRef.current;
      const index = msgs.findIndex((m) => m.id === messageId);
      if (index === -1) return;
      setMessages(msgs.slice(0, index));
      appendMessage({ role: "user", content });
    },
    [setMessages, appendMessage],
  );

  const scrollToBottom = useCallback((behavior: ScrollBehavior = "smooth") => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const prefersReducedMotion =
      window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ?? false;

    // Land at the end of the REAL content, not past the reserved bottom spacer.
    const spacerHeight = bottomSpacerRef.current?.offsetHeight ?? 0;
    container.scrollTo({
      top: container.scrollHeight - spacerHeight,
      behavior: prefersReducedMotion ? "auto" : behavior,
    });
  }, []);

  // Offset of the last user message within the scroll content (independent of
  // current scroll position). Null when there's no user message yet.
  const lastUserMessageOffset = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return null;
    const userMsgs = container.querySelectorAll<HTMLElement>(
      '[data-message-role="user"]',
    );
    const lastUser = userMsgs[userMsgs.length - 1];
    if (!lastUser) return null;
    const containerTop = container.getBoundingClientRect().top;
    return (
      container.scrollTop +
      (lastUser.getBoundingClientRect().top - containerTop)
    );
  }, []);

  // Reserve just enough space below the last user prompt that it can sit at the
  // top, then smooth-scroll it there.
  const pinLastUserMessageToTop = useCallback(
    (behavior: ScrollBehavior = "smooth") => {
      const container = scrollContainerRef.current;
      const spacer = bottomSpacerRef.current;
      if (!container) return;
      if (spacer) spacer.style.height = "0px"; // measure with no reserved space
      const offset = lastUserMessageOffset();
      if (offset == null) return;
      const contentBelow = container.scrollHeight - offset;
      const need = Math.max(
        0,
        container.clientHeight - PIN_TOP_GAP_PX - contentBelow,
      );
      if (spacer) spacer.style.height = `${need}px`;
      const prefersReducedMotion =
        window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ??
        false;
      container.scrollTo({
        top: Math.max(0, offset - PIN_TOP_GAP_PX),
        behavior: prefersReducedMotion ? "auto" : behavior,
      });
    },
    [lastUserMessageOffset],
  );

  // Keep the reserved space tight as the pinned answer streams in: it shrinks
  // toward 0 as the answer fills the viewport. Never moves scrollTop, so the
  // pinned prompt stays put.
  const resizeBottomSpacer = useCallback(() => {
    const container = scrollContainerRef.current;
    const spacer = bottomSpacerRef.current;
    if (!container || !spacer) return;
    const offset = lastUserMessageOffset();
    if (offset == null) {
      if (spacer.offsetHeight !== 0) spacer.style.height = "0px";
      return;
    }
    const currentSpacer = spacer.offsetHeight;
    const contentBelow = container.scrollHeight - currentSpacer - offset;
    const need = Math.max(
      0,
      container.clientHeight - PIN_TOP_GAP_PX - contentBelow,
    );
    if (Math.abs(need - currentSpacer) > 1) spacer.style.height = `${need}px`;
  }, [lastUserMessageOffset]);

  const updateScrollToBottomVisibility = useCallback(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    const distanceFromBottom = getDistanceFromBottom(container);
    const scrollingUp = container.scrollTop < lastScrollTopRef.current;
    lastScrollTopRef.current = container.scrollTop;

    let shouldShow = showScrollToBottomRef.current;

    if (distanceFromBottom <= SCROLL_BOTTOM_THRESHOLD_PX) {
      shouldShow = false;
    } else if (scrollingUp && distanceFromBottom >= SCROLL_BUTTON_REVEAL_PX) {
      shouldShow = true;
    }

    if (shouldShow !== showScrollToBottomRef.current) {
      showScrollToBottomRef.current = shouldShow;
      setShowScrollToBottom(shouldShow);
    }
  }, []);

  const handleScrollToLatest = useCallback(() => {
    pinnedTurnRef.current = false; // user chose the bottom — stop pinning
    scrollToBottom("smooth");
    showScrollToBottomRef.current = false;
    setShowScrollToBottom(false);
  }, [scrollToBottom]);

  const customHandleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    // Nothing to send: stay on the empty chat (greeting and starters).
    if (!input.trim()) {
      e.preventDefault();
      return;
    }
    setChatError(null);
    const data = buildRequestData(input);

    // Mark chat as started on first message
    if (!hasStartedChat) {
      setHasStartedChat(true);
    }

    pendingUserScrollRef.current = true;
    handleSubmit(e, {
      body: {
        data: data,
      },
      headers: {
        ...baseChatHeaders,
        "X-Device-ID": deviceIdRef.current,
      },
    });
  };

  // Check if there are any messages
  const hasMessages = messages.length > 0;
  const lastMessageRole = messages[messages.length - 1]?.role;

  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container || !(hasStartedChat || hasMessages)) return;

    const onScroll = () => {
      updateScrollToBottomVisibility();
    };

    lastScrollTopRef.current = container.scrollTop;
    onScroll();

    container.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      container.removeEventListener("scroll", onScroll);
    };
  }, [hasMessages, hasStartedChat, updateScrollToBottomVisibility]);

  useEffect(() => {
    const handleSourcesPanelEvent = (event: Event) => {
      const detail = (event as CustomEvent<SourcesPanelEventDetail>).detail;

      if (detail?.open && detail.nodes?.length) {
        setSourcesPanel((currentPanel) => {
          if (
            currentPanel?.groupId &&
            detail.groupId &&
            currentPanel.groupId === detail.groupId
          ) {
            return null;
          }

          return {
            nodes: detail.nodes!,
            groupId: detail.groupId,
            citedIndices: detail.citedIndices,
          };
        });
        return;
      }

      setSourcesPanel(null);
    };

    window.addEventListener(SOURCES_PANEL_EVENT, handleSourcesPanelEvent);
    return () =>
      window.removeEventListener(SOURCES_PANEL_EVENT, handleSourcesPanelEvent);
  }, []);

  // Anchor the just-sent prompt to the TOP (ChatGPT-style) on submit, then let
  // the answer stream into the reserved space below without the view chasing
  // it. Everything else keeps the normal "follow the bottom when near it."
  useEffect(() => {
    const container = scrollContainerRef.current;
    if (!container) return;

    // The user just submitted their own prompt — pin it to the top. The
    // just-sent message can be one throttled flush from the DOM, so retry
    // across a few frames until the specific latest user bubble exists.
    if (pendingUserScrollRef.current) {
      pendingUserScrollRef.current = false;
      pinnedTurnRef.current = true;
      if (showScrollToBottomRef.current) {
        showScrollToBottomRef.current = false;
        setShowScrollToBottom(false);
      }
      const targetUserId = [...messagesRef.current]
        .reverse()
        .find((message) => message.role === "user")?.id;
      let attempt = 0;
      const tryPin = () => {
        const selector = targetUserId
          ? `[data-message-role="user"][data-message-id="${CSS.escape(targetUserId)}"]`
          : '[data-message-role="user"]';
        const found = scrollContainerRef.current?.querySelector(selector);
        if (found || attempt > 8) {
          pinLastUserMessageToTop("smooth");
        } else {
          attempt += 1;
          requestAnimationFrame(tryPin);
        }
      };
      requestAnimationFrame(tryPin);
      return;
    }

    // While the current turn is pinned, never yank to the bottom — just keep
    // the reserved space tight as the answer grows beneath the pinned prompt.
    if (pinnedTurnRef.current) {
      resizeBottomSpacer();
      updateScrollToBottomVisibility();
      return;
    }

    const distanceFromBottom = getDistanceFromBottom(container);
    const shouldAutoScroll =
      distanceFromBottom <= SCROLL_BUTTON_REVEAL_PX ||
      lastMessageRole === "user";

    if (shouldAutoScroll) {
      scrollToBottom("smooth");
      if (showScrollToBottomRef.current) {
        showScrollToBottomRef.current = false;
        setShowScrollToBottom(false);
      }
      return;
    }

    updateScrollToBottomVisibility();
  }, [
    messages.length,
    isLoading,
    lastMessageRole,
    scrollToBottom,
    pinLastUserMessageToTop,
    resizeBottomSpacer,
    updateScrollToBottomVisibility,
  ]);

  // Keep the reserved space shrinking as the pinned answer streams in.
  // `displayMessages` updates ~11×/s during streaming, so this tracks growth.
  useEffect(() => {
    if (pinnedTurnRef.current) resizeBottomSpacer();
  }, [displayMessages, resizeBottomSpacer]);

  // When the turn finishes, release the pin (the next prompt re-pins) and
  // settle the reserved space to fit the final answer.
  useEffect(() => {
    if (isLoading) return;
    pinnedTurnRef.current = false;
    const id = requestAnimationFrame(() => resizeBottomSpacer());
    return () => cancelAnimationFrame(id);
  }, [isLoading, resizeBottomSpacer]);

  return (
    <div className="w-full h-full flex flex-col relative overflow-hidden">
      {/* Empty state - centered */}
      {!hasStartedChat && !hasMessages && (
        <div className="flex flex-1 items-center justify-center overflow-y-auto px-4 py-8">
          <div className="flex w-full max-w-[760px] flex-col gap-6">
            <Greeting />
            <StarterQuestions
              questions={starterQuestions}
              onAsk={(question) => appendMessage({ role: "user", content: question })}
            />
            <DisclaimerMessage />
          </div>
        </div>
      )}

      {/* Chat messages - takes remaining space */}
      {(hasStartedChat || hasMessages) && (
        <div
          ref={scrollContainerRef}
          data-sources-open={isSourcesPanelOpen ? "true" : "false"}
          // No CSS scroll-behavior here: each scrollTo() passes its own
          // behavior, "auto" under prefers-reduced-motion, which a CSS
          // "smooth" would override.
          className="pathway-chat-scroll-shell flex-1 overflow-y-auto overflow-x-hidden pl-2 pr-4 sm:px-6 md:px-8 lg:px-16 xl:px-24 2xl:px-32 pt-8 pb-44 sm:pb-48"
        >
          <div className="max-w-[760px] mx-auto">
            <ChatMessages
              messages={displayMessages}
              isLoading={isLoading}
              reload={reloadWithMode}
              stop={stop}
              append={appendMessage}
              onEditSubmit={handleEditSubmit}
            />
            {/* Reserved space so the just-sent prompt can pin to the top; the
                streaming answer fills it and it collapses as the answer grows. */}
            <div ref={bottomSpacerRef} data-bottom-spacer aria-hidden="true" />
          </div>
        </div>
      )}

      <SourcesSidebar
        open={isSourcesPanelOpen}
        nodes={sourcesPanel?.nodes ?? []}
        groupId={sourcesPanel?.groupId}
        citedIndices={sourcesPanel?.citedIndices}
        onClose={() => setSourcesPanel(null)}
      />

      {(hasStartedChat || hasMessages) && (
        <button
          type="button"
          onClick={handleScrollToLatest}
          aria-label="Scroll to latest messages"
          className={[
            "absolute left-1/2 -translate-x-1/2 z-20",
            "bottom-36 sm:bottom-36",
            "h-11 w-11 rounded-full border border-ia-border",
            "bg-ia-surface text-ia-text shadow-ia-pop",
            "transition-all duration-300 ease-[cubic-bezier(0.22,1,0.36,1)]",
            "hover:-translate-y-0.5 hover:border-ia-border-strong",
            "active:translate-y-0 active:scale-[0.97]",
            "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg",
            showScrollToBottom
              ? "opacity-100 scale-100 pointer-events-auto"
              : "opacity-0 translate-y-3 scale-95 pointer-events-none",
          ].join(" ")}
        >
          <ArrowDown className="mx-auto h-[18px] w-[18px]" />
        </button>
      )}

      {/* Compact centered error banner */}
      {chatError && (
        <div className="flex justify-center mb-2 px-4">
          {/* Error notice: Red 3 left bar; the message is text, not color alone. */}
          <div
            role="alert"
            className="flex w-full max-w-[760px] items-center gap-3 rounded-xl border border-l-4 border-ia-border border-l-ia-red-3 bg-ia-surface px-4 py-3 text-ia-text animate-error-slide-in"
          >
            <AlertTriangle aria-hidden="true" className="h-5 w-5 flex-shrink-0 text-ia-red-3" />
            <p className="flex-1 text-[15px]">{chatError}</p>
            <button
              type="button"
              onClick={() => setChatError(null)}
              className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-ia-text focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus"
              aria-label="Dismiss error"
            >
              <X aria-hidden="true" className="h-4 w-4" />
            </button>
          </div>
        </div>
      )}

      {/* Input area - positioned based on chat state */}
      <div
        data-sources-open={isSourcesPanelOpen ? "true" : "false"}
        className={`w-full border-t border-ia-border bg-ia-bg px-4 pb-5 pt-2 sm:px-6 sm:pb-6 ${
          !hasStartedChat && !hasMessages ? "static" : "sticky bottom-0"
        } pathway-chat-input-shell`}
      >
        <div className="mx-auto flex max-w-[760px] flex-col gap-3">
          <ChatInput
            input={input}
            handleSubmit={customHandleSubmit}
            handleInputChange={handleInputChange}
            isLoading={isLoading}
            messages={messages}
            append={appendMessage}
            setInput={setInput}
            stop={stop}
            inputPlaceholder={chromeStrings.inputPlaceholder}
          />

          {/* Always under the input: the student-privacy notice (CLAUDE.md
              §9.2) and the AI note. Gray 4 text at 13px (AA). */}
          <div className="flex flex-col gap-1.5" role="note">
            <p className="m-0 flex items-center gap-2 text-[13px] leading-[1.45] text-ia-text">
              <ShieldCheck aria-hidden="true" className="h-4 w-4 flex-shrink-0" />
              <span>{chromeStrings.ferpaNotice}</span>
            </p>
            <p className="m-0 text-[13px] leading-[1.45] text-ia-text">
              <span className="sm:hidden">{chromeStrings.aiNoteShort}</span>
              <span className="hidden sm:inline">{chromeStrings.aiNoteLong}</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
