const INLINE_FOOTNOTE_CITATION = /[ \t]*\[\^\d+\](?:[ \t]*\[\^\d+\])*/g;
const RENDERER_CITATION_PLACEHOLDER =
  /[ \t]*\[citation(?:-group)?:[^\]]+\]\(\)/g;

export function stripCitationsForClipboard(value: string): string {
  return value
    .replace(RENDERER_CITATION_PLACEHOLDER, "")
    .replace(INLINE_FOOTNOTE_CITATION, "")
    .replace(/[ \t]+([.,;:!?])/g, "$1")
    .replace(/[ \t]+\n/g, "\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

/**
 * Convert Markdown to clean, human-readable plain text for the clipboard.
 *
 * Instructors copy answers into emails and messages — they should never
 * see raw `###`, `**`, backticks, or `[text](url)` syntax. This strips the
 * syntax while keeping the words (and link URLs) intact.
 */
export function markdownToPlainText(value: string): string {
  return (
    value
      // Headings: "### Program Structure" -> "Program Structure"
      .replace(/^[ \t]*#{1,6}[ \t]+/gm, "")
      // Bold then italic (bold first so ** isn't half-eaten by * rules)
      .replace(/\*\*([^*]+)\*\*/g, "$1")
      .replace(/__([^_]+)__/g, "$1")
      .replace(/\*([^*\n]+)\*/g, "$1")
      .replace(/(^|[^A-Za-z0-9_])_([^_\n]+)_(?![A-Za-z0-9_])/g, "$1$2")
      // Strikethrough ~~text~~ -> text
      .replace(/~~([^~]+)~~/g, "$1")
      // Inline code `code` -> code
      .replace(/`([^`]+)`/g, "$1")
      // Images ![alt](url) -> alt  (before links)
      .replace(/!\[([^\]]*)\]\([^)]*\)/g, "$1")
      // Links [text](url) -> "text (url)", or just the url when they match
      .replace(/\[([^\]]+)\]\(([^)\s]+)[^)]*\)/g, (_m, text, url) =>
        text.trim() === url.trim() ? url : `${text} (${url})`,
      )
      // Blockquote markers "> " -> ""
      .replace(/^[ \t]*>[ \t]?/gm, "")
      // Markdown table separator rows ( |---|:--:| ) -> drop
      .replace(/^[ \t]*\|[ \t:|-]+\|[ \t]*$/gm, "")
      // Horizontal rules
      .replace(/^[ \t]*([-*_])[ \t]*\1[ \t]*\1[-*_ \t]*$/gm, "")
      // Bare inline HTML tags (<mark>, <kbd>, <sup>, ...)
      .replace(/<\/?[a-zA-Z][^>]*>/g, "")
      // Tidy whitespace left behind
      .replace(/[ \t]{2,}/g, " ")
      .replace(/[ \t]+([.,;:!?])/g, "$1")
      .replace(/[ \t]+\n/g, "\n")
      .replace(/\n{3,}/g, "\n\n")
      .trim()
  );
}

/**
 * Full clipboard cleanup for an assistant answer: drop citation markers,
 * then flatten Markdown to readable plain text.
 */
export function cleanAnswerForClipboard(value: string): string {
  return markdownToPlainText(stripCitationsForClipboard(value));
}
