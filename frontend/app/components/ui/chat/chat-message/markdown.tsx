import "katex/dist/katex.min.css";
import { CSSProperties, FC, memo, ReactNode, useMemo } from "react";
import { Lock } from "lucide-react";
import ReactMarkdown, { Options } from "react-markdown";
import rehypeKatex from "rehype-katex";
import rehypeRaw from "rehype-raw";
import rehypeSanitize, { defaultSchema } from "rehype-sanitize";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { DateSpansData, SourceData } from "..";
import { DraftComposer } from "../widgets/DraftComposer";
import { draftEditKey } from "@/app/lib/draft-registry";
import {
  buildSourcesGroupId,
  CitationGroupPill,
  getSortedSources,
  SourceNumberButton,
} from "./chat-sources";
import styles from "./markdown.module.css";
import { isLoginLink, rehypeSignInNotes } from "./sign-in-links";

// Sanitization schema: extends the default rehype-sanitize whitelist with
// the 5 inline semantic tags we let the LLM emit. NO extra attributes are
// allowed on any tag — rejects <mark style="...">, <kbd onclick="...">,
// etc. <script>, <iframe>, event handlers all stay default-denied.
const MARKDOWN_SANITIZE_SCHEMA = {
  ...defaultSchema,
  tagNames: [
    ...(defaultSchema.tagNames || []),
    "mark",
    "kbd",
    "dfn",
    "sup",
    "sub",
  ],
  attributes: {
    ...defaultSchema.attributes,
  },
};

const DRAFT_STREAM_FONT_FAMILY = "Georgia, 'Times New Roman', Times, serif";

const NON_DRAFT_BLOCK_LANGUAGES = new Set([
  "javascript",
  "js",
  "typescript",
  "ts",
  "tsx",
  "jsx",
  "python",
  "py",
  "java",
  "c",
  "cpp",
  "c++",
  "csharp",
  "cs",
  "go",
  "rust",
  "ruby",
  "php",
  "swift",
  "kotlin",
  "scala",
  "haskell",
  "lua",
  "bash",
  "sh",
  "shell",
  "zsh",
  "powershell",
  "sql",
  "json",
  "yaml",
  "yml",
  "toml",
  "xml",
  "html",
  "css",
  "scss",
  "diff",
  "patch",
  "mermaid",
]);

const SUBJECT_LINE_RE =
  /^(subject|asunto|assunto|objet|oggetto|betreff|tema|assumpte|件名|主题|主旨|тема)\s*:/im;
const EMAIL_SALUTATION_RE =
  /^(dear|hello|hi|hola|ol[aá]|bonjour|salut|ciao|hallo|estimad[oa]|querid[oa]|prezad[oa]|gentile|cher|ch[eè]re|уважаем|дорог|亲爱|こんにちは)/im;
const EMAIL_SIGNOFF_RE =
  /(sincerely|best regards|kind regards|regards|atentamente|cordialmente|sauda[cç][oõ]es|sinceramente|merci|grazie|saluti|saludos|с уважением|благодарю|此致|敬具)/iu;
const MESSAGE_TONE_RE =
  /(whatsapp|sms|text message|mensaje de texto|mensagem de texto|mensagem|mensaje|メッセージ|短信|сообщение|cont[aá]ctame|reply|responde|respond[ea])/iu;

const inferDraftTypeFromBlock = (
  language: string,
  content: string,
): "email" | "message" | null => {
  const normalizedLanguage = (language || "").trim().toLowerCase();
  if (normalizedLanguage === "email" || normalizedLanguage === "message") {
    return normalizedLanguage;
  }

  if (normalizedLanguage && NON_DRAFT_BLOCK_LANGUAGES.has(normalizedLanguage)) {
    return null;
  }

  const text = (content || "").trim();
  if (!text) {
    return null;
  }

  const lines = text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
  const hasSubject = SUBJECT_LINE_RE.test(text);
  const hasSalutation =
    EMAIL_SALUTATION_RE.test(lines[0] || "") || EMAIL_SALUTATION_RE.test(text);
  const hasSignoff = EMAIL_SIGNOFF_RE.test(text);
  const hasMessageTone = MESSAGE_TONE_RE.test(text);

  if (hasSubject || (hasSalutation && hasSignoff)) {
    return "email";
  }

  if (hasMessageTone || hasSalutation) {
    return "message";
  }

  if (lines.length >= 2 && lines.length <= 18 && /\[[^\]]+\]/.test(text)) {
    return "message";
  }

  return null;
};

// Drafts are user-facing text the instructor will send to students — they
// should never contain citation markers. The backend `normalize_rtf_draft`
// hoists `[^N]` out of the fence on the supervisor's `rtf` route, but the
// Instant-mode (B2 critic) path bypasses it and gpt-4o-mini sometimes emits
// citations inside the fence anyway. Strip both the raw `[^N]` and the
// preprocessed `[citation:N]()` / `[citation-group:0,1]()` forms before
// handing content to DraftComposer or the raw-text loading fallback. This
// is mechanics — known string shapes — not a semantic gate.
const stripCitationMarkersForDraft = (text: string): string =>
  text
    .replace(/\[\^\d+\]/g, "")
    .replace(/\[citation(?:-group)?:[\d,]+\]\(\)/g, "")
    // Strip line-leading markdown heading markers ("### Overview" -> "Overview").
    // DraftComposer renders the body as plain text, so a heading the model
    // emits shows the literal `###` (observed live). Markdown headings belong
    // in neither an email nor a message; the line-leading-only match leaves a
    // WhatsApp message's intentional inline `*bold*`/`_italic_` untouched.
    // Backstops the backend `normalize_rtf_draft` strip for the Instant/B2
    // path that bypasses it. Mechanics — known string shapes — not a gate.
    .replace(/^[ \t]{0,3}#{1,6}[ \t]+/gm, "")
    // Unwrap markdown STRONG emphasis ("**Preview Your Material:**" -> "Preview
    // Your Material:"). Same class as the heading strip above and observed the
    // same way: the model bolds the label of each item in a tips list, and the
    // literal asterisks reach the instructor — then get pasted into an email
    // client that has no idea what they mean. Prompt-side this is already
    // forbidden, but it holds on the direct-draft route and leaks on the
    // anaphoric one (measured 0 vs 8 markers), so the render stays defensive.
    // DOUBLE delimiters only: `**`/`__` are markdown, whereas a WhatsApp draft
    // uses SINGLE `*bold*`/`_italic_` — deliberately preserved, as above.
    .replace(/\*\*(?=\S)([\s\S]*?\S)\*\*/g, "$1")
    .replace(/__(?=\S)([\s\S]*?\S)__/g, "$1")
    .replace(/[ \t]+(?=\n)/g, "")
    .replace(/[ \t]{2,}/g, " ");

const renderRawTextBlock = (value: string) => {
  return (
    <div className="mt-4 mb-4 max-w-full rounded-2xl border border-gray-200/90 dark:border-gray-700/60 bg-white dark:bg-[#1a1f2b] shadow-sm overflow-hidden">
      <pre
        className="m-0 px-4 py-4 whitespace-pre-wrap break-words text-[16px] leading-[1.72] text-gray-800 dark:text-gray-200"
        style={{ fontFamily: DRAFT_STREAM_FONT_FAMILY }}
      >
        {value}
      </pre>
    </div>
  );
};

const MemoizedReactMarkdown: FC<Options> = memo(
  ReactMarkdown,
  (prevProps, nextProps) =>
    prevProps.children === nextProps.children &&
    prevProps.className === nextProps.className,
);

// Split preprocessed markdown into top-level blocks at blank-line boundaries,
// never inside fenced code (``` / ~~~) or display math ($$).
//
// Streaming-jank fix (2026-06-12): the backend streams one character per SSE
// event (~55 updates/s) and react-markdown re-parsed the ENTIRE accumulated
// answer (remark + rehype incl. a full HTML parse) on every update, so
// per-chunk cost grew with answer length — measured live: 12 painted frames
// across a 193s stream with a single 101.7s main-thread task on a 2.5KB
// answer. Rendering each block through the children+className memo means only
// the still-growing TAIL block re-parses per update; completed blocks never
// re-render mid-stream. Prefix-stability matters: a block's text never changes
// once the blank line after it has streamed, so earlier blocks stay memoized.
const splitMarkdownBlocks = (md: string): string[] => {
  if (!md) {
    return [];
  }
  const blocks: string[] = [];
  let cur: string[] = [];
  let fenceChar: string | null = null;
  let inMath = false;
  for (const line of md.split("\n")) {
    if (fenceChar !== null) {
      cur.push(line);
      if (new RegExp(`^\\s{0,3}${fenceChar}{3,}\\s*$`).test(line)) {
        fenceChar = null;
      }
      continue;
    }
    if (inMath) {
      cur.push(line);
      if (/\$\$\s*$/.test(line)) {
        inMath = false;
      }
      continue;
    }
    const fenceOpen = line.match(/^\s{0,3}(`{3,}|~{3,})/);
    if (fenceOpen) {
      fenceChar = fenceOpen[1][0];
      cur.push(line);
      continue;
    }
    if (
      /^\s*\$\$/.test(line) &&
      !/\$\$\s*$/.test(line.replace(/^\s*\$\$/, ""))
    ) {
      inMath = true;
      cur.push(line);
      continue;
    }
    if (line.trim() === "") {
      if (cur.length) {
        blocks.push(cur.join("\n"));
        cur = [];
      }
      continue;
    }
    cur.push(line);
  }
  if (cur.length) {
    blocks.push(cur.join("\n"));
  }
  return blocks;
};

const stripInternalTableProps = <T extends object>(props: T): T => {
  const { isHeader: _isHeader, ...safeProps } = props as T & {
    isHeader?: boolean;
  };
  return safeProps as T;
};

const preprocessLaTeX = (content: string) => {
  // Replace block-level LaTeX delimiters \[ \] with $$ $$
  const blockProcessedContent = content.replace(
    /\\\[([\s\S]*?)\\\]/g,
    (_, equation) => `$$${equation}$$`,
  );
  // Replace inline LaTeX delimiters \( \) with $ $
  const inlineProcessedContent = blockProcessedContent.replace(
    /\\\[([\s\S]*?)\\\]/g,
    (_, equation) => `$${equation}$`,
  );
  return inlineProcessedContent;
};

const preprocessMedia = (content: string) => {
  // Remove `sandbox:` from the beginning of the URL
  // to fix OpenAI's models issue appending `sandbox:` to the relative URL
  return content.replace(/(sandbox|attachment|snt):/g, "");
};

/**
 * Convert [^number] format to [citation:index]() format
 * Maps footnote numbers to sorted source indices
 */
const preprocessFootnoteCitations = (content: string, sources?: SourceData) => {
  if (sources && sources.nodes.length > 0) {
    // Create sorted index mapping: footnote number -> sorted array index
    const sortedSources = sources.nodes.slice().sort((a, b) => {
      const getNumber = (id: string) =>
        parseInt(id.match(/^\d+/)?.[0] || "0", 10);
      return getNumber(a.citation_node_id) - getNumber(b.citation_node_id);
    });

    // Match [^1], [^2], etc.
    const footnoteRegex = /\[\^(\d+)\]/g;
    content = content.replace(footnoteRegex, (match, number) => {
      const footnoteNum = parseInt(number, 10);
      // Find the index in sorted array where citation_node_id matches the footnote number
      const sortedIndex = sortedSources.findIndex((node) => {
        const nodeNum = parseInt(
          node.citation_node_id.match(/^\d+/)?.[0] || "0",
          10,
        );
        return nodeNum === footnoteNum;
      });

      if (sortedIndex >= 0) {
        return `[citation:${sortedIndex}]()`;
      }
      return "";
    });
  }
  return content;
};

/**
 * Update the citation flag [citation:id]() to the new format [citation:index](url)
 */
const preprocessCitations = (content: string, sources?: SourceData) => {
  if (sources) {
    const sortedSources = sources.nodes.slice().sort((a, b) => {
      const getNumber = (id: string) =>
        parseInt(id.match(/^\d+/)?.[0] || "0", 10);
      return getNumber(a.citation_node_id) - getNumber(b.citation_node_id);
    });
    const citationRegex = /\[citation:(.+?)\]\(\)/g;
    let match;
    // Find all the citation references in the content
    while ((match = citationRegex.exec(content)) !== null) {
      const citationId = match[1];
      // Check if it's already an index (numeric)
      if (/^\d+$/.test(citationId)) {
        continue; // Already processed by preprocessFootnoteCitations
      }
      // Find the source node with the id equal to the citation-id, also get the index of the source node
      const sourceNode = sortedSources.find((node) => node.id === citationId);
      // If the source node is found, replace the citation reference with the new format
      if (sourceNode !== undefined) {
        content = content.replace(
          match[0],
          `[citation:${sortedSources.indexOf(sourceNode)}]()`,
        );
      } else {
        // If the source node is not found, remove the citation reference
        content = content.replace(match[0], "");
      }
    }
  }
  return content;
};

/**
 * Collapse adjacent citations into one grouped marker so the UI can render
 * `Source +2` instead of three separate chips jammed together at sentence end.
 */
const groupAdjacentCitations = (content: string) => {
  return content.replace(/((?:\[citation:\d+\]\(\)[ \t]*){2,})/g, (match) => {
    const indices = Array.from(match.matchAll(/\[citation:(\d+)\]\(\)/g)).map(
      (citationMatch) => citationMatch[1],
    );

    if (indices.length < 2) {
      return match;
    }

    return `[citation-group:${indices.join(",")}]()`;
  });
};

/**
 * Strip footnote-style DEFINITION lines like `[8]: Source description`.
 *
 * Some LLM outputs (especially when the model slips reference styles)
 * emit markdown footnote definitions like:
 *     [8]: Source: Certificate and Degrees List | Program List.
 * We render inline `[^N]` markers as clickable SourceNumberButtons;
 * the definition lines have no rendering target and leak as plain text
 * (or worse, get interpreted as reference-link targets by remark-gfm).
 *
 * Defensive: strip them client-side regardless of how good the prompt is.
 */
const stripFootnoteDefinitions = (content: string) => {
  return content.replace(/^\[\d+\]:\s.*$/gm, "");
};

const stripUnresolvedFootnoteMarkers = (content: string) => {
  return content.replace(/\[\^\d+\]/g, "");
};

// A field/value label the LLM puts on its own bullet: `- **Age:**` or
// `- **Age**:` and NOTHING else after it.
const FIELD_LABEL_ONLY_RE = /^\*\*[^*]+:\*\*$|^\*\*[^*]+\*\*:$/;
const BULLET_LINE_RE = /^(\s*)([-*+])\s+(.*)$/;

// Nest "orphan" field/value bullets so a field label and its values render as
// a clean nested list, not a flat run of same-level bullets.
//
// gpt-4o-mini, when a field has MULTIPLE values, emits the label on its own
// bullet and the values as sibling bullets — sometimes flat (0-space) and
// sometimes under-indented by 1 space, both of which GFM renders as siblings
// of the label (it needs >=2 spaces to nest). Observed live 2026-06-19 on the
// EC3-vs-PathwayConnect comparison. The generation prompt asks for inline
// `- **Label:** value`, but adoption is imperfect, so this is the deterministic
// backstop: a label-only bold-field bullet followed by non-field bullets has
// those values re-indented to nest under it. A "new field" bullet (its content
// starts with `**`) ends the group, so an inline `- **Education Level:** ...`
// stays a sibling. Idempotent on already-nested lists; runs before
// splitMarkdownBlocks so a tight list is processed as one unit.
const nestOrphanFieldValueBullets = (content: string): string => {
  const lines = content.split("\n");
  const out: string[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const m = line.match(BULLET_LINE_RE);
    if (m && FIELD_LABEL_ONLY_RE.test(m[3].trim())) {
      const parentIndent = m[1].length;
      out.push(line);
      i += 1;
      const nestIndent = " ".repeat(parentIndent + 2);
      while (i < lines.length) {
        const v = lines[i].match(BULLET_LINE_RE);
        if (
          v &&
          !v[3].trimStart().startsWith("**") &&
          v[1].length <= parentIndent + 3
        ) {
          out.push(`${nestIndent}${v[2]} ${v[3]}`);
          i += 1;
        } else {
          break;
        }
      }
      continue;
    }
    out.push(line);
    i += 1;
  }
  return out.join("\n");
};

const preprocessContent = (content: string, sources?: SourceData) => {
  const normalizedContent = stripFootnoteDefinitions(
    nestOrphanFieldValueBullets(
      // (Upstream's calendar "Block/Term N" and program-catalog heading
      // promotion is gone: it reshaped ordinary instructor answers.)
      preprocessMedia(preprocessLaTeX(content)),
    ),
  );
  const citationContent = preprocessCitations(
    preprocessFootnoteCitations(normalizedContent, sources),
    sources,
  );

  return groupAdjacentCitations(
    stripUnresolvedFootnoteMarkers(citationContent),
  );
};

const DATE_PATTERN = new RegExp(
  [
    "\\b(?:Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?),?\\s+(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\s+\\d{1,2}(?:,\\s*\\d{4})?\\b",
    "\\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\\s+\\d{1,2}(?:,\\s*\\d{4})?\\b",
    "\\b(?:\\p{L}+,\\s*)?\\d{1,2}\\s+de\\s+\\p{L}+\\s+de\\s+\\d{4}\\b",
    "\\b(?:\\p{L}+,\\s*)?\\d{1,2}\\s+(?!(?:of|in|on|at|to|or|an|as|by|is|it|and|the|for|from|with|has|was|are|but|not|this|that|than|into|each|per|via|del)\\s)\\p{L}+\\s+\\d{4}\\b",
    "\\b\\d{1,2}[/-]\\d{1,2}[/-]\\d{2,4}\\b",
    "\\b\\d{4}-\\d{2}-\\d{2}\\b",
  ].join("|"),
  "giu",
);

const DATE_CHIP_CLASSNAME =
  "date-chip inline-block align-baseline";

// The same pale-blue highlight as <mark> (markdown.css), in the answer's font.
const DATE_CHIP_STYLE: CSSProperties = {
  background: "var(--highlight-bg)",
  color: "var(--highlight-text)",
  borderRadius: "8px",
  padding: "1px 6px",
  fontWeight: 700,
  whiteSpace: "nowrap",
};

const escapeRegExp = (value: string): string => {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
};

const highlightDateText = (text: string): ReactNode[] => {
  const matches = Array.from(text.matchAll(DATE_PATTERN));
  if (matches.length === 0) {
    return [text];
  }

  const parts: ReactNode[] = [];
  let cursor = 0;

  matches.forEach((match, index) => {
    const matched = match[0];
    const start = match.index ?? -1;
    if (!matched || start < cursor) {
      return;
    }

    if (start > cursor) {
      parts.push(text.slice(cursor, start));
    }

    parts.push(
      <span
        key={`date-${start}-${index}`}
        className={DATE_CHIP_CLASSNAME}
        style={DATE_CHIP_STYLE}
      >
        {matched}
      </span>,
    );
    cursor = start + matched.length;
  });

  if (cursor < text.length) {
    parts.push(text.slice(cursor));
  }

  return parts;
};

const highlightDatePhrases = (text: string, phrases: string[]): ReactNode[] => {
  if (!text || phrases.length === 0) {
    return [text];
  }

  const escaped = phrases
    .map((phrase) => phrase.trim())
    .filter((phrase) => phrase.length > 0)
    .sort((a, b) => b.length - a.length)
    .map(escapeRegExp);

  if (escaped.length === 0) {
    return [text];
  }

  const phraseRegex = new RegExp(`(${escaped.join("|")})`, "giu");
  const segments = text.split(phraseRegex);
  const normalizedPhraseSet = new Set(
    phrases.map((phrase) => phrase.trim().toLocaleLowerCase()),
  );

  return segments
    .filter((segment) => segment.length > 0)
    .map((segment, index) => {
      const isDate = normalizedPhraseSet.has(
        segment.trim().toLocaleLowerCase(),
      );
      if (!isDate) {
        return <span key={`date-text-${index}`}>{segment}</span>;
      }

      return (
        <span
          key={`date-phrase-${index}`}
          className={DATE_CHIP_CLASSNAME}
          style={DATE_CHIP_STYLE}
        >
          {segment}
        </span>
      );
    });
};

const highlightDatesInChildren = (
  children: ReactNode,
  phrases: string[],
): ReactNode => {
  if (typeof children === "string") {
    return phrases.length > 0
      ? highlightDatePhrases(children, phrases)
      : highlightDateText(children);
  }

  if (Array.isArray(children)) {
    return children.map((child, index) => {
      if (typeof child === "string") {
        return (
          <span key={`date-text-${index}`}>
            {phrases.length > 0
              ? highlightDatePhrases(child, phrases)
              : highlightDateText(child)}
          </span>
        );
      }
      return child;
    });
  }

  return children;
};

export default function Markdown({
  content,
  sources,
  dateSpans,
  isLoading,
  userLanguage,
  messageId,
}: {
  content: string;
  sources?: SourceData;
  dateSpans?: DateSpansData;
  isLoading?: boolean;
  userLanguage?: string;
  messageId?: string;
}) {
  const processedContent = useMemo(
    () => preprocessContent(content, sources),
    [content, sources],
  );
  // Stable top-level blocks: only the last (still-growing) one re-parses
  // while streaming; the rest hit MemoizedReactMarkdown's children memo.
  const blocks = useMemo(
    () => splitMarkdownBlocks(processedContent),
    [processedContent],
  );
  const normalizedDatePhrases = useMemo(() => {
    if (!dateSpans?.phrases?.length) {
      return [] as string[];
    }

    const seen = new Set<string>();
    const uniquePhrases: string[] = [];
    for (const phrase of dateSpans.phrases) {
      const value = (phrase || "").trim();
      if (!value) {
        continue;
      }
      const key = value.toLowerCase();
      if (seen.has(key)) {
        continue;
      }
      seen.add(key);
      uniquePhrases.push(value);
    }

    return uniquePhrases;
  }, [dateSpans?.phrases]);

  // Sorted sources — same display order the Sources drawer uses. Shared
  // helper so citation chips and drawer rows agree on order + group id.
  const sortedSources = useMemo(
    () => getSortedSources(sources?.nodes),
    [sources?.nodes],
  );

  // Unique group id to scope citation-hover DOM queries. MUST be derived from
  // the SORTED sources — `buildSourcesGroupId` (used for the drawer rows) is
  // also called on sorted sources. Deriving it from the raw, unsorted
  // `sources.nodes` produced a mismatched id whenever the backend returned
  // nodes out of citation order, which silently broke the hover highlight.
  const groupId = useMemo(
    () => buildSourcesGroupId(sortedSources),
    [sortedSources],
  );

  // Hoisted from the JSX so every per-block renderer shares it. Memoized
  // blocks keep the closure from the render in which they last changed —
  // same staleness semantics the single-document memo had; the loading→ready
  // className flip re-renders every block once at settle with fresh values.
  const mdComponents: Options["components"] = {
    p({ children }) {
      return (
        <p className="mb-3 last:mb-0">
          {highlightDatesInChildren(children, normalizedDatePhrases)}
        </p>
      );
    },
    ul({ children }) {
      return <ul className="my-3 space-y-1.5 pl-5">{children}</ul>;
    },
    ol({ children, start }) {
      // Pass `start` through: when bullets/paragraphs split an ordered
      // list, markdown emits a SECOND <ol start={N}> — dropping it made
      // every continuation render from "1." again.
      return (
        <ol start={start} className="my-3 space-y-1.5 pl-5">
          {children}
        </ol>
      );
    },
    h2({ children }) {
      return (
        <h2 className={styles.heading2}>
          {highlightDatesInChildren(children, normalizedDatePhrases)}
        </h2>
      );
    },
    h3({ children }) {
      return (
        <h3 className={styles.heading3}>
          {highlightDatesInChildren(children, normalizedDatePhrases)}
        </h3>
      );
    },
    h4({ children }) {
      return (
        <h4 className={styles.heading4}>
          {highlightDatesInChildren(children, normalizedDatePhrases)}
        </h4>
      );
    },
    li({ children }) {
      return (
        <li>{highlightDatesInChildren(children, normalizedDatePhrases)}</li>
      );
    },
    table({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <div className={styles.tableWrapper}>
          <table className={styles.table} {...safeProps}>
            {children}
          </table>
        </div>
      );
    },
    thead({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <thead className={styles.tableHead} {...safeProps}>
          {children}
        </thead>
      );
    },
    tbody({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <tbody className={styles.tableBody} {...safeProps}>
          {children}
        </tbody>
      );
    },
    tr({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <tr className={styles.tr} {...safeProps}>
          {children}
        </tr>
      );
    },
    th({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <th className={styles.th} {...safeProps}>
          {children}
        </th>
      );
    },
    td({ node: _node, children, ...props }) {
      const safeProps = stripInternalTableProps(props);
      return (
        <td className={styles.td} {...safeProps}>
          {children}
        </td>
      );
    },
    blockquote({ node: _node, children, ...props }) {
      return (
        <blockquote className={styles.blockquote} {...props}>
          {children}
        </blockquote>
      );
    },
    code({ node, inline, className, children, ...props }) {
      if (children.length) {
        if (children[0] == "▍") {
          return <span className="mt-1 animate-pulse cursor-default">▍</span>;
        }

        children[0] = (children[0] as string).replace("`▍`", "▍");
      }

      const match = /language-(\w+)/.exec(className || "");
      const language = (match && match[1]) || "";

      if (inline) {
        const cls = [styles.inlineCode, className].filter(Boolean).join(" ");
        return (
          <code className={cls} {...props}>
            {children}
          </code>
        );
      }

      const blockContent = String(children).replace(/\n$/, "");
      const inferredDraftType = inferDraftTypeFromBlock(language, blockContent);

      if (inferredDraftType) {
        const cleanContent = stripCitationMarkersForDraft(blockContent);
        if (isLoading) {
          return renderRawTextBlock(cleanContent);
        }

        return (
          <DraftComposer
            type={inferredDraftType}
            content={cleanContent}
            isLoading={false}
            languageCode={userLanguage}
            persistKey={draftEditKey(messageId, cleanContent)}
          />
        );
      }

      return renderRawTextBlock(blockContent);
    },
    a({ href, children }) {
      // If a text link starts with 'citation:', then render it as a citation reference
      if (
        Array.isArray(children) &&
        typeof children[0] === "string" &&
        children[0].startsWith("citation-group:")
      ) {
        const indices = children[0]
          .replace("citation-group:", "")
          .split(",")
          .map((value) => Number(value))
          .filter((value) => Number.isInteger(value));

        if (indices.length > 0 && sortedSources) {
          return (
            <CitationGroupPill
              indices={indices}
              sources={sortedSources}
              groupId={groupId}
            />
          );
        }

        return <></>;
      }

      // If a text link starts with 'citation:', then render it as a citation reference
      if (
        Array.isArray(children) &&
        typeof children[0] === "string" &&
        children[0].startsWith("citation:")
      ) {
        const index = Number(children[0].replace("citation:", ""));
        if (!isNaN(index) && sortedSources && sortedSources[index]) {
          return (
            <SourceNumberButton
              index={index}
              node={sortedSources[index]}
              groupId={groupId}
            />
          );
        } else {
          // citation is not looked up yet, don't render anything
          return <></>;
        }
      }
      // A page behind a sign-in gets a lock before its text; the backend's
      // "(sign-in required)" note follows it.
      return (
        <a href={href} target="_blank" rel="noopener noreferrer">
          {isLoginLink(href) && (
            <Lock
              className="mr-1 inline-block h-[0.9em] w-[0.9em] align-[-0.1em]"
              aria-hidden="true"
            />
          )}
          {children}
        </a>
      );
    },
  };

  const loadingClass = isLoading ? "markdown-loading" : "markdown-ready";
  return (
    <div
      className={`prose dark:prose-invert prose-p:leading-relaxed prose-pre:p-0 break-words overflow-wrap-anywhere custom-markdown text-[#454540] dark:text-[#D6D6D6] text-[16px] leading-[1.6] tracking-normal max-w-full ${loadingClass}`}
    >
      {blocks.map((block, i) => (
        <MemoizedReactMarkdown
          key={i}
          className={`md-block ${loadingClass}`}
          remarkPlugins={[remarkGfm, remarkMath]}
          rehypePlugins={[
            rehypeRaw as any,
            [rehypeSanitize, MARKDOWN_SANITIZE_SCHEMA] as any,
            rehypeKatex as any,
            rehypeSignInNotes as any,
          ]}
          components={mdComponents}
        >
          {block}
        </MemoizedReactMarkdown>
      ))}
    </div>
  );
}
