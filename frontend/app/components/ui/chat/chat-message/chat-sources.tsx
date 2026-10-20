import { BookOpen, ExternalLink, FileText, Globe, X } from "lucide-react";
import { MouseEvent, useEffect, useMemo, useRef, useState } from "react";

import { getChromeStrings, type ChromeStrings } from "../../../../lib/chrome-strings";
import { resolveUiLanguage } from "../../../../lib/i18n";
import {
  HoverCard,
  HoverCardContent,
  HoverCardTrigger,
} from "../../hover-card";
import { cn } from "../../lib/utils";
import { SourceData, SourceNode } from "../index";

export const SOURCES_PANEL_EVENT = "pathway:sources-panel";

export type SourcesPanelEventDetail = {
  open: boolean;
  nodes?: SourceNode[];
  groupId?: string;
  // Positions (in citation order) of the sources the answer cites. The panel
  // lists only these, numbered as their badges are.
  citedIndices?: number[];
};

const METADATA_TITLE_KEYS = [
  "title_tag",
  "logical_doc_label",
  "title",
  "page_title",
  "document_title",
  "source_title",
  "file_name",
  "name",
];

const MAX_SNIPPET_LENGTH = 230;

const getCitationNumber = (node: SourceNode) =>
  parseInt(node.citation_node_id.match(/^\d+/)?.[0] || "0", 10);

export const getSortedSources = (nodes: SourceNode[] = []) =>
  nodes.slice().sort((a, b) => getCitationNumber(a) - getCitationNumber(b));

/**
 * Which sources an answer cites: the positions, in getSortedSources order,
 * of the nodes its [^N] markers point at. Markdown maps a marker to a badge
 * the same way (preprocessFootnoteCitations), so a badge's number and its
 * card's number always agree. The backend sends every retrieved node, cited
 * or not; only the cited ones back the answer.
 */
export const getCitedIndices = (answer: string, sorted: SourceNode[]) => {
  const indices = new Set<number>();
  for (const match of (answer || "").matchAll(/\[\^(\d+)\]/g)) {
    const number = parseInt(match[1], 10);
    const index = sorted.findIndex((node) => getCitationNumber(node) === number);
    if (index >= 0) indices.add(index);
  }
  return Array.from(indices).sort((a, b) => a - b);
};

export const buildSourcesGroupId = (nodes: SourceNode[] = []) => {
  if (nodes.length === 0) return "";
  return nodes[0].id.replace(/[^a-zA-Z0-9]/g, "").slice(0, 16);
};

const safeUrl = (url?: string) => {
  if (!url) return null;
  try {
    return new URL(url);
  } catch {
    return null;
  }
};

export const getSourceDomain = (url?: string) => {
  const parsedUrl = safeUrl(url);
  if (!parsedUrl) return "Source";
  return parsedUrl.hostname.replace(/^www\./, "");
};

const prettifyDomain = (domain: string) => {
  if (!domain || domain === "Source") return "Source";
  const parts = domain.split(".");
  const brand = parts.length > 2 ? parts.at(-2) || domain : parts[0];
  return brand
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
};

const titleFromUrl = (url?: string) => {
  const parsedUrl = safeUrl(url);
  if (!parsedUrl) return "";
  const lastPathSegment = parsedUrl.pathname.split("/").filter(Boolean).at(-1);
  if (!lastPathSegment) return prettifyDomain(getSourceDomain(url));
  return decodeURIComponent(lastPathSegment)
    .replace(/\.(html|pdf|aspx?)$/i, "")
    .replace(/[-_]+/g, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
};

const normalizeSourceTitle = (value: string) => {
  return (
    value
      .replace(/\s+/g, " ")
      .trim()
      .replace(/\bBYU\s*[- ]?\s*Pathway\b/gi, "BYU-Pathway")
      .replace(/\bBYU\s*[- ]?\s*Idaho\b/gi, "BYU-Idaho")
      .replace(/\bByupathway\b/gi, "BYU-Pathway")
      // Strip the trailing " | <Site>" SEO title suffix so a page title like
      // "Course Drops and Withdrawals | BYU-Pathway Worldwide" doesn't carry the
      // site name into the citation chip. Matches the final pipe-segment when it
      // contains a known BYU-Pathway-family site name (tolerates a trailing
      // "Worldwide"/"Online" etc.); [^|]* keeps it to the LAST segment only.
      .replace(
        /\s*\|\s*[^|]*\b(?:BYU-Pathway|BYU-Idaho|EnglishConnect|Ensign College)\b[^|]*$/i,
        "",
      )
      .trim()
  );
};

// Page CHROME that some crawled pages use as their <title> (a call-to-action
// prompt or a bare site name), which makes a poor citation source label. When a
// source's metadata title is chrome, skip it and fall back to the URL-derived
// title (e.g. byupathway.edu/help-faqs -> "Help Faqs"). This is the source-label
// side of the same fix that strips the CTA header from retrieved chunk TEXT.
const isChromeSourceTitle = (value: string) => {
  const v = value.trim();
  if (!v) return true;
  if (/^Have\s+(any\s+questions|a\s+question)\b.*\bhelp\b/i.test(v))
    return true;
  if (/^(BYU-Pathway|BYU-Idaho|EnglishConnect|Ensign College)$/i.test(v))
    return true;
  return false;
};

export const getSourceTitle = (node?: SourceNode) => {
  if (!node) return "Source";

  for (const key of METADATA_TITLE_KEYS) {
    const value = node.metadata?.[key];
    if (typeof value === "string") {
      const cleanValue = normalizeSourceTitle(value);
      if (
        cleanValue &&
        !/^https?:\/\//i.test(cleanValue) &&
        !isChromeSourceTitle(cleanValue)
      ) {
        return cleanValue;
      }
    }
  }

  return (
    normalizeSourceTitle(titleFromUrl(node.url)) ||
    normalizeSourceTitle(prettifyDomain(getSourceDomain(node.url)))
  );
};

const truncateText = (value: string, maxLength: number) => {
  if (value.length <= maxLength) return value;
  return `${value.slice(0, maxLength - 1).trimEnd()}...`;
};

export const getSourceSnippet = (
  node?: SourceNode,
  maxLength = MAX_SNIPPET_LENGTH,
) => {
  const text = (node?.text || "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .trim();

  if (!text) return "";

  const sentence =
    text.match(/.{80,}?[.!?](?:\s|$)/)?.[0]?.trim() ||
    text.match(/[^.!?]+[.!?]/)?.[0]?.trim() ||
    text;

  return truncateText(sentence, maxLength);
};

const highlightReferenceListItem = (
  groupId: string | undefined,
  index: number,
  shouldHighlight: boolean,
) => {
  if (!groupId) return;
  const selector = `.reference-list-item[data-citation-group="${groupId}"][data-citation-index="${index}"]`;
  document
    .querySelectorAll(selector)
    .forEach((item) =>
      item.classList.toggle("citation-hovered", shouldHighlight),
    );
};

// The instructor guides are `source=instructor-assistant`; the public pages
// they link to are `instructor-assistant-linked` (CLAUDE.md §1, §8.3).
const LINKED_SOURCE = "instructor-assistant-linked";

export const isExternalSource = (node?: SourceNode) =>
  node?.metadata?.source === LINKED_SOURCE;

/** "Instructor guide (PDF)" or "External page · <host>" (CLAUDE.md §8.3). */
export const getSourceTypeLabel = (
  node: SourceNode | undefined,
  strings: ChromeStrings,
) =>
  isExternalSource(node)
    ? strings.sourceTypeExternal.replace("{host}", getSourceDomain(node?.url))
    : strings.sourceTypeGuide;

function useChromeStrings() {
  const [uiLang, setUiLang] =
    useState<ReturnType<typeof resolveUiLanguage>>("en");
  useEffect(() => {
    setUiLang(resolveUiLanguage());
    const handler = () => setUiLang(resolveUiLanguage());
    window.addEventListener("user-language-pref-changed", handler);
    return () =>
      window.removeEventListener("user-language-pref-changed", handler);
  }, []);
  return getChromeStrings(uiLang);
}

function SourceTypeLine({
  node,
  strings,
}: {
  node?: SourceNode;
  strings: ChromeStrings;
}) {
  const external = isExternalSource(node);
  return (
    <p className="m-0 flex items-center gap-1.5 text-[13px] leading-snug text-ia-text">
      {external ? (
        <Globe aria-hidden="true" className="h-3.5 w-3.5 flex-shrink-0 text-ia-blue-3" />
      ) : (
        <FileText aria-hidden="true" className="h-3.5 w-3.5 flex-shrink-0" />
      )}
      <span className="truncate">{getSourceTypeLabel(node, strings)}</span>
    </p>
  );
}

/**
 * The "Sources (N)" button under an answer (prototype btn-secondary). N counts
 * the sources the answer cites. An answer that cites nothing (a refusal, "not
 * in the guides") gets no button: nothing backs it.
 */
export function ChatSources({ data, answer }: { data: SourceData; answer: string }) {
  const strings = useChromeStrings();
  const sortedSources = useMemo(
    () => getSortedSources(data.nodes),
    [data.nodes],
  );
  const groupId = useMemo(
    () => buildSourcesGroupId(sortedSources),
    [sortedSources],
  );
  const citedIndices = useMemo(
    () => getCitedIndices(answer, sortedSources),
    [answer, sortedSources],
  );

  if (citedIndices.length === 0) return null;

  const openSourcesPanel = () => {
    window.dispatchEvent(
      new CustomEvent<SourcesPanelEventDetail>(SOURCES_PANEL_EVENT, {
        detail: {
          open: true,
          nodes: sortedSources,
          groupId,
          citedIndices,
        },
      }),
    );
  };

  return (
    <>
      <button
        type="button"
        onClick={openSourcesPanel}
        className="inline-flex h-11 items-center gap-2 rounded-full border border-ia-border bg-transparent px-4 text-sm font-semibold text-ia-text transition-colors hover:border-ia-border-strong focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg sm:h-10"
        aria-label={strings.sourcesOpenAria.replace(
          "{n}",
          String(citedIndices.length),
        )}
      >
        <BookOpen className="h-[18px] w-[18px]" aria-hidden="true" />
        <span>
          {strings.sourcesTitle} ({citedIndices.length})
        </span>
      </button>
    </>
  );
}

function CitationPopoverContent({
  node,
  index,
  strings,
}: {
  node?: SourceNode;
  index: number;
  strings: ChromeStrings;
}) {
  const title = getSourceTitle(node);
  const snippet = getSourceSnippet(node, 190);

  return (
    <a
      href={node?.url || "#"}
      target={node?.url ? "_blank" : undefined}
      rel={node?.url ? "noopener noreferrer" : undefined}
      className="block rounded-xl p-4 text-left no-underline"
    >
      <div className="flex items-start gap-3">
        <span className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-full bg-ia-blue-2 text-[13px] font-bold text-ia-gray-4">
          {index + 1}
        </span>
        <div className="flex min-w-0 flex-col gap-1.5">
          <p className="m-0 line-clamp-2 text-[15px] font-semibold leading-snug text-ia-text">
            {title || `Source ${index + 1}`}
          </p>
          <SourceTypeLine node={node} strings={strings} />
          {snippet && (
            <p className="m-0 line-clamp-3 text-sm leading-[1.45] text-ia-text">
              {snippet}
            </p>
          )}
        </div>
      </div>
    </a>
  );
}

// The inline citation badge (direction D): Blue 2 with Gray 4 at rest,
// Blue 4 with white when hovered or focused. 22px, 26px on phones.
const CITE_BADGE =
  "citation-link mx-[2px] inline-flex h-[26px] min-w-[26px] items-center justify-center rounded-full px-[7px] align-[1px] sm:h-[22px] sm:min-w-[22px] " +
  "bg-ia-blue-2 text-[13px] font-bold leading-none text-ia-gray-4 no-underline sm:text-xs " +
  "transition-colors duration-150 hover:bg-ia-blue-4 hover:text-white " +
  "focus-visible:bg-ia-blue-4 focus-visible:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus focus-visible:ring-offset-2 focus-visible:ring-offset-ia-bg";

export function SourceNumberButton({
  index,
  className,
  node,
  url,
  groupId,
}: {
  index: number;
  className?: string;
  node?: SourceNode;
  url?: string;
  groupId?: string;
}) {
  const strings = useChromeStrings();
  const sourceNode =
    node ?? (url ? ({ url, metadata: {}, text: "" } as SourceNode) : undefined);
  const sourceUrl = sourceNode?.url || url;
  const title = getSourceTitle(sourceNode);

  const handleMouseEnter = () =>
    highlightReferenceListItem(groupId, index, true);
  const handleMouseLeave = () =>
    highlightReferenceListItem(groupId, index, false);

  const badge = (
    <a
      href={sourceUrl || "#"}
      target={sourceUrl ? "_blank" : undefined}
      rel={sourceUrl ? "noopener noreferrer" : undefined}
      className={cn(CITE_BADGE, className)}
      aria-label={`Source ${index + 1}: ${title}${sourceUrl ? " (opens in a new tab)" : ""}`}
      data-citation-index={index}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
    >
      {index + 1}
    </a>
  );

  return (
    <HoverCard openDelay={120} closeDelay={80}>
      <HoverCardTrigger asChild>{badge}</HoverCardTrigger>
      <HoverCardContent
        side="top"
        align="start"
        className="w-[min(360px,calc(100vw-32px))] rounded-xl border-ia-border bg-ia-surface p-0 text-ia-text shadow-ia-pop"
      >
        <CitationPopoverContent node={sourceNode} index={index} strings={strings} />
      </HoverCardContent>
    </HoverCard>
  );
}

/**
 * Several citations at one spot. Up to three show as badges side by side;
 * more collapse to the first badge plus a "+N" button that expands them.
 */
export function CitationGroupPill({
  indices,
  sources,
  groupId,
}: {
  indices: number[];
  sources: SourceNode[];
  groupId?: string;
}) {
  const [isExpanded, setIsExpanded] = useState(false);
  const validIndices = indices.filter((index) => sources[index]);

  if (validIndices.length === 0) return null;

  const shown = isExpanded || validIndices.length <= 3 ? validIndices : validIndices.slice(0, 1);
  const hidden = validIndices.length - shown.length;

  const expandGroup = (event: MouseEvent<HTMLButtonElement>) => {
    event.preventDefault();
    event.stopPropagation();
    setIsExpanded(true);
  };

  return (
    <span className="inline-flex max-w-full flex-wrap items-center gap-y-1 align-baseline">
      {shown.map((index) => (
        <SourceNumberButton
          key={index}
          index={index}
          node={sources[index]}
          groupId={groupId}
        />
      ))}
      {hidden > 0 && (
        <button
          type="button"
          onClick={expandGroup}
          className={CITE_BADGE}
          aria-label={`Show ${hidden} more citation${hidden === 1 ? "" : "s"}`}
          aria-expanded={false}
        >
          +{hidden}
        </button>
      )}
    </span>
  );
}

/** The Sources panel (prototype side panel): one card per source. */
export function SourcesSidebar({
  open,
  nodes,
  groupId,
  citedIndices,
  onClose,
}: {
  open: boolean;
  nodes: SourceNode[];
  groupId?: string;
  citedIndices?: number[];
  onClose: () => void;
}) {
  const sortedAll = useMemo(() => getSortedSources(nodes), [nodes]);
  // Only the cited sources, each keeping its position (= its badge number).
  const listed = useMemo(() => {
    const entries = sortedAll.map((node, index) => ({ node, index }));
    if (!citedIndices) return entries;
    const cited = new Set(citedIndices);
    return entries.filter((entry) => cited.has(entry.index));
  }, [sortedAll, citedIndices]);
  const asideRef = useRef<HTMLElement>(null);
  const strings = useChromeStrings();
  const passagesTemplate =
    listed.length === 1
      ? strings.sourcesCountSingular
      : strings.sourcesCountPlural;
  const passagesLabel = passagesTemplate.replace(
    "{n}",
    String(listed.length),
  );

  // Toggle `inert` imperatively (React 18 drops `inert=""`): a closed panel
  // is off-screen but its links would stay focusable, so Tab would land in
  // it and scroll the page sideways.
  useEffect(() => {
    const node = asideRef.current;
    if (!node) return;
    if (open) {
      node.removeAttribute("inert");
    } else {
      node.setAttribute("inert", "");
    }
  }, [open]);

  // Escape closes the panel.
  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  return (
    <aside
      ref={asideRef}
      className={cn(
        "absolute right-0 top-0 z-30 flex h-full w-full flex-col sm:w-[320px] lg:w-[400px]",
        "border-l border-ia-border bg-ia-surface text-ia-text shadow-ia-panel",
        "transition-[transform,opacity] duration-300 ease-[cubic-bezier(0.22,1,0.36,1)] motion-reduce:transition-none",
        open
          ? "translate-x-0 opacity-100"
          : "pointer-events-none translate-x-full opacity-0",
      )}
      aria-hidden={!open}
      aria-label={strings.sourcesTitle}
    >
      <div className="flex items-center justify-between gap-3 border-b border-ia-border py-4 pl-6 pr-4">
        <div className="min-w-0">
          <h2 className="m-0 text-lg font-bold leading-tight">{strings.sourcesTitle}</h2>
          <p className="m-0 text-[13px] leading-snug">{passagesLabel}</p>
        </div>
        <button
          type="button"
          onClick={onClose}
          className="inline-flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-ia-text transition-colors hover:bg-ia-blue-1 hover:text-ia-gray-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus"
          aria-label={strings.sourcesCloseAria}
        >
          <X aria-hidden="true" className="h-5 w-5" />
        </button>
      </div>

      <ol className="m-0 flex min-h-0 flex-1 list-none flex-col gap-3 overflow-y-auto p-4 sm:px-6 sm:pb-6">
        {listed.map(({ node, index }) => {
          const title = getSourceTitle(node);
          const snippet = getSourceSnippet(node);
          const external = isExternalSource(node);

          return (
            <li
              key={`${node.id}-${index}`}
              data-citation-group={groupId}
              data-citation-index={index}
              className="reference-list-item flex gap-3 rounded-xl border border-ia-border bg-ia-surface p-4 dark:bg-ia-gray-5"
            >
              <span className="flex h-[26px] w-[26px] flex-shrink-0 items-center justify-center rounded-full bg-ia-blue-2 text-[13px] font-bold text-ia-gray-4">
                {index + 1}
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                <h3 className="m-0 text-[15px] font-semibold leading-snug">
                  {title || `Source ${index + 1}`}
                </h3>
                <SourceTypeLine node={node} strings={strings} />
                {snippet && (
                  <p className="m-0 line-clamp-3 text-sm leading-[1.45]">{snippet}</p>
                )}
                {node.url && (
                  <a
                    href={node.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="mt-0.5 inline-flex min-h-[44px] items-center gap-1.5 self-start text-sm font-semibold text-ia-link underline sm:min-h-0 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ia-focus"
                  >
                    {external ? "Open page" : "Open guide"}
                    <ExternalLink aria-hidden="true" className="h-3.5 w-3.5" />
                    <span className="sr-only">(opens in a new tab)</span>
                  </a>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </aside>
  );
}
