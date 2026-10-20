// frontend/app/lib/chrome-strings.ts
//
// Strings for the app chrome (header, input notes, settings, feedback,
// sources). The UI is English (CLAUDE.md §13 Q12); answers still follow the
// language of the question. The translation mechanism stays: add a language
// to CHROME_STRINGS and it is used; any language not listed falls back to
// English. (Upstream's translations were not carried over: they describe a
// different assistant.)

import type { LangCode } from "./i18n";

export interface ChromeStrings {
  // Header
  headerTitle: string; // "Instructor Assistant"
  // Chat input
  inputPlaceholder: string;
  inputPlaceholderShort: string; // phones, where the long one would be cut off
  // Notes under the chat input: student privacy (CLAUDE.md §9.2) and the AI note
  ferpaNotice: string; // "Don't include student names, IDs, or grades."
  aiNoteShort: string; // mobile, ~5-6 words
  aiNoteLong: string; // sm+ breakpoint, full sentence
  // Settings menu
  settingsTitle: string; // "Settings"
  settingsTheme: string; // "Theme"
  settingsLanguage: string; // "Language"
  settingsHelp: string; // "Help"
  settingsFeedback: string; // "Send feedback"
  settingsLanguageAuto: string; // "Auto"
  // Themes
  themeLight: string;
  themeDark: string;
  themeSystem: string;
  // Greeting (time-of-day phrases for all langs)
  greetingMorning: string; // "Good morning!"
  greetingAfternoon: string; // "Good afternoon!"
  greetingEvening: string; // "Good evening!"
  greetingAfterHours: string; // "Up late? How can I help?"
  greetingSub: string; // the line under the greeting
  // Casual greeting pool. Non-empty only for es/pt (reviewed-native-quality
  // markets); empty for en (component uses its own WARM_TEXTS) and for
  // fr/it/ja/ko/zh/tl (unreviewed, ~zero traffic — stay time-of-day only).
  casualGreetings: string[];
  // Disclaimer card (above chat input on landing)
  disclaimerLabel: string; // "Disclaimer:"
  disclaimerBody: string;
  // Buttons / tooltips
  sendButton: string; // "Send"
  regenerateButton: string; // "Regenerate"
  stopButton: string; // "Stop"
  copyButton: string; // "Copy"
  // Draft composer tooltips
  draftSend: string;
  // Thinking indicator — shown before the first backend status event lands
  thinkingDefault: string; // "Thinking…"
  // Sources drawer / pill
  sourcesTitle: string; // "Sources"
  sourcesCountSingular: string; // "{n} cited passage" — use {n} placeholder
  sourcesCountPlural: string; // "{n} cited passages"
  sourcesCloseAria: string; // "Close sources"
  sourcesOpenAria: string; // "Open {n} answer sources"
  sourceTypeGuide: string; // "Instructor guide (PDF)" (CLAUDE.md §8.3)
  sourceTypeExternal: string; // "External page · {host}"
  // Per-message thumb feedback (UserFeedbackComponent)
  feedbackLoveTitle: string; // "Love this"
  feedbackNeedsImprovementTitle: string; // "Needs improvement"
  feedbackPlaceholder: string; // textarea placeholder
  feedbackCancelButton: string; // "Cancel"
  feedbackSubmitButton: string; // "Submit"
  feedbackThanksToast: string; // "Thanks for your feedback!"
  // General feedback drawer (gear menu → Send feedback)
  gfDrawerTitle: string; // "Send feedback"
  gfDrawerDescription: string;
  gfDrawerLabel: string; // "Describe your feedback (required)"
  gfDrawerPlaceholder: string;
  gfDrawerSensitiveInfo: string;
  gfDrawerCancel: string; // "Cancel"
  gfDrawerSend: string; // "Send"
  gfDrawerSending: string; // "Sending..."
  gfDrawerCloseTitle: string; // "Close"
  gfDrawerEmptyToast: string;
  gfDrawerSuccessToast: string;
  gfDrawerErrorToast: string;
  // Draft composer (email/message editor) toasts
  draftLinkSelectFirstToast: string; // "Select text to turn into a link."
  draftLinkInvalidUrlToast: string; // "Enter a valid link URL."
  draftTweakErrorToast: string; // "Please rephrase."
}

export const CHROME_STRINGS: Partial<Record<LangCode, ChromeStrings>> = {
  en: {
    headerTitle: "Instructor Assistant",
    inputPlaceholder:
      "Ask about teaching, policies, pay, Canvas, student support…",
    inputPlaceholderShort: "Ask a question…",
    ferpaNotice: "Don’t include student names, IDs, or grades.",
    aiNoteShort: "AI answers can be wrong. Check the linked guide.",
    aiNoteLong:
      "Instructor Assistant is AI and can be wrong. Check the linked guide.",
    settingsTitle: "Settings",
    settingsTheme: "Theme",
    settingsLanguage: "Language",
    settingsHelp: "Help",
    settingsFeedback: "Send feedback",
    settingsLanguageAuto: "Auto",
    themeLight: "Light",
    themeDark: "Dark",
    themeSystem: "System",
    greetingMorning: "Good morning!",
    greetingAfternoon: "Good afternoon!",
    greetingEvening: "Good evening!",
    greetingAfterHours: "Up late? How can I help?",
    greetingSub:
      "Ask about teaching, course administration, student support, or instructor policies.",
    casualGreetings: [],
    disclaimerLabel: "Disclaimer:",
    disclaimerBody:
      " Answers are generated by AI from BYU-Pathway instructor guides and the public pages they link to. They may contain mistakes, so check the cited guide.",
    sendButton: "Send",
    regenerateButton: "Regenerate",
    stopButton: "Stop",
    copyButton: "Copy",
    draftSend: "Send",
    thinkingDefault: "Thinking…",
    sourcesTitle: "Sources",
    sourcesCountSingular: "{n} cited passage",
    sourcesCountPlural: "{n} cited passages",
    sourcesCloseAria: "Close sources",
    sourcesOpenAria: "Open {n} answer sources",
    sourceTypeGuide: "Instructor guide (PDF)",
    sourceTypeExternal: "External page · {host}",
    feedbackLoveTitle: "Helpful",
    feedbackNeedsImprovementTitle: "Not helpful",
    feedbackPlaceholder:
      "What would have made this answer more helpful? Please leave out student names and IDs.",
    feedbackCancelButton: "Cancel",
    feedbackSubmitButton: "Submit",
    feedbackThanksToast: "Thanks for your feedback!",
    gfDrawerTitle: "Send feedback",
    gfDrawerDescription:
      "Help us improve the BYU-Pathway Instructor Assistant. Share what happened and what you expected.",
    gfDrawerLabel: "Describe your feedback (required)",
    gfDrawerPlaceholder: "Tell us what prompted this feedback...",
    gfDrawerSensitiveInfo:
      "Please don’t include student names, IDs, grades, or other sensitive information.",
    gfDrawerCancel: "Cancel",
    gfDrawerSend: "Send",
    gfDrawerSending: "Sending...",
    gfDrawerCloseTitle: "Close",
    gfDrawerEmptyToast: "Please describe your feedback before sending.",
    gfDrawerSuccessToast: "Thanks for your feedback!",
    gfDrawerErrorToast: "Could not send feedback. Please try again.",
    draftLinkSelectFirstToast: "Select text to turn into a link.",
    draftLinkInvalidUrlToast: "Enter a valid link URL.",
    draftTweakErrorToast: "Please rephrase.",
  },
};

export function getChromeStrings(lang: LangCode): ChromeStrings {
  return CHROME_STRINGS[lang] ?? (CHROME_STRINGS.en as ChromeStrings);
}
