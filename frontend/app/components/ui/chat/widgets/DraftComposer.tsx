"use client";

import {
  Bold,
  Check,
  Copy,
  Italic,
  Link2,
  List,
  ListOrdered,
  Send,
  Sparkles,
  Underline,
} from "lucide-react";
import Image from "next/image";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import {
  registerDraftSource,
  saveDraftEdit,
  getDraftEdit,
  type DraftSnapshot,
} from "@/app/lib/draft-registry";
import { getChromeStrings, type ChromeStrings } from "../../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../../lib/i18n";
import {
  getDeviceId,
  getSessionId,
  getTimezone,
} from "../../../../utils/session";
import { Button } from "../../button";
import { Tooltip } from "../../tooltip";
import { Toast, useToast } from "../../toast";
import { useClientConfig } from "../hooks/use-config";
import { useCopyToClipboard } from "../hooks/use-copy-to-clipboard";
import { getDraftComposerTranslations } from "../utils/localization";

interface DraftComposerProps {
  type: "email" | "message";
  content: string;
  isLoading?: boolean;
  languageCode?: string;
  // Stable key (message id + original draft) for persisting an in-place edit
  // across a remount. See app/lib/draft-registry.ts (edit store).
  persistKey?: string;
}

interface DraftEditApiResponse {
  edited_text?: string | null;
  blocked?: boolean;
  message?: string | null;
  reason?: string | null;
}

type TextStyleOption = "p" | "h1" | "h2" | "h3";
type DropdownStyleOption = TextStyleOption | "ul" | "ol";

const RICH_TEXT_FONT_FAMILY = "Georgia, 'Times New Roman', Times, serif";
const FORMAT_BLOCK_VALUE: Record<TextStyleOption, string> = {
  p: "<p>",
  h1: "<h1>",
  h2: "<h2>",
  h3: "<h3>",
};
// The style names, in the interface language.
const styleLabel = (
  strings: ChromeStrings,
  option: DropdownStyleOption,
): string =>
  ({
    p: strings.draftStyleText,
    h1: strings.draftStyleH1,
    h2: strings.draftStyleH2,
    h3: strings.draftStyleH3,
    ol: strings.draftNumberedList,
    ul: strings.draftBulletedList,
  })[option];
const STYLE_PREVIEW_OPTION_STYLE: Record<
  DropdownStyleOption,
  React.CSSProperties
> = {
  p: { fontSize: "14px", fontWeight: 400 },
  h3: { fontSize: "14px", fontWeight: 700 },
  h2: { fontSize: "15px", fontWeight: 700 },
  h1: { fontSize: "16px", fontWeight: 700 },
  ol: { fontSize: "14px", fontWeight: 500 },
  ul: { fontSize: "14px", fontWeight: 500 },
};
const ASK_INPUT_MAX_CHARS = 400;
const SUBJECT_LINE_RE =
  /^(subject|asunto|assunto|objet|oggetto|betreff|tema|assumpte|件名|主题|主旨|тема|제목)\s*:\s*(.+)$/i;

const SPANISH_SIGNAL_PATTERNS = [
  /\b(hola|estudiante|atentamente|estimad[oa]|querid[oa]|saludos?)\b/i,
  /\b(reuni[oó]n|invitaci[oó]n|aprendiz|contacto|correo|mensaje)\b/i,
  /\b(asunto)\b/i,
];

const PORTUGUESE_SIGNAL_PATTERNS = [
  /\b(ol[aá]|aluno|atenciosamente|prezad[oa]|sauda[cç][oõ]es)\b/i,
  /\b(reuni[aã]o|convite|aprendiz|contato|e-mail|mensagem)\b/i,
  /\b(assunto)\b/i,
];

const FRENCH_SIGNAL_PATTERNS = [
  /\b(bonjour|salut|cordialement|ch[eè]re?)\b/i,
  /\b(r[eé]union|invitation|[eé]tudiant|contact)\b/i,
  /\b(objet)\b/i,
];

const ITALIAN_SIGNAL_PATTERNS = [
  /\b(ciao|saluti|cordiali|gentile)\b/i,
  /\b(riunione|invito|studente|contatto)\b/i,
  /\b(oggetto)\b/i,
];

const GERMAN_SIGNAL_PATTERNS = [
  /\b(hallo|guten tag|mit freundlichen|gr[uü][sß]en)\b/i,
  /\b(einladung|treffen|sch[uü]ler|kontakt|nachricht)\b/i,
  /\b(betreff)\b/i,
];

function countPatternMatches(raw: string, patterns: RegExp[]): number {
  return patterns.reduce(
    (count, pattern) => (pattern.test(raw) ? count + 1 : count),
    0,
  );
}

function detectDraftLanguage(raw: string): string {
  if (!raw) {
    return "en";
  }

  if (/[ぁ-ゖァ-ヺ]/u.test(raw) || /件名|こんにちは|学生/u.test(raw)) {
    return "ja";
  }

  if (/[一-龯]/u.test(raw) || /主题|您好|学生/u.test(raw)) {
    return "zh";
  }

  if (/[А-Яа-яЁё]/.test(raw)) {
    return "ru";
  }

  if (countPatternMatches(raw, SPANISH_SIGNAL_PATTERNS) >= 2) {
    return "es";
  }

  if (countPatternMatches(raw, PORTUGUESE_SIGNAL_PATTERNS) >= 2) {
    return "pt";
  }

  if (countPatternMatches(raw, FRENCH_SIGNAL_PATTERNS) >= 2) {
    return "fr";
  }

  if (countPatternMatches(raw, ITALIAN_SIGNAL_PATTERNS) >= 2) {
    return "it";
  }

  if (countPatternMatches(raw, GERMAN_SIGNAL_PATTERNS) >= 2) {
    return "de";
  }

  if (/제목|안녕하세요|학생/u.test(raw)) {
    return "ko";
  }

  return "en";
}

function normalizeLanguageCode(langCode?: string): string {
  if (!langCode) {
    return "";
  }
  return langCode.toLowerCase().split("-")[0].split("_")[0].trim();
}

/** Extract subject and body from draft content. */
function parseEmailContent(raw: string): { subject: string; body: string } {
  const lines = raw.split("\n");
  let subject = "";
  let bodyStart = 0;

  for (let i = 0; i < lines.length; i++) {
    const match = lines[i].match(SUBJECT_LINE_RE);
    if (match) {
      subject = match[2].trim();
      bodyStart = i + 1;
      // skip a blank line after Subject:
      if (bodyStart < lines.length && lines[bodyStart].trim() === "") {
        bodyStart++;
      }
      break;
    }
  }

  const body = lines.slice(bodyStart).join("\n").trim();
  return { subject, body };
}

/** Build a Gmail compose URL. */
function gmailComposeUrl(subject: string, body: string): string {
  // Use Gmail's compose view route that is more stable across desktop/mobile browsers.
  const params = new URLSearchParams({
    view: "cm",
    fs: "1",
    to: "",
    su: subject,
    body,
  });
  // Outlook compose endpoints can render '+' literally, so normalize spaces to %20.
  const query = params.toString().replace(/\+/g, "%20");
  return `https://mail.google.com/mail/?${query}`;
}

/** Build an Outlook compose URL. */
function outlookComposeUrl(
  subject: string,
  body: string,
  accountType: "work" | "personal",
): string {
  const params = new URLSearchParams({ to: "", subject, body });
  const query = params.toString().replace(/\+/g, "%20");
  const baseUrl =
    accountType === "work"
      ? "https://outlook.office.com/mail/deeplink/compose"
      : "https://outlook.live.com/mail/0/deeplink/compose";
  return `${baseUrl}?${query}`;
}

export function DraftComposer({
  type,
  content,
  isLoading,
  languageCode,
  persistKey,
}: DraftComposerProps) {
  const isEmail = type === "email";
  const { backend = "" } = useClientConfig();
  const { isCopied, copyToClipboard } = useCopyToClipboard({ timeout: 2000 });
  const { show, message, type: toastType, showToast, hideToast } = useToast();
  const editorRef = useRef<HTMLDivElement>(null);
  const subjectTextareaRef = useRef<HTMLTextAreaElement>(null);
  const toolbarRef = useRef<HTMLDivElement>(null);
  const floatingToolbarRef = useRef<HTMLDivElement>(null);
  const savedSelectionRef = useRef<Range | null>(null);
  const askSelectionRef = useRef<HTMLSpanElement | null>(null);
  const hydratedContentRef = useRef<string | null>(null);
  // True once the user has typed into the draft, i.e. the DOM has diverged from
  // the `content` prop the model produced. Two jobs: it tells the chat submit
  // path there is something worth sending, and it stops a late `content` change
  // (the critic appends a correction after the draft settles) from silently
  // overwriting text the user is still working on.
  const isDirtyRef = useRef(false);

  const [sendOpen, setSendOpen] = useState(false);
  const [subjectText, setSubjectText] = useState("");
  // Live mirror of subjectText so the stable markDirty callback can persist the
  // current subject without going stale or re-subscribing on every keystroke.
  const subjectTextRef = useRef(subjectText);
  subjectTextRef.current = subjectText;
  const [isSubjectWrapped, setIsSubjectWrapped] = useState(false);
  const [textStyle, setTextStyle] = useState<DropdownStyleOption>("p");
  const [isCompactToolbar, setIsCompactToolbar] = useState(false);
  const [toolbarState, setToolbarState] = useState<{
    visible: boolean;
    top: number;
    left: number;
    mode: "format" | "ask" | "link";
    loading: boolean;
    diffMode: boolean;
  }>({
    visible: false,
    top: 0,
    left: 0,
    mode: "format",
    loading: false,
    diffMode: false,
  });
  const [prompt, setPrompt] = useState("");
  const [linkInput, setLinkInput] = useState("");
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
  const inferredLanguageCode = useMemo(
    () => detectDraftLanguage(content),
    [content],
  );
  const uiLanguage = useMemo(() => {
    const normalizedIncoming = normalizeLanguageCode(languageCode);
    if (!normalizedIncoming) {
      return inferredLanguageCode;
    }

    if (normalizedIncoming === "en" && inferredLanguageCode !== "en") {
      return inferredLanguageCode;
    }

    return normalizedIncoming;
  }, [languageCode, inferredLanguageCode]);
  const localized = useMemo(
    () => getDraftComposerTranslations(uiLanguage),
    [uiLanguage],
  );

  const streamingEmailSubject = useMemo(() => {
    if (!isEmail) return "";
    return parseEmailContent(content).subject;
  }, [content, isEmail]);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 640px)");
    const update = () => setIsCompactToolbar(media.matches);
    update();

    if (typeof media.addEventListener === "function") {
      media.addEventListener("change", update);
      return () => media.removeEventListener("change", update);
    }

    media.addListener(update);
    return () => media.removeListener(update);
  }, []);

  // Sync content from props while streaming
  useEffect(() => {
    if (!editorRef.current) return;

    const parsed = isEmail
      ? parseEmailContent(content)
      : { subject: "", body: content };
    const nextBody = isEmail ? parsed.body : content;
    const isEmptyEditor = editorRef.current.innerHTML.trim().length === 0;
    const shouldHydrate =
      isLoading ||
      hydratedContentRef.current !== content ||
      isEmptyEditor;

    // Never discard the user's own text. `content` can change after the draft
    // has settled — the critic appends a correction, and the combined
    // draft+update string is what reaches this prop — and hydrating on that
    // would wipe edits the user has not sent yet. An empty editor still
    // hydrates: there is nothing to lose, and that is the first-paint path.
    if (shouldHydrate && isDirtyRef.current && !isEmptyEditor) {
      hydratedContentRef.current = content;
      return;
    }

    if (shouldHydrate) {
      // On a fresh mount, restore an in-place edit the user made to THIS draft
      // before it was remounted (see draft-registry edit store). The key embeds
      // `content`, so a regenerated draft (new content) finds no entry and
      // hydrates normally. A restored edit stays dirty so it still transmits and
      // the dirty guard above protects it from a later content change.
      const saved = persistKey && isEmptyEditor ? getDraftEdit(persistKey) : null;
      editorRef.current.innerHTML = renderContentWithHighlights(
        saved ? saved.body : nextBody,
        { renderRichEmailFormatting: isEmail },
      );
      hydratedContentRef.current = content;
      askSelectionRef.current = null;
      isDirtyRef.current = !!saved;
      if (isEmail && !isLoading) {
        setSubjectText(saved ? saved.subject : parsed.subject);
      }
    }
  }, [content, isEmail, isLoading, persistKey]);

  // Close send dropdown on outside click
  useEffect(() => {
    if (!sendOpen) return;
    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (!toolbarRef.current?.contains(target)) {
        setSendOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [sendOpen]);

  const resizeSubjectTextarea = useCallback(() => {
    const el = subjectTextareaRef.current;
    if (!el) return;
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 128)}px`;

    const lineHeight =
      Number.parseFloat(window.getComputedStyle(el).lineHeight) || 22;
    setIsSubjectWrapped(el.scrollHeight > lineHeight + 1);
  }, []);

  useEffect(() => {
    if (!isEmail) return;
    resizeSubjectTextarea();
  }, [isEmail, resizeSubjectTextarea, subjectText]);

  useEffect(() => {
    if (!isEmail) return;

    const onResize = () => resizeSubjectTextarea();
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [isEmail, resizeSubjectTextarea]);

  const getBodyText = useCallback((): string => {
    if (editorRef.current) {
      return editorRef.current.innerText || "";
    }

    if (isEmail) {
      return parseEmailContent(content).body;
    }

    return content;
  }, [content, isEmail]);

  const getPlainText = useCallback((): string => {
    const body = getBodyText().trim();
    if (!isEmail) return body;

    const subject = subjectText.trim();
    if (!subject) return body;

    return `Subject: ${subject}\n\n${body}`;
  }, [getBodyText, isEmail, subjectText]);

  // Publish this draft so the chat submit path can send the user's edits with
  // the next turn. Without this the model receives only the message history,
  // i.e. the draft as IT wrote it, and any in-place edit is invisible.
  useEffect(() => {
    const source = {
      getSnapshot: (): DraftSnapshot | null => {
        if (!editorRef.current) return null;
        return {
          draftType: isEmail ? "email" : "message",
          subject: isEmail ? subjectText.trim() : "",
          body: (editorRef.current.innerText || "").trim(),
        };
      },
      isDirty: () => isDirtyRef.current,
    };
    return registerDraftSource(source);
  }, [isEmail, subjectText]);

  const markDirty = useCallback(() => {
    isDirtyRef.current = true;
    // Persist the edit outside the component so it survives a remount (a new
    // turn replaces this widget's DOM node). Restored on the next mount by the
    // hydration effect above, keyed by persistKey (message id + original draft).
    if (persistKey && editorRef.current) {
      saveDraftEdit(persistKey, {
        draftType: isEmail ? "email" : "message",
        subject: isEmail ? subjectTextRef.current.trim() : "",
        body: (editorRef.current.innerText || "").trim(),
      });
    }
  }, [persistKey, isEmail]);

  const onCopy = () => {
    if (isCopied) return;
    copyToClipboard(getPlainText());
  };

  /** Save the current selection so it persists when toolbar steals focus. */
  const saveSelection = useCallback(() => {
    const sel = window.getSelection();
    if (sel && sel.rangeCount > 0 && !sel.isCollapsed) {
      savedSelectionRef.current = sel.getRangeAt(0).cloneRange();
    }
  }, []);

  /** Restore a previously saved selection. */
  const restoreSelection = useCallback(() => {
    const range = savedSelectionRef.current;
    if (!range) return;
    const sel = window.getSelection();
    if (sel) {
      sel.removeAllRanges();
      sel.addRange(range);
    }
  }, []);

  const clearAskSelectionHighlight = useCallback(() => {
    const marker = askSelectionRef.current;
    if (!marker || !marker.parentNode) return;

    const parent = marker.parentNode;
    while (marker.firstChild) {
      parent.insertBefore(marker.firstChild, marker);
    }
    parent.removeChild(marker);
    askSelectionRef.current = null;
  }, []);

  const highlightSelectionForAsk = useCallback((): boolean => {
    clearAskSelectionHighlight();
    restoreSelection();

    const selection = window.getSelection();
    if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
      return false;
    }

    const range = selection.getRangeAt(0);
    if (!editorRef.current?.contains(range.commonAncestorContainer)) {
      return false;
    }

    const marker = document.createElement("span");
    marker.className =
      "bg-[#FFE8A3]/90 dark:bg-[#5C4A1A]/60 text-inherit rounded px-0.5 break-words";

    try {
      range.surroundContents(marker);
    } catch {
      const fragment = range.extractContents();
      marker.appendChild(fragment);
      range.insertNode(marker);
    }

    askSelectionRef.current = marker;

    const nextRange = document.createRange();
    nextRange.selectNodeContents(marker);
    savedSelectionRef.current = nextRange.cloneRange();
    selection.removeAllRanges();
    selection.addRange(nextRange);
    return true;
  }, [clearAskSelectionHighlight, restoreSelection]);

  const cancelLinkMode = useCallback(() => {
    setLinkInput("");
    setToolbarState((s) => {
      if (s.mode !== "link") return s;
      return { ...s, mode: "format", visible: false };
    });
  }, []);

  const closeFloatingToolbar = useCallback(() => {
    clearAskSelectionHighlight();
    setPrompt("");
    setLinkInput("");
    setToolbarState((s) => ({
      ...s,
      visible: false,
      mode: "format",
      loading: false,
      diffMode: false,
    }));
  }, [clearAskSelectionHighlight]);

  const getSelectionStyle = useCallback((range: Range): DropdownStyleOption => {
    const editor = editorRef.current;
    if (!editor) return "p";

    const node =
      range.startContainer.nodeType === Node.ELEMENT_NODE
        ? (range.startContainer as Element)
        : range.startContainer.parentElement;
    if (!node || !editor.contains(node)) {
      return "p";
    }

    const block = node.closest("h1,h2,h3,ul,ol,li,p");
    if (!block) return "p";

    const tag = block.tagName.toLowerCase();
    if (tag === "h1" || tag === "h2" || tag === "h3" || tag === "p") {
      return tag;
    }
    if (tag === "ul" || tag === "ol") {
      return tag;
    }
    if (tag === "li") {
      const listParent = block.closest("ul,ol");
      if (listParent?.tagName.toLowerCase() === "ol") return "ol";
      if (listParent?.tagName.toLowerCase() === "ul") return "ul";
    }
    return "p";
  }, []);

  const handleSelection = useCallback(() => {
    const selection = window.getSelection();
    if (
      !selection ||
      selection.isCollapsed ||
      !editorRef.current?.contains(selection.anchorNode)
    ) {
      // Don't hide toolbar if in ask mode, link mode, or diff mode.
      if (
        toolbarState.mode !== "ask" &&
        toolbarState.mode !== "link" &&
        !toolbarState.diffMode
      ) {
        setToolbarState((s) => ({ ...s, visible: false }));
      }
      return;
    }

    saveSelection();
    clearAskSelectionHighlight();

    const range = selection.getRangeAt(0);
    setTextStyle(getSelectionStyle(range));
    const rect = range.getBoundingClientRect();

    setToolbarState((s) => ({
      ...s,
      visible: true,
      mode: "format",
      top: rect.top - 44,
      left: rect.left + rect.width / 2 - 100,
    }));
  }, [
    toolbarState.mode,
    toolbarState.diffMode,
    saveSelection,
    clearAskSelectionHighlight,
    getSelectionStyle,
  ]);

  // Keep floating toolbar in viewport bounds and recalculate on resize.
  useEffect(() => {
    if (!toolbarState.visible) return;

    const toolbarEl = floatingToolbarRef.current;
    if (!toolbarEl) return;

    const edgePadding = 8;

    const clampLeftToViewport = () => {
      const toolbarWidth = toolbarEl.offsetWidth;
      const minLeft = edgePadding;
      const rawMaxLeft = window.innerWidth - edgePadding - toolbarWidth;
      const maxLeft = Math.max(minLeft, rawMaxLeft);
      const clampedLeft = Math.max(
        minLeft,
        Math.min(toolbarState.left, maxLeft),
      );

      if (Math.abs(clampedLeft - toolbarState.left) > 0.5) {
        setToolbarState((s) =>
          Math.abs(s.left - clampedLeft) > 0.5
            ? { ...s, left: clampedLeft }
            : s,
        );
      }
    };

    clampLeftToViewport();
    window.addEventListener("resize", clampLeftToViewport);
    return () => window.removeEventListener("resize", clampLeftToViewport);
  }, [
    toolbarState.visible,
    toolbarState.left,
    toolbarState.mode,
    toolbarState.diffMode,
    toolbarState.loading,
    isCompactToolbar,
    textStyle,
    prompt,
    linkInput,
  ]);

  // Dismiss the floating toolbar when clicking outside it.
  // For format mode, keep in-editor click behavior controlled by selection changes.
  // For ask/link/diff modes, any click outside the toolbar should close immediately.
  useEffect(() => {
    if (!toolbarState.visible) return;

    const handler = (e: MouseEvent) => {
      const target = e.target as Node;
      if (floatingToolbarRef.current?.contains(target)) return;

      if (
        toolbarState.mode === "ask" ||
        toolbarState.mode === "link" ||
        toolbarState.diffMode
      ) {
        closeFloatingToolbar();
        return;
      }

      const clickedInsideEditor = editorRef.current?.contains(target);
      if (!clickedInsideEditor) {
        closeFloatingToolbar();
      }
    };

    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [
    toolbarState.visible,
    toolbarState.mode,
    toolbarState.diffMode,
    closeFloatingToolbar,
  ]);

  const applyFormat = useCallback(
    (command: string, value?: string) => {
      restoreSelection();
      document.execCommand(command, false, value);
      saveSelection();
    },
    [restoreSelection, saveSelection],
  );

  const applyTextStyle = useCallback(
    (nextStyle: DropdownStyleOption) => {
      if (nextStyle === "ul") {
        applyFormat("insertUnorderedList");
        setTextStyle("ul");
        return;
      }
      if (nextStyle === "ol") {
        applyFormat("insertOrderedList");
        setTextStyle("ol");
        return;
      }

      setTextStyle(nextStyle);
      applyFormat("formatBlock", FORMAT_BLOCK_VALUE[nextStyle]);
    },
    [applyFormat],
  );

  const openLinkMode = useCallback(() => {
    clearAskSelectionHighlight();
    restoreSelection();
    const selection = window.getSelection();
    if (
      !selection ||
      selection.rangeCount === 0 ||
      selection.isCollapsed ||
      !editorRef.current?.contains(
        selection.getRangeAt(0).commonAncestorContainer,
      )
    ) {
      showToast(chromeStrings.draftLinkSelectFirstToast, "error");
      setToolbarState((s) => ({ ...s, mode: "format", visible: false }));
      return;
    }

    setLinkInput("");
    setToolbarState((s) => ({ ...s, mode: "link", visible: true }));
  }, [
    clearAskSelectionHighlight,
    restoreSelection,
    showToast,
    chromeStrings.draftLinkSelectFirstToast,
  ]);

  const applyLink = useCallback(() => {
    const trimmed = linkInput.trim();
    if (!trimmed) return;

    const normalized = /^(https?:\/\/|mailto:)/i.test(trimmed)
      ? trimmed
      : `https://${trimmed}`;

    if (!/^(https?:\/\/|mailto:)/i.test(normalized)) {
      showToast(chromeStrings.draftLinkInvalidUrlToast, "error");
      return;
    }

    restoreSelection();
    const selection = window.getSelection();
    if (
      !selection ||
      selection.rangeCount === 0 ||
      selection.isCollapsed ||
      !editorRef.current?.contains(
        selection.getRangeAt(0).commonAncestorContainer,
      )
    ) {
      showToast(chromeStrings.draftLinkSelectFirstToast, "error");
      setToolbarState((s) => ({ ...s, mode: "format", visible: false }));
      return;
    }

    document.execCommand("createLink", false, normalized);
    saveSelection();
    setLinkInput("");
    setToolbarState((s) => ({ ...s, mode: "format", visible: false }));
  }, [
    linkInput,
    restoreSelection,
    saveSelection,
    showToast,
    chromeStrings.draftLinkInvalidUrlToast,
    chromeStrings.draftLinkSelectFirstToast,
  ]);

  const askForChange = useCallback(async () => {
    const instruction = prompt.trim().slice(0, ASK_INPUT_MAX_CHARS);
    if (!instruction) return;

    let selectedText = "";
    let selectedRange: Range | null = null;

    if (askSelectionRef.current) {
      selectedText = askSelectionRef.current.textContent || "";
      selectedRange = document.createRange();
      selectedRange.selectNode(askSelectionRef.current);
    } else {
      restoreSelection();
      const selection = window.getSelection();
      if (!selection || selection.rangeCount === 0 || selection.isCollapsed) {
        setToolbarState((s) => ({ ...s, mode: "format", visible: false }));
        return;
      }
      selectedRange = selection.getRangeAt(0);
      selectedText = selectedRange.toString();
    }

    if (!selectedText.trim() || !selectedRange) {
      setToolbarState((s) => ({ ...s, mode: "format", visible: false }));
      return;
    }

    setToolbarState((s) => ({ ...s, loading: true }));

    try {
      if (!backend) {
        throw new Error("Missing backend configuration");
      }

      const deviceId = await getDeviceId();

      const response = await fetch(`${backend}/api/v1/chat/draft/edit`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-API-Key": process.env.NEXT_PUBLIC_API_KEY ?? "",
          "X-Session-ID": getSessionId(),
          "X-Device-ID": deviceId,
          "X-Timezone": getTimezone(),
        },
        body: JSON.stringify({
          draft_type: type,
          instruction,
          selected_text: selectedText,
          full_content: getPlainText(),
          subject: isEmail ? subjectText.trim() : undefined,
        }),
      });

      let payload: DraftEditApiResponse = {};
      try {
        payload = (await response.json()) as DraftEditApiResponse;
      } catch {
        payload = {};
      }

      if (!response.ok) {
        throw new Error(payload.message || "Failed to apply edit");
      }

      const updatedText = (payload.edited_text || "").trim();
      if (payload.blocked || !updatedText) {
        // Surface the backend's specific per-reason message (e.g. the
        // security-block message, or "Selected text is too long...").
        // Fall back to the generic toast only when the backend did not
        // send one (e.g. an empty rewrite with no rejection message).
        const backendMessage = (payload.message || "").trim();
        showToast(
          backendMessage || chromeStrings.draftTweakErrorToast,
          "error",
        );
        setToolbarState((s) => ({
          ...s,
          loading: false,
          mode: "ask",
          visible: true,
        }));
        return;
      }

      const fragment = document.createDocumentFragment();

      const del = document.createElement("del");
      del.className =
        "text-gray-400 dark:text-gray-500 bg-gray-100 dark:bg-gray-800 line-through mx-0.5 px-0.5 rounded";
      del.textContent = selectedText;

      const ins = document.createElement("ins");
      ins.className =
        "text-[#7A5600] dark:text-[#FFC328] bg-[#FFF4D6] dark:bg-[#3A3120] no-underline mx-0.5 px-0.5 rounded";
      ins.textContent = updatedText;

      fragment.appendChild(del);
      fragment.appendChild(ins);
      selectedRange.deleteContents();
      selectedRange.insertNode(fragment);
      askSelectionRef.current = null;

      setToolbarState((s) => ({
        ...s,
        loading: false,
        diffMode: true,
        mode: "format",
      }));

      setPrompt("");
    } catch {
      // Transient/network failure (fetch rejected, bad config). The backend
      // produced no usable per-reason message here, so keep the generic toast
      // rather than leaking a raw browser error string to the user.
      showToast(chromeStrings.draftTweakErrorToast, "error");
      setToolbarState((s) => ({
        ...s,
        loading: false,
        mode: "ask",
        visible: true,
      }));
    }
  }, [
    backend,
    getPlainText,
    isEmail,
    prompt,
    restoreSelection,
    showToast,
    subjectText,
    type,
    chromeStrings.draftTweakErrorToast,
  ]);

  const acceptDiff = useCallback(() => {
    if (!editorRef.current) return;
    clearAskSelectionHighlight();
    editorRef.current.querySelectorAll("del").forEach((el) => el.remove());
    editorRef.current.querySelectorAll("ins").forEach((el) => {
      const text = document.createTextNode(el.textContent || "");
      el.parentNode?.replaceChild(text, el);
    });
    setToolbarState((s) => ({ ...s, diffMode: false, visible: false }));
  }, [clearAskSelectionHighlight]);

  const undoDiff = useCallback(() => {
    if (!editorRef.current) return;
    clearAskSelectionHighlight();
    editorRef.current.querySelectorAll("ins").forEach((el) => el.remove());
    editorRef.current.querySelectorAll("del").forEach((el) => {
      const text = document.createTextNode(el.textContent || "");
      el.parentNode?.replaceChild(text, el);
    });
    setToolbarState((s) => ({ ...s, diffMode: false, visible: false }));
  }, [clearAskSelectionHighlight]);

  const handleSend = useCallback(
    (provider: "gmail" | "outlookWork" | "outlookPersonal") => {
      if (!isEmail) return;
      const subject = subjectText.trim();
      const body = getBodyText().trim();
      let url = gmailComposeUrl(subject, body);
      if (provider === "outlookWork") {
        url = outlookComposeUrl(subject, body, "work");
      } else if (provider === "outlookPersonal") {
        url = outlookComposeUrl(subject, body, "personal");
      }
      window.open(url, "_blank");
      setSendOpen(false);
    },
    [getBodyText, isEmail, subjectText],
  );

  const showSkeleton = Boolean(isLoading && content.trim().length === 0);
  const selectValue: TextStyleOption | DropdownStyleOption =
    !isCompactToolbar && (textStyle === "ul" || textStyle === "ol")
      ? "p"
      : textStyle;
  const askButtonLabel = chromeStrings.draftTweak;

  return (
    <div className="mt-4 mb-4 max-w-full flex flex-col rounded-2xl overflow-visible border border-gray-200/90 dark:border-gray-700/60 bg-white dark:bg-[#1a1f2b] shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-2.5 border-b border-gray-100 dark:border-gray-700/50 bg-gray-50/70 dark:bg-[#1e2430]">
        <div className="text-sm font-semibold tracking-tight text-gray-700 dark:text-gray-200">
          {isEmail ? localized.emailLabel : localized.messageLabel}
        </div>
        <div className="relative flex items-center gap-1" ref={toolbarRef}>
          <Tooltip label={isCopied ? chromeStrings.draftCopied : chromeStrings.draftCopy} side="bottom" align="end">
          <button
            onClick={onCopy}
            aria-label={isCopied ? chromeStrings.draftCopied : chromeStrings.draftCopy}
            className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
          >
            {isCopied ? (
              <Check className="w-4 h-4 text-green-500" />
            ) : (
              <Copy className="w-4 h-4" />
            )}
          </button>
          </Tooltip>

          {isEmail && (
            <Tooltip label={chromeStrings.draftSend} side="bottom" align="end">
            <button
              onClick={() => setSendOpen((v) => !v)}
              className="p-1.5 rounded-md text-gray-400 hover:text-gray-600 dark:text-gray-500 dark:hover:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700/50 transition-colors"
              aria-label={chromeStrings.draftSend}
            >
              <Send className="w-4 h-4" />
            </button>
            </Tooltip>
          )}

          {/* Send dropdown */}
          {isEmail && sendOpen && (
            <div className="absolute right-0 top-full mt-2 z-20 min-w-[200px] rounded-2xl border border-black/10 dark:border-white/10 bg-white/95 dark:bg-[#242628]/95 shadow-[0_18px_40px_rgba(0,0,0,0.2)] backdrop-blur-xl p-1.5 font-sans">
              <button
                className="flex items-center gap-3 w-full rounded-xl px-3 py-2.5 text-left text-[15px] font-sans font-medium text-[#3D3D3A] dark:text-[#F3F4F6] hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                onClick={() => handleSend("gmail")}
              >
                <span className="inline-flex h-[18px] w-[18px] items-center justify-center shrink-0">
                  <Image
                    src="/gmail.png"
                    alt=""
                    aria-hidden
                    width={18}
                    height={18}
                    className="h-full w-full object-contain"
                  />
                </span>
                Gmail
              </button>
              <button
                className="flex items-center gap-3 w-full rounded-xl px-3 py-2.5 text-left text-[15px] font-sans font-medium text-[#3D3D3A] dark:text-[#F3F4F6] hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                onClick={() => handleSend("outlookWork")}
              >
                <span className="inline-flex h-[18px] w-[18px] items-center justify-center shrink-0">
                  <Image
                    src="/ms-outlook.svg"
                    alt=""
                    aria-hidden
                    width={18}
                    height={18}
                    className="h-full w-full object-contain"
                  />
                </span>
                {chromeStrings.draftOutlookWork}
              </button>
              <button
                className="flex items-center gap-3 w-full rounded-xl px-3 py-2.5 text-left text-[15px] font-sans font-medium text-[#3D3D3A] dark:text-[#F3F4F6] hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
                onClick={() => handleSend("outlookPersonal")}
              >
                <span className="inline-flex h-[18px] w-[18px] items-center justify-center shrink-0">
                  <Image
                    src="/ms-outlook.svg"
                    alt=""
                    aria-hidden
                    width={18}
                    height={18}
                    className="h-full w-full object-contain"
                  />
                </span>
                {chromeStrings.draftOutlookPersonal}
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Editor Body */}
      <div className="relative">
        {showSkeleton ? (
          <DraftSkeleton isEmail={isEmail} />
        ) : (
          <>
            {isEmail && (
              <div className="px-4 pt-3 pb-2">
                <div
                  className={`flex gap-2 rounded-md border border-gray-200/70 dark:border-gray-700/70 bg-gray-50/70 dark:bg-white/[0.03] px-2.5 py-1.5 ${isSubjectWrapped ? "items-start" : "items-center"}`}
                >
                  <span
                    className={`${isSubjectWrapped ? "pt-1" : ""} text-[15px] font-bold text-gray-700 dark:text-gray-300 shrink-0`}
                  >
                    {localized.subjectLabel}
                  </span>
                  <textarea
                    ref={subjectTextareaRef}
                    value={isLoading ? streamingEmailSubject : subjectText}
                    onChange={(e) => {
                      // Update the mirror first so markDirty persists THIS
                      // keystroke's subject, not the previous render's.
                      subjectTextRef.current = e.target.value;
                      markDirty();
                      setSubjectText(e.target.value);
                    }}
                    onInput={resizeSubjectTextarea}
                    disabled={Boolean(isLoading)}
                    placeholder={localized.addSubjectPlaceholder}
                    rows={1}
                    className="flex-1 min-w-0 bg-transparent border-none outline-none text-[16px] leading-[1.4] font-medium text-gray-700 dark:text-gray-300 placeholder:text-gray-400 dark:placeholder:text-gray-500 disabled:opacity-80 resize-none overflow-hidden whitespace-pre-wrap break-words"
                    style={{
                      fontFamily: RICH_TEXT_FONT_FAMILY,
                      overflowWrap: "anywhere",
                      wordBreak: "break-word",
                    }}
                  />
                </div>
                <div className="mt-2 h-px bg-gradient-to-r from-gray-300/80 via-gray-300/40 to-transparent dark:from-gray-600/90 dark:via-gray-500/30 dark:to-transparent" />
              </div>
            )}

            <div
              ref={editorRef}
              contentEditable={!isLoading}
              onInput={markDirty}
              onMouseUp={handleSelection}
              onKeyUp={handleSelection}
              className={`
                px-4 ${isEmail ? "pb-4 pt-1" : "py-4"} text-[16px] leading-[1.72] whitespace-pre-wrap
                break-words text-gray-800 dark:text-gray-200
                [&_h1]:text-[30px] [&_h1]:leading-[1.2] [&_h1]:font-semibold [&_h1]:my-2
                [&_h2]:text-[24px] [&_h2]:leading-[1.25] [&_h2]:font-semibold [&_h2]:my-2
                [&_h3]:text-[20px] [&_h3]:leading-[1.3] [&_h3]:font-semibold [&_h3]:my-2
                [&_ul]:list-disc [&_ul]:pl-6 [&_ul]:my-2
                [&_ol]:list-decimal [&_ol]:pl-6 [&_ol]:my-2
                [&_li]:my-1
                focus:outline-none
                ${!isLoading ? "cursor-text caret-[#B07D00] dark:caret-[#FFC328]" : ""}
              `}
              style={{
                minHeight: 140,
                wordBreak: "break-word",
                overflowWrap: "anywhere",
                overflowX: "hidden",
                fontFamily: RICH_TEXT_FONT_FAMILY,
              }}
              suppressContentEditableWarning
              spellCheck
            />
          </>
        )}

        {/* Floating Toolbar */}
        {toolbarState.visible && !showSkeleton && (
          <div
            ref={floatingToolbarRef}
            className="fixed z-20 max-w-[calc(100vw-16px)] overflow-hidden flex items-center bg-white dark:bg-gray-800 shadow-lg border border-gray-200 dark:border-gray-600 rounded-lg p-1 gap-0.5 text-sm animate-in fade-in duration-150"
            style={{
              top: Math.max(4, toolbarState.top),
              left: toolbarState.left,
            }}
            onMouseDown={(e) => {
              const target = e.target as HTMLElement;
              if (target.closest("input, textarea, select, option")) {
                return;
              }
              e.preventDefault();
            }}
          >
            {toolbarState.diffMode ? (
              <div className="flex gap-1 items-center px-1">
                <span className="text-xs text-gray-500 dark:text-gray-400 mr-1">
                  {chromeStrings.draftAcceptOrUndo}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-green-600 dark:text-green-400 hover:bg-green-50 dark:hover:bg-green-900/30"
                  onClick={acceptDiff}
                >
                  {chromeStrings.draftAccept}
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/30"
                  onClick={undoDiff}
                >
                  {chromeStrings.draftUndo}
                </Button>
              </div>
            ) : toolbarState.mode === "format" ? (
              <>
                {isEmail && (
                  <>
                    <select
                      value={selectValue}
                      onChange={(e) =>
                        applyTextStyle(e.target.value as DropdownStyleOption)
                      }
                      className="h-7 w-[96px] sm:w-[118px] rounded border border-gray-200 dark:border-gray-600 bg-white dark:bg-gray-800 px-1.5 text-[14px] text-gray-700 dark:text-gray-200 outline-none cursor-pointer"
                      title={chromeStrings.draftTextStyle.replace("{style}", styleLabel(chromeStrings, textStyle))}
                    >
                      <option value="p" style={STYLE_PREVIEW_OPTION_STYLE.p}>
                        {chromeStrings.draftStyleText}
                      </option>
                      <option value="h1" style={STYLE_PREVIEW_OPTION_STYLE.h1}>
                        {chromeStrings.draftStyleH1}
                      </option>
                      <option value="h2" style={STYLE_PREVIEW_OPTION_STYLE.h2}>
                        {chromeStrings.draftStyleH2}
                      </option>
                      <option value="h3" style={STYLE_PREVIEW_OPTION_STYLE.h3}>
                        {chromeStrings.draftStyleH3}
                      </option>
                      {isCompactToolbar && (
                        <>
                          <option
                            value="ol"
                            style={STYLE_PREVIEW_OPTION_STYLE.ol}
                          >
                            {chromeStrings.draftNumberedList}
                          </option>
                          <option
                            value="ul"
                            style={STYLE_PREVIEW_OPTION_STYLE.ul}
                          >
                            {chromeStrings.draftBulletedList}
                          </option>
                        </>
                      )}
                    </select>
                    <div className="w-px h-5 bg-gray-200 dark:bg-gray-600 mx-0.5" />
                  </>
                )}

                <Tooltip label={chromeStrings.draftBold} side="top">
                <button
                  className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applyFormat("bold");
                  }}
                  aria-label={chromeStrings.draftBold}
                >
                  <Bold className="w-4 h-4" />
                </button>
                </Tooltip>
                <Tooltip label={chromeStrings.draftItalic} side="top">
                <button
                  className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applyFormat("italic");
                  }}
                  aria-label={chromeStrings.draftItalic}
                >
                  <Italic className="w-4 h-4" />
                </button>
                </Tooltip>
                <Tooltip label={chromeStrings.draftUnderline} side="top">
                <button
                  className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    applyFormat("underline");
                  }}
                  aria-label={chromeStrings.draftUnderline}
                >
                  <Underline className="w-4 h-4" />
                </button>
                </Tooltip>

                {!isCompactToolbar && (
                  <>
                    <Tooltip label={chromeStrings.draftBulletedList} side="top">
                    <button
                      className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        applyTextStyle("ul");
                      }}
                      aria-label={chromeStrings.draftBulletedList}
                    >
                      <List className="w-4 h-4" />
                    </button>
                    </Tooltip>

                    <Tooltip label={chromeStrings.draftNumberedList} side="top">
                    <button
                      className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                      onMouseDown={(e) => {
                        e.preventDefault();
                        applyTextStyle("ol");
                      }}
                      aria-label={chromeStrings.draftNumberedList}
                    >
                      <ListOrdered className="w-4 h-4" />
                    </button>
                    </Tooltip>
                  </>
                )}

                {isEmail && (
                  <Tooltip label={chromeStrings.draftInsertLink} side="top">
                  <button
                    className="p-1.5 rounded hover:bg-gray-100 dark:hover:bg-gray-700 text-gray-600 dark:text-gray-300 transition-colors"
                    onMouseDown={(e) => {
                      e.preventDefault();
                      openLinkMode();
                    }}
                    aria-label={chromeStrings.draftInsertLink}
                  >
                    <Link2 className="w-4 h-4" />
                  </button>
                  </Tooltip>
                )}

                <div className="w-px h-5 bg-gray-200 dark:bg-gray-600 mx-0.5" />
                <button
                  className="flex items-center min-w-0 max-w-[68px] sm:max-w-none gap-1 px-1.5 sm:px-2 py-1.5 rounded text-xs font-medium text-[#7A5600] dark:text-[#FFC328] hover:bg-[#FFF4D6] dark:hover:bg-[#3A3120] transition-colors"
                  onMouseDown={(e) => {
                    e.preventDefault();
                    if (!highlightSelectionForAsk()) {
                      setToolbarState((s) => ({ ...s, visible: false }));
                      return;
                    }
                    setToolbarState((s) => ({ ...s, mode: "ask" }));
                  }}
                  title={chromeStrings.draftTweak}
                >
                  <Sparkles className="w-3.5 h-3.5 shrink-0" />
                  <span className="truncate">{askButtonLabel}</span>
                </button>
              </>
            ) : toolbarState.mode === "ask" ? (
              <div className="flex items-center gap-1.5 px-1">
                <input
                  autoFocus
                  type="text"
                  placeholder={chromeStrings.draftTweakPlaceholder}
                  className="text-sm bg-transparent border-none outline-none w-44 px-1 text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500"
                  maxLength={ASK_INPUT_MAX_CHARS}
                  value={prompt}
                  onChange={(e) =>
                    setPrompt(e.target.value.slice(0, ASK_INPUT_MAX_CHARS))
                  }
                  onKeyDown={(e) => e.key === "Enter" && askForChange()}
                />
                <button
                  className="px-2 py-1 rounded text-xs font-medium bg-[#FFC328] hover:bg-[#F5B400] text-[#1F1E1D] disabled:opacity-40 transition-colors"
                  disabled={toolbarState.loading || !prompt.trim()}
                  onClick={askForChange}
                >
                  {toolbarState.loading ? chromeStrings.draftApplying : chromeStrings.draftApply}
                </button>
                {toolbarState.loading && (
                  <span className="h-3 w-3 rounded-full border-2 border-gray-300 border-t-[#E0A400] animate-spin" />
                )}
              </div>
            ) : (
              <div className="flex items-center gap-1.5 px-1">
                <input
                  autoFocus
                  type="url"
                  placeholder={chromeStrings.draftLinkPlaceholder}
                  className="text-sm bg-transparent border-none outline-none w-36 sm:w-44 px-1 text-gray-700 dark:text-gray-200 placeholder-gray-400 dark:placeholder-gray-500"
                  value={linkInput}
                  onChange={(e) => setLinkInput(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      applyLink();
                    } else if (e.key === "Escape") {
                      cancelLinkMode();
                    }
                  }}
                />
                <button
                  className="px-2 py-1 rounded text-xs font-medium bg-[#FFC328] hover:bg-[#F5B400] text-[#1F1E1D] disabled:opacity-40 transition-colors"
                  disabled={!linkInput.trim()}
                  onClick={applyLink}
                >
                  {chromeStrings.draftInsert}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      <Toast
        message={message}
        show={show}
        type={toastType}
        onClose={hideToast}
      />
    </div>
  );
}

const PLACEHOLDER_TOKEN_RE =
  /\[(?!https?:\/\/)(?!mailto:)(?=[^\]\n]*[\p{L}])([^\]\n]{1,80})\]/gu;
const MARKDOWN_LINK_RE = /\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g;
const BARE_URL_RE = /(^|[\s(>])(https?:\/\/[^\s<)]+)/g;

function renderContentWithHighlights(
  text: string,
  options?: { renderRichEmailFormatting?: boolean },
): string {
  const safeText = escapeHtml(text);
  const formattedText = options?.renderRichEmailFormatting
    ? normalizeEmailMarkdownToHtml(safeText)
    : safeText;

  return formattedText
    .replace(
      PLACEHOLDER_TOKEN_RE,
      '<span class="bg-[#FFF4D6] dark:bg-[#3A3120] text-[#5C4100] dark:text-[#FFE8A3] px-1 rounded font-medium">[$1]</span>',
    )
    .replace(/\n/g, "<br />");
}

function normalizeEmailMarkdownToHtml(escapedText: string): string {
  const linkTokens: Array<{ token: string; html: string }> = [];
  let linkTokenIndex = 0;
  let normalized = escapedText.replace(
    MARKDOWN_LINK_RE,
    (match, label: string, href: string) => {
      const sanitizedHref = sanitizeHref(href);
      if (!sanitizedHref) {
        return match;
      }

      const token = `__DRAFT_LINK_${linkTokenIndex++}__`;
      linkTokens.push({
        token,
        html: buildDraftLinkHtml(sanitizedHref, label),
      });
      return token;
    },
  );

  normalized = normalized.replace(
    BARE_URL_RE,
    (match, prefix: string, href: string) => {
      const { cleanHref, trailingPunctuation } =
        splitTrailingUrlPunctuation(href);
      const sanitizedHref = sanitizeHref(cleanHref);
      if (!sanitizedHref) {
        return match;
      }

      const token = `__DRAFT_LINK_${linkTokenIndex++}__`;
      linkTokens.push({
        token,
        html: buildDraftLinkHtml(sanitizedHref, cleanHref),
      });
      return `${prefix}${token}${trailingPunctuation}`;
    },
  );

  normalized = normalized
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[\s(])\*([^*\n]+)\*(?=$|[\s).,!?:;])/g, "$1<em>$2</em>")
    .replace(/(^|[\s(])_([^_\n]+)_(?=$|[\s).,!?:;])/g, "$1<em>$2</em>");

  for (const { token, html } of linkTokens) {
    normalized = normalized.split(token).join(html);
  }

  return normalized;
}

function sanitizeHref(href: string): string | null {
  const trimmed = href.trim();
  if (!trimmed) {
    return null;
  }

  if (!/^(https?:\/\/|mailto:)/i.test(trimmed)) {
    return null;
  }

  return trimmed;
}

function splitTrailingUrlPunctuation(href: string): {
  cleanHref: string;
  trailingPunctuation: string;
} {
  const match = href.match(/^(.*?)([.,!?;:]+)?$/);
  if (!match) {
    return { cleanHref: href, trailingPunctuation: "" };
  }

  return {
    cleanHref: match[1] || href,
    trailingPunctuation: match[2] || "",
  };
}

function buildDraftLinkHtml(href: string, label: string): string {
  return `<a href="${href}" target="_blank" rel="noopener noreferrer" class="text-[#7A5600] dark:text-[#FFC328] underline underline-offset-2">${label}</a>`;
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/\"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function DraftSkeleton({ isEmail }: { isEmail: boolean }) {
  return (
    <div className="px-4 py-4 animate-pulse" style={{ minHeight: 140 }}>
      {isEmail && (
        <>
          <div className="flex items-center gap-2 mb-2">
            <div className="h-4 w-14 rounded bg-gray-200 dark:bg-gray-700" />
            <div className="h-4 flex-1 rounded bg-gray-200 dark:bg-gray-700" />
          </div>
          <div className="mb-3 h-px bg-gradient-to-r from-gray-200 via-gray-200/40 to-transparent dark:from-gray-700 dark:via-gray-600/30 dark:to-transparent" />
        </>
      )}
      <div className="space-y-2">
        <div className="h-3.5 w-full rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-3.5 w-11/12 rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-3.5 w-10/12 rounded bg-gray-200 dark:bg-gray-700" />
        <div className="h-3.5 w-8/12 rounded bg-gray-200 dark:bg-gray-700" />
      </div>
    </div>
  );
}
